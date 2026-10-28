"""MaapClient facade for ESA MAAP satellite data access."""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from pathlib import Path
from typing import Callable, Optional

from maap_client.auth import load_credentials, TokenManager
from maap_client.catalog_build import BaselineInfo, CatalogCollectionManager
from maap_client.catalog_query import CatalogQueryablesManager
from maap_client.config import MaapConfig
from maap_client.download import DownloadManager
from maap_client.exceptions import (
    AuthenticationError,
    BatchDownloadAborted,
    CredentialsError,
    InvalidRequestError,
)
from maap_client.filters import (
    filter_by_fields,
    filter_by_orbit_frame,
    merge_frames,
    resolve_filters,
    sort_by_sensing_time,
    validate_time_range,
)
from maap_client.search import MaapSearcher
from maap_client.tracker import GlobalStateTracker, StateTracker
from maap_client.missions import Mission, get_mission, mission_for_filename, parse_product
from maap_client.paths import (
    extract_baseline,
    is_zip_url,
    local_relpath,
    url_to_local_path,
)
from maap_client.registry import Registry
from maap_client.types import DownloadResult, SearchResult, SyncResult
from maap_client.utils import normalize_time_range as _normalize_time_range
from maap_client.utils import normalize_format, parse_datetime, to_zulu

logger = logging.getLogger(__name__)


