"""MaapClient facade for MAAP EarthCARE data access."""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from pathlib import Path
from typing import Optional

from maap_client.auth import load_credentials, TokenManager
from maap_client.catalog_build import BaselineInfo, CatalogCollectionManager
from maap_client.catalog_query import CatalogQueryablesManager
from maap_client.config import MaapConfig
from maap_client.download import DownloadManager
from maap_client.exceptions import InvalidRequestError
from maap_client.search import MaapSearcher
from maap_client.tracker import GlobalStateTracker, StateTracker
from maap_client.paths import extract_baseline, extract_product
from maap_client.registry import Registry
from maap_client.types import DownloadResult, SearchResult, SyncResult
from maap_client.utils import normalize_time_range as _normalize_time_range
from maap_client.utils import parse_datetime, timezone_is_aware, to_zulu

logger = logging.getLogger(__name__)


class MaapClient:
    """
    High-level client for MAAP EarthCARE data access.

    Provides a unified interface for:
    - Listing collections, products, and baselines
    - Searching for data products
    - Downloading files
    - Tracking download state

    Note:
        This class is not thread-safe. Create separate instances for concurrent use.
    """

    def __init__(self, config: Optional[MaapConfig] = None):
        """
        Initialize MAAP client.

        Args:
            config: Optional configuration (uses defaults/env if not provided)
        """
        self._config = config or MaapConfig.load()
        self._catalog: Optional[CatalogQueryablesManager] = None
        self._searcher: Optional[MaapSearcher] = None
        self._token_manager: Optional[TokenManager] = None
        self._downloader: Optional[DownloadManager] = None
        self._state: Optional[GlobalStateTracker] = None

    @property
    def config(self) -> MaapConfig:
        """Get current configuration."""
        return self._config

    @property
    def catalog(self) -> CatalogQueryablesManager:
        """Get catalog manager (lazy initialization)."""
        if self._catalog is None:
            self._catalog = CatalogQueryablesManager(
                catalog_url=self._config.catalog_url,
                catalog_dir=self._config.catalog_dir,
            )
        return self._catalog

    @property
    def searcher(self) -> MaapSearcher:
        """Get STAC searcher (lazy initialization)."""
        if self._searcher is None:
            self._searcher = MaapSearcher(
                catalog_url=self._config.catalog_url,
                mission_start=self._config.mission_start,
                mission_end=self._config.mission_end,
            )
        return self._searcher

    @property
    def state(self) -> GlobalStateTracker:
        """Get state tracker manager (lazy initialization)."""
        if self._state is None:
            self._state = GlobalStateTracker(
                registry_dir=self._config.registry_dir,
                mission=self._config.mission,
                data_dir=self._config.data_dir,
            )
        return self._state

    def _get_token_manager(self) -> TokenManager:
        """Get token manager (lazy initialization, requires credentials)."""
        if self._token_manager is None:
            credentials = load_credentials(self._config.credentials_file)
            self._token_manager = TokenManager(
                credentials=credentials,
                token_url=self._config.token_url,
            )
        return self._token_manager

    def _get_downloader(self) -> DownloadManager:
        """Get download manager (lazy initialization)."""
        if self._downloader is None:
            self._downloader = DownloadManager(
                token_manager=self._get_token_manager(),
                data_dir=self._config.data_dir,
                mission=self._config.mission,
            )
        return self._downloader

    # === VALIDATION ===

    @staticmethod
    def _validate_time_range(
        start: Optional[datetime],
        end: Optional[datetime],
        orbit: Optional[str] = None,
    ) -> None:
        """
        Validate time parameters. Called by methods with time/orbit args.

        Args:
            start: Start datetime
            end: End datetime
            orbit: Orbit+frame string

        Raises:
            InvalidRequestError: If validation fails
        """
        # Timezone awareness (prevents subtle bugs from naive datetimes)
        if start is not None and not timezone_is_aware(start):
            raise InvalidRequestError(
                "'start' must be timezone-aware (e.g., datetime(..., tzinfo=timezone.utc))."
            )
        if end is not None and not timezone_is_aware(end):
            raise InvalidRequestError(
                "'end' must be timezone-aware (e.g., datetime(..., tzinfo=timezone.utc))."
            )

        # Mutual exclusivity
        if orbit and (start or end):
            raise InvalidRequestError(
                "Cannot combine 'orbit' with 'start'/'end'. "
                "Use orbit for orbit-based search, or start/end for time-based."
            )

        # Logical order
        if start and end and start > end:
            raise InvalidRequestError(
                f"'start' must be before 'end' (got {start} > {end})."
            )

    # === CATALOG OPERATIONS ===

    def update_catalogs(
        self,
        collections: Optional[list[str]] = None,
        force: bool = False,
        out_dir: Optional[Path] = None,
    ) -> dict[str, Path]:
        """
        Download/update catalog queryables.
        """
        self._config.ensure_directories()
        if out_dir:
            manager = CatalogQueryablesManager(
                catalog_url=self._config.catalog_url,
                catalog_dir=out_dir,
            )
            return manager.download(collections, force)
        return self.catalog.download(collections, force)

    def list_collections(self) -> list[str]:
        """List all known MAAP collections from config."""
        return self._config.collections.copy()

    def list_products(
        self,
        collection: str,
        from_built: bool = False,
        verify: bool = False,
    ) -> list[str]:
        """
        List products for a collection.
        """
        # MAAP - Catalog Queryables refresh
        if verify:
            queryables = self.catalog.load(collection, refresh=True)
            return queryables.list_products()

        # Catalog Built
        if from_built:
            manager = CatalogCollectionManager(
                client=self, catalog_dir=self.config.built_catalog_dir
            )
            catalog = manager.load(collection)
            if not catalog:
                raise FileNotFoundError(
                    f"Built catalog not found for {collection}. "
                    f"Run: maap catalog build {collection}"
                )
            return catalog.list_products()

        # Catalog Queryables (only if already exist, read-only)
        queryables = self.catalog.load(collection, refresh=False)
        return queryables.list_products()

    def list_baselines(
        self,
        collection: str,
        product_type: str = "",
        from_built: bool = False,
        verify: bool = False,
    ) -> list[str]:
        """
        List available baselines.
        """
        if (verify or from_built) and not product_type:
            raise ValueError(
                "product_type is required when verify=True or from_built=True"
            )

        # MAAP
        if verify:
            return self.searcher.search_baselines(
                collection, product_type, catalog_manager=self.catalog
            )

        # Catalog Built
        if from_built:
            manager = CatalogCollectionManager(
                client=self, catalog_dir=self.config.built_catalog_dir
            )
            catalog = manager.load(collection)
            if not catalog:
                raise FileNotFoundError(
                    f"Built catalog not found for {collection}. "
                    f"Run: maap catalog build {collection} {product_type}"
                )
            product_info = catalog.get_product(product_type)
            if not product_info:
                raise ValueError(
                    f"Product {product_type} not found in built catalog. "
                    f"Run: maap catalog build {collection} {product_type}"
                )
            return product_info.list_baselines()

        # Catalog Queryables (only if already exist, read-only)
        queryables = self.catalog.load(collection, refresh=False)

        return queryables.list_baselines()

    def get_baseline_info(
        self,
        collection: str,
        product_type: str,
        baseline: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        from_built: bool = False,
    ) -> Optional[BaselineInfo]:
        """
        Get metadata for a specific baseline.

        Args:
            collection: Collection name
            product_type: Product type name
            baseline: Baseline version
            start: Optional start datetime to limit search range
            end: Optional end datetime to limit search range
            from_built: If True, load from built catalog instead of API
        """
        if from_built:
            try:
                manager = CatalogCollectionManager(
                    client=self, catalog_dir=self.config.built_catalog_dir
                )
                catalog = manager.load(collection)
                if not catalog:
                    return None
                product_info = catalog.get_product(product_type)
                if not product_info:
                    return None
                return product_info.get_baseline(baseline)
            except (FileNotFoundError, ValueError):
                return None

        info_range = self.searcher.search_product_info_range(
            collection=collection,
            product_type=product_type,
            baseline=baseline,
            start=start,
            end=end,
        )

        if info_range is None:
            return None

        first_granule, last_granule = info_range

        count = self.searcher.search_product_count(
            collection=collection,
            product_type=product_type,
            baseline=baseline,
            start=start,
            end=end,
        )

        now = to_zulu(datetime.now(timezone.utc))

        return BaselineInfo(
            time_start=to_zulu(first_granule.sensing_time),
            time_end=to_zulu(last_granule.sensing_time),
            frame_start=first_granule.orbit_frame,
            frame_end=last_granule.orbit_frame,
            count=count,
            updated_at=now,
        )

    # === STATE OPERATIONS ===

    def get_tracker(
        self,
        collection: str,
        product_type: str,
        baseline: str,
    ) -> StateTracker:
        """
        Get a state tracker for a specific collection/product/baseline.

        Args:
            collection: Collection name
            product_type: Product type name
            baseline: Baseline version

        Returns:
            StateTracker instance
        """
        self._config.ensure_directories()
        return self.state.get_tracker(collection, product_type, baseline)

    # === UTILITY METHODS ===

    def normalize_time_range(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> tuple[datetime, datetime]:
        """
        Normalize and clamp a time range to mission bounds and current time.

        - Defaults start to mission_start, clamps to be >= mission_start
        - Defaults end to min(now, mission_end), clamps to be <= min(now, mission_end)

        Args:
            start: Optional start datetime
            end: Optional end datetime

        Returns:
            Tuple of (start, end) datetimes clamped to valid mission bounds
        """
        mission_start = parse_datetime(self._config.mission_start)
        mission_end = parse_datetime(self._config.mission_end)
        return _normalize_time_range(start, end, mission_start, mission_end)

    # === REGISTRY OPERATIONS ===

    def save_to_registry(
        self,
        urls: list[str],
        collection: str,
        product_type: str,
    ) -> tuple[int, list[Path]]:
        """
        Save URLs to registry files, grouped by sensing date and baseline.

        Automatically extracts baseline from each URL and routes it to the
        correct registry path. Handles mixed baselines in the same URL list.

        Args:
            urls: List of URLs to save (can contain mixed baselines)
            collection: Collection name
            product_type: Product type

        Returns:
            Tuple of (new_urls_count, files_written)
        """
        if not urls:
            return 0, []

        # Group URLs by baseline
        urls_by_baseline: dict[str, list[str]] = {}
        for url in urls:
            filename = os.path.basename(url)
            bl = extract_baseline(filename) or "UNKNOWN"
            urls_by_baseline.setdefault(bl, []).append(url)

        total_new_count = 0
        all_files_written: list[Path] = []
        for bl, bl_urls in urls_by_baseline.items():
            registry = Registry(
                registry_dir=self._config.registry_dir,
                mission=self._config.mission,
                collection=collection,
                product_type=product_type,
                baseline=bl,
            )
            new_count, files = registry.save_urls(bl_urls, self._config.data_dir)
            total_new_count += new_count
            all_files_written.extend(files)

        # Return count and unique files
        return total_new_count, list(dict.fromkeys(all_files_written))

    def load_from_registry(
        self,
        collection: str,
        product_type: str,
        baseline: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[str]:
        """
        Load URLs from registry files.

        Args:
            collection: Collection name
            product_type: Product type
            baseline: Baseline filter (discovers from registry if None)
            start: Optional start datetime filter
            end: Optional end datetime filter

        Raises:
            InvalidRequestError: If start > end

        Returns:
            List of URLs
        """
        # Validate time range
        self._validate_time_range(start, end)

        registry_dir = self._config.registry_dir

        # Discover baselines from registry if not specified
        if baseline:
            baselines = [baseline]
        else:
            base_path = registry_dir / "urls" / self._config.mission / collection / product_type
            if not base_path.exists():
                logger.info(f"No registry files found at {base_path}")
                return []
            baselines = [d.name for d in base_path.iterdir() if d.is_dir()]
            if not baselines:
                logger.info(f"No baseline directories in {base_path}")
                return []
            logger.info(f"Found baselines: {', '.join(sorted(baselines))}")

        # Load URLs from registry files
        all_urls: list[str] = []
        seen: set[str] = set()
        for bl in baselines:
            registry = Registry(
                registry_dir=registry_dir,
                mission=self._config.mission,
                collection=collection,
                product_type=product_type,
                baseline=bl,
            )
            for url in registry.load_urls(start=start, end=end):
                if url not in seen:
                    seen.add(url)
                    all_urls.append(url)

        logger.info(f"Found {len(all_urls)} URLs in registry files")
        return all_urls

    # === HIGH-LEVEL OPERATIONS ===

    def search(
        self,
        collection: str,
        product_type: str,
        baseline: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        orbit: Optional[str] = None,
        use_catalog: bool = False,
        max_items: int = 50000,
        verbose: bool = False,
    ) -> SearchResult:
        """
        Search for product URLs.

        Supports both time-based and orbit-based search (mutually exclusive).
        For time ranges > 10 days, automatically uses day-by-day iteration
        internally for reliability.

        Args:
            collection: Collection name
            product_type: Product type
            baseline: Optional baseline filter (if omitted, searches all baselines)
            start: Start datetime (for time-based search)
            end: End datetime (for time-based search)
            orbit: Orbit+frame string (for orbit-based search, mutually exclusive with start/end)
            use_catalog: Use cached catalog bounds for optimization
            max_items: Maximum items to return
            verbose: Show progress during search

        Raises:
            InvalidRequestError: If orbit is used with start/end, or start > end,
                                or datetimes are not timezone-aware

        Returns:
            SearchResult with urls and metadata
        """
        # Validate parameters
        self._validate_time_range(start, end, orbit)

        # Orbit-based search
        if orbit:
            queryables = self.catalog.load(collection)
            if queryables and not queryables.supports_orbit():
                raise InvalidRequestError(
                    f"Collection '{collection}' does not support orbit search. "
                    f"Use --date or --start/--end instead."
                )
            urls = self.searcher.search_urls_by_orbit(
                collection=collection,
                product_type=product_type,
                orbit_frame=orbit,
                baseline=baseline,
                verbose=verbose,
            )
            # Extract baselines from results
            baselines_found = list(set(
                extract_baseline(os.path.basename(url)) or "UNKNOWN"
                for url in urls
            ))
            return SearchResult(
                urls=urls,
                baselines_found=sorted(baselines_found),
                start=None,
                end=None,
                total_count=len(urls),
            )

        # Time-based search with optional catalog optimization
        search_start = start
        search_end = end

        if use_catalog and baseline:
            info = self.get_baseline_info(collection, product_type, baseline, from_built=True)
            if info:
                cached = info.time_range()
                if cached:
                    logger.info(f"Using cached temporal coverage for {baseline}...")
                    data_start, data_end = cached[0], cached[1]
                    search_start = max(start, data_start) if start else data_start
                    search_end = min(end, data_end) if end else data_end

        urls = self.searcher.search_urls(
            collection=collection,
            product_type=product_type,
            baseline=baseline,
            start=search_start,
            end=search_end,
            max_items=max_items,
            verbose=verbose,
        )

        # Extract baselines from results
        baselines_found = list(set(
            extract_baseline(os.path.basename(url)) or "UNKNOWN"
            for url in urls
        ))

        return SearchResult(
            urls=urls,
            baselines_found=sorted(baselines_found),
            start=search_start,
            end=search_end,
            total_count=len(urls),
        )

    def download(
        self,
        urls: list[str],
        collection: str,
        out_dir: Optional[Path] = None,
        track_state: bool = False,
        skip_existing: bool = True,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> DownloadResult:
        """
        Download files from URLs.

        Extracts product_type and baseline from each URL for structured paths.
        Collection must be provided as it's not in the URL.

        Args:
            urls: List of URLs to download
            collection: Collection name (required, not in URL)
            out_dir: If provided, download to flat directory; otherwise structured paths
            track_state: Track downloads in state files
            skip_existing: Skip files that already exist
            dry_run: Only report what would be downloaded
            verbose: Print progress messages

        Returns:
            DownloadResult with downloaded paths, skipped, errors
        """
        result = DownloadResult()
        start_time = time.time()

        if not urls:
            logger.info("No URLs to download")
            return result

        # Dry run
        if dry_run:
            logger.info(f"Would download {len(urls)} files:")
            for url in urls[:10]:
                logger.info(f"  {url}")
            if len(urls) > 10:
                logger.info(f"  ... and {len(urls) - 10} more")
            result.skipped = urls
            return result

        self._config.ensure_directories()

        # Download to flat directory (--out-dir)
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            downloader = self._get_downloader()
            total_urls = len(urls)

            for i, url in enumerate(urls, 1):
                parsed_url = urlparse(url)
                filename = os.path.basename(parsed_url.path)
                output_path = out_dir / filename

                if skip_existing and output_path.exists():
                    logger.info(f"[{i:>{len(str(total_urls))}}/{total_urls}] Already exists: {filename}")
                    result.skipped.append(url)
                    continue

                try:
                    logger.info(f"[{i:>{len(str(total_urls))}}/{total_urls}] Downloading: {filename}")
                    downloader.download_file(url, output_path)
                    result.downloaded[url] = output_path
                except Exception as e:
                    result.errors.append(f"{url}: {e}")

            result.elapsed_seconds = time.time() - start_time
            logger.info(f"Downloaded {len(result.downloaded)} files")
            return result

        # Download to structured paths (grouped by product/baseline)
        urls_by_key: dict[tuple[str, str], list[str]] = {}
        for url in urls:
            filename = os.path.basename(url)
            product = extract_product(filename)
            baseline = extract_baseline(filename)
            if not product or not baseline:
                result.errors.append(f"Cannot extract product/baseline from {filename}")
                continue
            urls_by_key.setdefault((product, baseline), []).append(url)

        downloader = self._get_downloader()
        for (product, baseline), group_urls in urls_by_key.items():
            try:
                tracker = None
                if track_state:
                    tracker = self.state.get_tracker(collection, product, baseline)
                    tracker.add_urls(group_urls)

                downloaded = downloader.batch_download(
                    urls=group_urls,
                    collection=collection,
                    product_type=product,
                    baseline=baseline,
                    skip_existing=skip_existing,
                    on_download=tracker.mark_downloaded if tracker else None,
                    verbose=verbose,
                )
                result.downloaded.update(downloaded)
            except Exception as e:
                result.errors.append(f"{product}/{baseline}: {e}")

        result.elapsed_seconds = time.time() - start_time
        logger.info(f"Downloaded {len(result.downloaded)} files")
        return result

    def download_from_registry(
        self,
        collection: str,
        product_type: str,
        baseline: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        out_dir: Optional[Path] = None,
        skip_existing: bool = True,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> DownloadResult:
        """
        Download files from registry.

        Always tracks state when downloading from registry.

        Args:
            collection: Collection name
            product_type: Product type
            baseline: Baseline filter (discovers from registry if None)
            start: Optional start datetime filter
            end: Optional end datetime filter
            out_dir: If provided, download to flat directory; otherwise structured paths
            skip_existing: Skip files that already exist
            dry_run: Only report what would be downloaded
            verbose: Print progress messages

        Raises:
            InvalidRequestError: If start > end or datetimes not timezone-aware

        Returns:
            DownloadResult with downloaded paths, skipped, errors
        """
        # Validate time range (done inside load_from_registry)
        urls = self.load_from_registry(
            collection=collection,
            product_type=product_type,
            baseline=baseline,
            start=start,
            end=end,
        )
        return self.download(
            urls=urls,
            collection=collection,
            out_dir=out_dir,
            track_state=True,  # Always track state when downloading from registry
            skip_existing=skip_existing,
            dry_run=dry_run,
            verbose=verbose,
        )

    def get(
        self,
        collection: str,
        product_type: str,
        baseline: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        orbit: Optional[str] = None,
        out_dir: Optional[Path] = None,
        max_items: int = 50000,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> DownloadResult:
        """
        Search + download in one step.

        Convenience method that combines search() and download().

        Args:
            collection: Collection name
            product_type: Product type
            baseline: Optional baseline filter
            start: Start datetime (for time-based search)
            end: End datetime (for time-based search)
            orbit: Orbit+frame string (for orbit-based search)
            out_dir: If provided, download to flat directory; otherwise structured paths
            max_items: Maximum items to get
            dry_run: Only report what would be downloaded
            verbose: Print progress messages

        Raises:
            InvalidRequestError: If orbit is used with start/end, or start > end

        Returns:
            DownloadResult with downloaded paths, skipped, errors
        """
        # Search (validation happens inside search())
        search_result = self.search(
            collection=collection,
            product_type=product_type,
            baseline=baseline,
            start=start,
            end=end,
            orbit=orbit,
            max_items=max_items,
            verbose=verbose,
        )

        # Download
        return self.download(
            urls=search_result.urls,
            collection=collection,
            out_dir=out_dir,
            track_state=False,  # get() doesn't track state by default
            dry_run=dry_run,
            verbose=verbose,
        )

    def sync(
        self,
        collection: str,
        product_type: str,
        baseline: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        max_items: int = 50000,
        verbose: bool = False,
    ) -> SyncResult:
        """
        Incremental sync: search + download + state tracking.

        Loops day-by-day, calling search() for each day, then saving to
        registry and downloading. This provides incremental progress and
        state persistence.

        Default time range: last 3 days if no start/end specified.

        Args:
            collection: Collection name
            product_type: Product type
            baseline: Optional baseline filter (syncs all baselines if None)
            start: Optional start datetime
            end: Optional end datetime (defaults to now)
            max_items: Maximum items to sync
            verbose: Print progress messages

        Raises:
            InvalidRequestError: If start > end or datetimes not timezone-aware

        Returns:
            SyncResult with stats and tracker for post-sync operations
        """
        # Validate time range
        self._validate_time_range(start, end)

        # Default time range: last 3 days
        now = datetime.now(timezone.utc).replace(microsecond=0)
        if start is None and end is None:
            start = now - timedelta(days=3)
            end = now
        elif start and not end:
            end = now

        # Discover baselines if not specified
        if baseline:
            baselines = [baseline]
        else:
            baselines = self.list_baselines(collection, product_type, from_built=False)
            if not baselines:
                logger.warning(f"No baselines found for {collection}/{product_type}")
                return SyncResult(
                    collection=collection,
                    product_type=product_type,
                    baselines=[],
                )
            logger.info(f"Syncing all baselines: {', '.join(b.upper() for b in baselines)}...")

        result = SyncResult(
            collection=collection,
            product_type=product_type,
            baselines=baselines,
        )

        for bl in baselines:
            logger.info(f"Syncing {collection}/{product_type}/{bl.upper()}...")
            logger.info(f"  {to_zulu(start)}")
            logger.info(f"  {to_zulu(end)}")

            # Search day-by-day (use searcher directly)
            urls: list[str] = []
            for day_urls in self.searcher.search_urls_iter_day(
                collection=collection,
                product_type=product_type,
                baseline=bl,
                start=start,
                end=end,
                verbose=verbose,
            ):
                urls.extend(day_urls)

            result.urls_found += len(urls)

            # Get tracker and add URLs
            tracker = self.get_tracker(collection, product_type, bl)
            tracker.add_urls(urls)

            # Filter to pending downloads
            pending = tracker.get_pending_downloads()
            to_download = [url for url in urls if url in pending][:max_items]

            if not to_download:
                logger.info(f"No new files to download for {bl.upper()}")
                continue

            logger.info(f"Found {len(urls)} URLs, {len(pending)} pending, downloading {len(to_download)}")

            # Download with state tracking
            try:
                self._config.ensure_directories()
                downloader = self._get_downloader()
                downloaded = downloader.batch_download(
                    urls=to_download,
                    collection=collection,
                    product_type=product_type,
                    baseline=bl,
                    skip_existing=True,
                    on_download=tracker.mark_downloaded,
                    verbose=verbose,
                )
                result.urls_downloaded += len(downloaded)
                logger.info(f"Downloaded {len(downloaded)} files for {bl.upper()}")
            except Exception as e:
                result.errors.append(f"{bl.upper()}: {e}")
                logger.error(f"Error syncing {bl.upper()}: {e}")

            # Store last tracker for post-sync operations
            result.tracker = tracker

        if len(baselines) > 1:
            logger.info(f"Total downloaded: {result.urls_downloaded} files")

        return result

    def build_catalog(
        self,
        collection: Optional[str] = None,
        product_type: Optional[str] = None,
        baseline: Optional[str] = None,
        latest_baseline: bool = False,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        force: bool = False,
        out_dir: Optional[Path] = None,
        verbose: bool = False,
    ) -> dict[str, Path]:
        """
        Build catalog from API queries.

        Args:
            collection: Collection name (builds all if None)
            product_type: Product type filter
            baseline: Baseline filter
            latest_baseline: Only build for latest baseline
            start: Optional start datetime filter
            end: Optional end datetime filter
            force: Delete existing catalog and rebuild from scratch
            out_dir: Output directory (uses config default if None)
            verbose: Print progress messages

        Raises:
            InvalidRequestError: If start > end or datetimes not timezone-aware

        Returns:
            Dictionary mapping collection name to catalog file path
        """
        # Validate time range
        self._validate_time_range(start, end)

        # Use config's built_catalog_dir if not specified
        catalog_dir = out_dir or self._config.built_catalog_dir

        # Parse filters
        products_filter = [product_type] if product_type else None
        baselines_filter = [baseline] if baseline else None

        # Determine collections to build
        if collection:
            collections = [collection]
        else:
            collections = self.list_collections()
            logger.info(f"Building catalogs for {len(collections)} collections...")

        results: dict[str, Path] = {}

        for coll in collections:
            try:
                logger.info(f"Building catalog for {coll}...")

                if start or end:
                    start_str = to_zulu(start) if start else "..."
                    end_str = to_zulu(end) if end else "..."
                    logger.info(f"  {start_str}")
                    logger.info(f"  {end_str}")

                manager = CatalogCollectionManager(client=self, catalog_dir=catalog_dir)
                catalog = manager.build(
                    collection=coll,
                    products_filter=products_filter,
                    baselines_filter=baselines_filter,
                    latest_baseline=latest_baseline,
                    start=start,
                    end=end,
                    force=force,
                    verbose=verbose,
                )

                path = manager.save(catalog)
                results[coll] = path
                logger.info(f"Wrote catalog to {path}")

                # Summary
                products = catalog.products
                total_products = len(products)
                total_baselines = sum(len(p.baselines) for p in products.values())
                logger.info(f"Summary: {total_products} products, {total_baselines} baselines")

            except Exception as e:
                logger.error(f"Error building {coll}: {e}")

        return results