class MaapClient:
    """
    High-level client for ESA MAAP satellite data access (EarthCARE, Aeolus,
    Biomass, FLEX); one instance serves the mission its config is set to.

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
        self._state: Optional[GlobalStateTracker] = None

    @property
    def config(self) -> MaapConfig:
        """Get current configuration."""
        return self._config

    @property
    def mission(self) -> Mission:
        """Profile of the configured mission."""
        return get_mission(self._config.mission)

    @property
    def catalog(self) -> CatalogQueryablesManager:
        """Get catalog manager (lazy initialization)."""
        if self._catalog is None:
            self._catalog = CatalogQueryablesManager(
                catalog_url=self._config.catalog_url,
                catalog_dir=self._config.catalog_dir,
                collections=self.list_collections(),
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
                default_formats=self._config.default_formats,
                mission=self._config.mission,
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

    def _get_downloader(self, product_dir: bool = False) -> DownloadManager:
        """Get download manager."""
        return DownloadManager(
            token_manager=self._get_token_manager(),
            data_dir=self._config.data_dir,
            mission=self._config.mission,
            product_dir=product_dir,
        )

    # === VALIDATION ===

    @staticmethod
    def _product_dir_error(mission: Mission) -> InvalidRequestError:
        return InvalidRequestError(
            f"{mission.name} individual files need --product-dir: names repeat across and within products"
        )

    def _check_product_dir_format(
        self, product_type: str, format: Optional[str], product_dir: bool
    ) -> None:
        """
        Reject individual files that need product_dir, before any search.

        The configured mission's files need it when it declares
        files_need_product_dir and product_type is not one of its
        single_file_products. The effective format is the explicit one, else
        the configured default list; anything but ``zip`` selects individual
        files.

        Raises:
            InvalidRequestError: Individual files that need product_dir, without it
        """
        mission = self.mission
        if product_dir or not mission.files_need_product_dir:
            return
        if product_type in mission.single_file_products:
            return
        formats = (normalize_format(format),) if format else self._config.default_formats
        if any(f != "zip" for f in formats):
            raise self._product_dir_error(mission)

    @staticmethod
    def _needs_product_dir(url: str) -> Optional[Mission]:
        """
        The URL's mission when the URL is an individual file that needs
        product_dir (see Mission.files_need_product_dir), else None. A product
        type that cannot be read from the URL needs it; a zip never does.
        """
        mission = mission_for_filename(url)
        if mission is None or not mission.files_need_product_dir or is_zip_url(url):
            return None
        if mission.parse(url).product_type in mission.single_file_products:
            return None
        return mission

    def _check_download_layout(
        self,
        urls: list[str],
        product_dir: bool,
        collection: str,
        out_dir: Optional[Path] = None,
    ) -> None:
        """
        Reject a batch whose files cannot each get their own local path.

        Individual files of a mission that declares files_need_product_dir
        need product_dir (their names repeat across and within products),
        unless their product type is one of its single_file_products; a zip
        does not. As a defensive check, two different URLs mapping to one
        local path fail the run instead of one of them being skipped as
        already downloaded.

        Raises:
            InvalidRequestError: On an individual file that needs product_dir
                without it, a URL with unsafe path segments (``..``), or two
                different URLs sharing a local path
        """
        if not product_dir:
            for url in urls:
                if mission := self._needs_product_dir(url):
                    raise self._product_dir_error(mission)

        seen: dict[Path, str] = {}
        for url in dict.fromkeys(urls):
            try:
                relpath = local_relpath(url, product_dir)
            except ValueError as e:
                raise InvalidRequestError(str(e)) from e
            if out_dir:
                path = out_dir / relpath
            else:
                path = url_to_local_path(
                    url, self._config.data_dir, self._config.mission, collection, product_dir
                )
            if path is None:
                continue
            if path in seen:
                raise InvalidRequestError(
                    f"Two URLs map to the same local path {path}: {seen[path]} and {url}"
                )
            seen[path] = url

    def _resolve_filters(
        self,
        orbit: Optional[str],
        frames: Optional[list[str]],
        filters: Optional[dict[str, list]],
        registry: bool = False,
    ) -> tuple[Optional[int], Optional[list[str]], Optional[dict[str, list[str]]]]:
        """
        Validate orbit and filters with filters.resolve_filters; ``frames`` is
        an alias of ``filters["frame"]``.

        Returns:
            (orbit number, frame letters of orbits, other filters): on missions
            with orbit_frame_letter the "frame" filter is returned apart, for
            the searcher's frames and the offline orbit/frame filter.
        """
        if not (orbit or frames or filters):
            return None, None, None
        orbit_num, resolved = resolve_filters(self.mission, orbit, merge_frames(frames, filters), registry)
        letters = resolved.pop("frame", None) if self.mission.orbit_frame_letter else None
        return orbit_num, letters, resolved or None

    def _queryables(self, filters: Optional[dict[str, list[str]]]) -> Optional[dict[str, list[str]]]:
        """Map resolved filters (option -> values) to STAC queryables -> values."""
        if not filters:
            return None
        return {spec.queryable: filters[spec.option] for spec in self.mission.filters if spec.option in filters}

    # === CATALOG OPERATIONS ===

    def update_catalogs(
        self,
        collections: Optional[list[str]] = None,
        force: bool = False,
        out_dir: Optional[Path] = None,
        failures_out: Optional[list[tuple[str, str]]] = None,
    ) -> dict[str, Path]:
        """
        Download/update catalog queryables.

        Collections default to the configured mission's. failures_out, if given,
        is appended with (collection, error) for each collection that failed.
        """
        self._config.ensure_directories()
        if out_dir:
            manager = CatalogQueryablesManager(
                catalog_url=self._config.catalog_url,
                catalog_dir=out_dir,
                collections=self.list_collections(),
            )
        else:
            manager = self.catalog
        results = manager.download(collections, force)
        if failures_out is not None:
            failures_out.extend(manager.last_failures)
        return results

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

        Note:
            ``count`` comes from the server's ``numberMatched`` (STAC
            ``datetime`` metadata), while ``time_*``/``frame_*`` come from
            filename sensing times — the two can disagree slightly at range
            edges.

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
            # parsed from the URL: Aeolus, Biomass and FLEX file names do not
            # all carry the baseline
            bl = extract_baseline(url) or "UNKNOWN"
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
        validate_time_range(start, end)

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
        format: Optional[str] = None,
        reverse: bool = False,
        frames: Optional[list[str]] = None,
        on_day: Optional[Callable[[list[str]], None]] = None,
        filters: Optional[dict[str, list[str]]] = None,
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
            orbit: Orbit+frame string (for orbit-based search, mutually exclusive with start/end).
                  Accepts either '1525' (orbit only, combine with frames) or '01525E'
                  (orbit+frame combined; frames must not also be given).
            use_catalog: Use cached catalog bounds for optimization
            max_items: Maximum items to return
            verbose: Show progress during search
            format: 'zip', 'all' or a file extension (default: the mission's format priority list)
            frames: Alias of filters['frame'] (e.g. EarthCARE frame letters; works
                   for both time-based and orbit-based search); if orbit already
                   includes a frame letter, frames must be omitted
            on_day: Called with each day's URLs as found (day-by-day path only).
                   Durability hook for incremental persistence.
            filters: Mission filters, option -> values, str or int, alone or in
                   a list (e.g. Biomass {'track': [2], 'repeat_cycle': '1'});
                   see Mission.filters and filters.resolve_filters

        Raises:
            InvalidRequestError: If orbit is used with start/end, or start > end,
                                or datetimes are not timezone-aware, or orbit already
                                includes a frame letter while frames is also given,
                                or a filter is not one of the mission's

        Returns:
            SearchResult with urls and metadata
        """
        # Validate parameters
        validate_time_range(start, end, orbit)
        orbit_num, resolved_frames, filters = self._resolve_filters(orbit, frames, filters)
        extra = self._queryables(filters)

        # Orbit-based search
        if orbit_num is not None:
            queryables = self.catalog.load(collection)
            if queryables and not queryables.supports_orbit():
                raise InvalidRequestError(
                    f"Collection '{collection}' does not support orbit search. "
                    f"Use --date or --start/--end instead."
                )
            urls = self.searcher.search_urls_by_orbit(
                collection=collection,
                product_type=product_type,
                orbit=orbit_num,
                frames=resolved_frames,
                baseline=baseline,
                max_items=max_items,
                verbose=verbose,
                format=format,
                extra=extra,
            )
            if reverse:
                urls = sort_by_sensing_time(urls, reverse=True)
            # Extract baselines from results
            baselines_found = list(set(
                extract_baseline(url) or "UNKNOWN"
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
            format=format,
            reverse=reverse,
            frames=resolved_frames,
            on_day=on_day,
            extra=extra,
        )

        # Extract baselines from results
        baselines_found = list(set(
            extract_baseline(url) or "UNKNOWN"
            for url in urls
        ))

        return SearchResult(
            urls=urls,
            baselines_found=sorted(baselines_found),
            start=search_start,
            end=search_end,
            total_count=len(urls),
            failed_days=list(self.searcher.last_failed_days),
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
        product_dir: bool = False,
        reverse: bool = False,
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
            product_dir: If True, place each file inside a folder named after its product

        Raises:
            InvalidRequestError: On individual files that need product_dir (e.g.
                                Biomass) without it, or two different URLs
                                sharing a local path

        Returns:
            DownloadResult with downloaded paths, skipped, errors
        """
        result = DownloadResult()
        start_time = time.time()

        if not urls:
            logger.info("No URLs to download")
            return result

        self._check_download_layout(urls, product_dir, collection, out_dir)

        if reverse:
            urls = sort_by_sensing_time(urls, reverse=True)

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
            downloader = self._get_downloader(product_dir=product_dir)
            total_urls = len(urls)

            for i, url in enumerate(urls, 1):
                parsed_url = urlparse(url)
                filename = os.path.basename(parsed_url.path)
                output_path = out_dir / local_relpath(url, product_dir)

                if skip_existing and output_path.exists():
                    logger.info(f"[{i:>{len(str(total_urls))}}/{total_urls}] Already exists: {filename}")
                    result.skipped.append(url)
                    continue

                try:
                    logger.info(f"[{i:>{len(str(total_urls))}}/{total_urls}] Downloading: {filename}")
                    downloader.download_file(url, output_path)
                    result.downloaded[url] = output_path
                except (AuthenticationError, CredentialsError):
                    # Auth failures doom every remaining download identically:
                    # propagate so callers can classify.
                    raise
                except Exception as e:
                    result.errors.append(f"{url}: {e}")

            result.elapsed_seconds = time.time() - start_time
            logger.info(f"Downloaded {len(result.downloaded)} files")
            return result

        # Download to structured paths (grouped by product/baseline)
        urls_by_key: dict[tuple[str, str], list[str]] = {}
        for url in urls:
            filename = os.path.basename(url)
            # parsed from the URL: Aeolus keeps the baseline in the path, and
            # Biomass internal files are not named after their product
            parsed = parse_product(url)
            product = parsed.product_type if parsed else None
            baseline = parsed.baseline if parsed else None
            if not product or not baseline:
                result.permanent_errors.append(f"cannot parse product/baseline from {filename}")
                continue
            if parsed.sensing_time is None:
                # batch_download would silently skip it; a retry cannot fix the name.
                result.permanent_errors.append(f"cannot parse filename (no sensing time): {filename}")
                continue
            urls_by_key.setdefault((product, baseline), []).append(url)

        downloader = self._get_downloader(product_dir=product_dir)
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
                # batch_download's mapping includes successes and skipped
                # files; anything absent failed and must reach the caller.
                for u in group_urls:
                    if u not in downloaded:
                        result.errors.append(f"{u}: download failed")
            except (AuthenticationError, CredentialsError):
                # Auth failures doom every remaining download identically:
                # propagate so callers can classify.
                raise
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
        product_dir: bool = False,
        reverse: bool = False,
        orbit: Optional[str] = None,
        frames: Optional[list[str]] = None,
        filters: Optional[dict[str, list[str]]] = None,
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
            orbit: Optional orbit spec to filter registry URLs by ('1525' or
                  '01525E'); if it already includes a frame letter, frames must
                  be omitted
            frames: Optional frame letters to filter registry URLs by
            filters: Mission filters (option -> values) matched against the
                  product names of the registry URLs

        Raises:
            InvalidRequestError: If start > end, datetimes not timezone-aware, or
                                orbit already includes a frame letter while frames
                                is also given, or orbit is given for a mission whose
                                names carry no absolute orbit, or a filter is not one
                                of the mission's or cannot be read from the names

        Returns:
            DownloadResult with downloaded paths, skipped, errors
        """
        orbit_num, resolved_frames, filters = self._resolve_filters(orbit, frames, filters, registry=True)
        # Validate time range (done inside load_from_registry)
        urls = self.load_from_registry(
            collection=collection,
            product_type=product_type,
            baseline=baseline,
            start=start,
            end=end,
        )
        if orbit_num is not None and self.mission.orbit_offline == "some":
            # Names that carry the orbit only sometimes (Aeolus L0/L1 ms
            # timestamps): reject the others instead of silently dropping them.
            # With "all" orbit-less names (EarthCARE AUX_CC*, AUX_ORBPRE,
            # MPL_ORBSCT) are dropped by filter_by_orbit_frame.
            orbitless = sorted({
                parsed.product_type or parsed.product
                for parsed in map(self.mission.parse, urls)
                if parsed.orbit_frame is None
            })
            if orbitless:
                raise InvalidRequestError(
                    f"Cannot filter by orbit offline: the product names of {', '.join(orbitless)} "
                    f"do not carry the orbit; use search instead"
                )
        if orbit_num is not None or resolved_frames:
            total = len(urls)
            urls = filter_by_orbit_frame(urls, orbit=orbit_num, frames=resolved_frames)
            logger.info(f"{len(urls)} of {total} registry URLs match the orbit/frame filter")
        if filters:
            total = len(urls)
            try:
                urls = filter_by_fields(urls, filters, self.mission)
            except ValueError as e:
                raise InvalidRequestError(str(e)) from e
            logger.info(f"{len(urls)} of {total} registry URLs match the {', '.join(filters)} filter")
        return self.download(
            urls=urls,
            collection=collection,
            out_dir=out_dir,
            track_state=True,  # Always track state when downloading from registry
            skip_existing=skip_existing,
            dry_run=dry_run,
            verbose=verbose,
            product_dir=product_dir,
            reverse=reverse,
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
        format: Optional[str] = None,
        product_dir: bool = False,
        reverse: bool = False,
        frames: Optional[list[str]] = None,
        filters: Optional[dict[str, list[str]]] = None,
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
            orbit: Orbit+frame string (for orbit-based search). Accepts either
                  '1525' (combine with frames) or '01525E' (frame included;
                  frames must not also be given).
            out_dir: If provided, download to flat directory; otherwise structured paths
            max_items: Maximum items to get
            dry_run: Only report what would be downloaded
            verbose: Print progress messages
            format: 'zip', 'all' or a file extension (default: the mission's format priority list)
            frames: Optional frame letters to restrict the search to
            filters: Mission filters, option -> values (see search())

        Raises:
            InvalidRequestError: If orbit is used with start/end, or start > end,
                                or orbit already includes a frame letter while
                                frames is also given, or a filter is not one of
                                the mission's, or individual files that need
                                product_dir (e.g. Biomass) are asked for
                                without it (before any search)

        Returns:
            DownloadResult with downloaded paths, skipped, errors
        """
        self._check_product_dir_format(product_type, format, product_dir)

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
            format=format,
            reverse=reverse,
            frames=frames,
            filters=filters,
        )

        # Download (URLs are already ordered by search; no need to sort again)
        result = self.download(
            urls=search_result.urls,
            collection=collection,
            out_dir=out_dir,
            track_state=False,  # get() doesn't track state by default
            dry_run=dry_run,
            verbose=verbose,
            product_dir=product_dir,
        )
        result.failed_days = search_result.failed_days
        return result

    def sync(
        self,
        collection: str,
        product_type: str,
        baseline: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        max_items: int = 50000,
        verbose: bool = False,
        format: Optional[str] = None,
        product_dir: bool = False,
        reverse: bool = False,
        frames: Optional[list[str]] = None,
        max_consecutive_failures: Optional[int] = None,
        filters: Optional[dict[str, list[str]]] = None,
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
            format: 'zip', 'all' or a file extension (default: the mission's format priority list)
            frames: Optional frame letters to restrict the sync to (state is
                   per-URL, so filtered syncs are safe)
            max_consecutive_failures: Forwarded to batch_download; abort a baseline's batch after this many consecutive failures (None = never).
            filters: Mission filters, option -> values (see search()); state is
                   per-URL, so filtered syncs are safe

        Raises:
            InvalidRequestError: If start > end or datetimes not timezone-aware,
                                or a filter is not one of the mission's, or
                                individual files that need product_dir (e.g.
                                Biomass) are asked for without it (before any
                                search)

        Returns:
            SyncResult with stats and tracker for post-sync operations
        """
        # Validate time range
        validate_time_range(start, end)
        self._check_product_dir_format(product_type, format, product_dir)
        _, frames, filters = self._resolve_filters(None, frames, filters)
        extra = self._queryables(filters)

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

            try:
                tracker = self.get_tracker(collection, product_type, bl)
                result.tracker = tracker

                # Search day-by-day, registering each day as it is found so
                # a later failure never loses discovered URLs.
                urls: list[str] = []
                for day_urls in self.searcher.search_urls_iter_day(
                    collection=collection,
                    product_type=product_type,
                    baseline=bl,
                    start=start,
                    end=end,
                    verbose=verbose,
                    format=format,
                    reverse=reverse,
                    frames=frames,
                    extra=extra,
                ):
                    if day_urls:
                        tracker.add_urls(day_urls)
                        urls.extend(day_urls)

                for failed_day, err in self.searcher.last_failed_days:
                    result.failed_days.append((bl, failed_day, err))

                result.urls_found += len(urls)

                # Filter to pending downloads. Scoped to the sync range: the
                # result is identical (to_download intersects with this run's
                # URLs, all inside the range) but the read stays off registry
                # files a concurrent same-product worker may be appending to.
                pending = tracker.get_pending_downloads(start, end)
                to_download = [url for url in urls if url in pending][:max_items]

                if not to_download:
                    logger.info(f"No new files to download for {bl.upper()}")
                    continue

                logger.info(f"Found {len(urls)} URLs, {len(pending)} pending, downloading {len(to_download)}")

                self._check_download_layout(to_download, product_dir, collection)

                # Download with state tracking
                self._config.ensure_directories()
                downloader = self._get_downloader(product_dir=product_dir)
                downloaded = downloader.batch_download(
                    urls=to_download,
                    collection=collection,
                    product_type=product_type,
                    baseline=bl,
                    skip_existing=True,
                    on_download=tracker.mark_downloaded,
                    verbose=verbose,
                    max_consecutive_failures=max_consecutive_failures,
                )
                result.urls_downloaded += len(downloaded)

                # batch_download's mapping includes successes and skipped
                # files; anything absent failed and must reach the caller.
                for url in to_download:
                    if url not in downloaded:
                        result.errors.append(f"{url}: download failed")

                logger.info(f"Downloaded {len(downloaded)} files for {bl.upper()}")
            except (AuthenticationError, CredentialsError, BatchDownloadAborted, InvalidRequestError):
                # Auth failures doom every remaining baseline identically, an
                # abort was explicitly requested by the caller, and a rejected
                # layout is the same for every baseline: propagate so callers
                # can classify instead of parsing stringified errors.
                raise
            except Exception as e:
                result.errors.append(f"{bl.upper()}: {e}")
                logger.error(f"Error syncing {bl.upper()}: {e}")

        if len(baselines) > 1:
            logger.info(f"Total downloaded: {result.urls_downloaded} files")

        return result

    def build_catalog(
        self,
        collection: Optional[str] = None,
        product_type: Optional[str] = None,
        baseline: Optional[str] = None,
        latest_baseline: bool = False,
        force: bool = False,
        out_dir: Optional[Path] = None,
        verbose: bool = False,
        failures_out: Optional[list[tuple[str, str, str, str]]] = None,
    ) -> dict[str, Path]:
        """
        Build catalog from API queries.

        Args:
            collection: Collection name (builds all if None)
            product_type: Product type filter
            baseline: Baseline filter
            latest_baseline: Only build for latest baseline
            force: Delete existing catalog and rebuild from scratch
            out_dir: Output directory (uses config default if None)
            verbose: Print progress messages
            failures_out: Optional caller-provided list; appended with
                (collection, product, baseline, error) for every baseline
                that failed after retries. A whole-collection error appends
                (collection, "*", "*", error).

        Returns:
            Dictionary mapping collection name to catalog file path
        """
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

                manager = CatalogCollectionManager(client=self, catalog_dir=catalog_dir)
                catalog = manager.build(
                    collection=coll,
                    products_filter=products_filter,
                    baselines_filter=baselines_filter,
                    latest_baseline=latest_baseline,
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

                if failures_out is not None:
                    failures_out.extend(
                        (coll, prod, bl, err) for prod, bl, err in manager.last_failures
                    )

            except Exception as e:
                logger.error(f"Error building {coll}: {e}")
                if failures_out is not None:
                    failures_out.append((coll, "*", "*", str(e)))

        return results
