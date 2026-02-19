"""STAC search operations for MAAP catalog.

STAC API Behavior Notes
-----------------------
These notes document observed behavior of pystac_client with the MAAP STAC API:

About the "datetime" parameter:
- Accepts both Python datetime objects and ISO 8601 strings ("2024-07-25T00:00:00Z")
- Supports open-ended ranges: (start, None) or (None, end)
- Cannot use (None, None) - at least one bound required
- Using MISSION_START/MISSION_END vs None has no performance difference

Time filtering:
- STAC API filters by item datetime metadata (observational/acquisition time)
- This module post-filters by sensing_time extracted from filenames
- Some items returned by STAC may fall outside requested range based on sensing time

Result ordering:
- STAC API results are not guaranteed to be ordered by sensing time
- To get the first/last granule for a time range, must retrieve all results and sort

Performance:
- The STAC API search time per day increases with range size:
    1-10 days: ~2.6s/day
    30 days: ~3.1s/day
    180 days: ~5.7s/day
- For large ranges, day-by-day searching is ~2x faster than a single API call.

Product-specific:
- AUX_MET_1D: Not searchable by orbit/frame (fields not indexed)
- AUX_MET_1D: Has multiple versions per granule, requires deduplication

Assumptions:
- All MAAP STAC items have enclosure URLs, so matched() reflects downloadable count
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Literal, Optional

from pystac_client import Client

from maap_client.constants import DEFAULT_CATALOG_URL, DEFAULT_MISSION_START, DEFAULT_MISSION_END
from maap_client.paths import (
    extract_sensing_time,
    extract_creation_time,
    extract_baseline,
    extract_info,
    filter_by_sensing_time,
)
from maap_client.types import GranuleInfo
from maap_client.utils import format_time_range, normalize_time_range, parse_datetime, to_stac_datetime

logger = logging.getLogger(__name__)

# Products that require deduplication by (baseline, sensing_time)
DEDUP_PRODUCTS = {"AUX_MET_1D"}

# Products that don't have orbit/frame indexed in STAC metadata
NO_ORBIT_PRODUCTS = {"AUX_MET_1D"}


class MaapSearcher:
    """
    STAC search operations for MAAP catalog.
    """

    def __init__(
        self,
        catalog_url: Optional[str] = None,
        mission_start: Optional[str] = None,
        mission_end: Optional[str] = None,
    ):
        """Initialize MAAP searcher.

        Args:
            catalog_url: STAC catalog URL. Defaults to DEFAULT_CATALOG_URL.
            mission_start: Mission start datetime (ISO 8601). Defaults to DEFAULT_MISSION_START.
            mission_end: Mission end datetime (ISO 8601). Defaults to DEFAULT_MISSION_END.
        """
        self._catalog_url = catalog_url or DEFAULT_CATALOG_URL
        self._mission_start = mission_start or DEFAULT_MISSION_START
        self._mission_end = mission_end or DEFAULT_MISSION_END
        self._client: Optional[Client] = None

    @property
    def client(self) -> Client:
        """Lazy-load STAC client."""
        if self._client is None:
            self._client = Client.open(self._catalog_url)
        return self._client
    
    @staticmethod
    def _iter_day_ranges(
        start: datetime,
        end: datetime,
    ) -> Iterator[tuple[datetime, datetime]]:
        """
        Generate day-by-day time windows for efficient STAC searches.

        Edge cases:
        - First day: uses original start time (may be partial day)
        - Middle days: full day (00:00:00Z to 23:59:59Z)
        - Last day: uses original end time (may be partial day)

        Only yields valid windows where start < end.
        """
        current = start.date()
        end_date = end.date()
        is_first = True

        while current <= end_date:
            if is_first:
                day_start = start
                is_first = False
            else:
                day_start = datetime(
                    current.year, current.month, current.day,  0,  0,  0, tzinfo=timezone.utc)

            if current == end_date:
                day_end = end
            else:
                day_end = datetime(
                    current.year, current.month, current.day, 23, 59, 59, tzinfo=timezone.utc)

            if day_start < day_end:
                yield (day_start, day_end)

            current += timedelta(days=1)

    def _resolve_time_range(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> tuple[datetime, datetime]:
        """
        Normalize and clamp a time range to mission bounds and current time.

        - Defaults start to mission_start, clamps to be >= mission_start
        - Defaults end to min(now, mission_end), clamps to be <= min(now, mission_end)

        Returns:
            Tuple of (clamped_start, clamped_end)
        """
        mission_start = parse_datetime(self._mission_start)
        mission_end = parse_datetime(self._mission_end)
        return normalize_time_range(start, end, mission_start, mission_end)

    @staticmethod
    def _extract_enclosures(search, format: Optional[str] = None) -> list[str]:
        """Extract enclosure URLs from STAC search results.

        Args:
            search: STAC search results
            format: Preferred file format ('h5' or 'hdr'). Defaults to 'h5'.
        """
        if format == "hdr":
            priority = ("enclosure_hdr",)
        else:
            priority = ("enclosure_h5",)

        urls = []
        for item in search.items():
            url = None
            for key in priority:
                if key in item.assets:
                    url = item.assets[key].href
                    break
            else:
                for key in item.assets:
                    if key.startswith("enclosure"):
                        url = item.assets[key].href
                        break
            if url:
                urls.append(url)
        return urls

    @staticmethod
    def _sort_urls(urls: list[str]) -> list[str]:
        """Sort URLs by sensing time."""
        return sorted(urls, key=lambda u: extract_sensing_time(u) or datetime.min)

    @staticmethod
    def _dedup_urls(urls: list[str]) -> list[str]:
        """Deduplicate URLs by (baseline, sensing_time), keeping earliest creation_time."""
        urls_by_key: dict[tuple, tuple[str, datetime]] = {}
        for url in urls:
            baseline = extract_baseline(url)
            sensing_time = extract_sensing_time(url)
            creation_time = extract_creation_time(url)
            if not baseline or not sensing_time or not creation_time:
                logger.warning(f"Skipping URL with missing metadata (baseline={baseline}, sensing_time={sensing_time}, creation_time={creation_time}): {url}")
                continue
            key = (baseline, sensing_time)
            if key not in urls_by_key or creation_time < urls_by_key[key][1]:
                urls_by_key[key] = (url, creation_time)
        return [url for url, _ in urls_by_key.values()]

    def _clean_search_results(
        self,
        search,
        product_type: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        dedup: bool = True,
        format: Optional[str] = None,
    ) -> list[str]:
        """Process STAC search results into sorted, deduplicated URLs.

        Returns:
            List of sorted, deduplicated product URLs
        """
        # Extract enclosure URLs
        urls = self._extract_enclosures(search, format=format)
        # Filter by sensing_time
        urls = filter_by_sensing_time(urls, start, end)
        # Sort by sensing_time
        urls = self._sort_urls(urls)

        # Deduplicate (for DEDUP_PRODUCTS only, if dedup=True)
        if dedup and product_type in DEDUP_PRODUCTS:
            urls = self._dedup_urls(urls)

        return urls

    def search_has_any_product(
        self,
        collection: str,
        product_type: str,
        baseline: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        verbose: bool = False,
    ) -> bool:
        """
        Check if any data exists for product+baseline combination.

        Returns:
            True if at least one item exists
        """
        if verbose:
            logger.info(f"Checking {collection} {product_type}/{baseline}{format_time_range(start, end)}...")

        datetime_arg = (start, end) if start is not None and end is not None else None

        search = self.client.search(
            collections=[collection],
            filter=f"productType = '{product_type}' AND productVersion = '{baseline}'",
            datetime=datetime_arg,
            method="GET",
            max_items=150,
        )

        matched = search.matched()
        if matched is None or matched == 0:
            if verbose:
                logger.info("  not found")
            return False
        if start is None:
            if verbose:
                logger.info("  EXISTS")
            return True

        urls = self._clean_search_results(search, product_type, start, end, dedup=False)
        result = len(urls) >= 1
        if verbose:
            logger.info("  EXISTS" if result else "  not found")
        return result
    
    def search_product_count(
        self,
        collection: str,
        product_type: str,
        baseline: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        verbose: bool = False,
    ) -> int:
        """
        Count matching products without fetching all items.

        Note:
            The initial STAC query filters by datetime metadata. When a time range
            is provided, results are post-filtered by sensing_time and the count
            is adjusted accordingly.

        Returns:
            Number of matching products
        """
        if verbose:
            logger.info(f"Counting {collection} {product_type}/{baseline}{format_time_range(start, end)}...")

        datetime_arg = (start, end) if start is not None and end is not None else None

        search = self.client.search(
            collections=[collection],
            filter=f"productType = '{product_type}' AND productVersion = '{baseline}'",
            datetime=datetime_arg,
            method="GET",
            max_items=150,
        )

        matched = search.matched()
        if matched is None:
            matched = 0
        if verbose:
            logger.info(f"  count: {matched}")
        return matched

    def search_baselines(
        self,
        collection: str,
        product_type: str,
        candidates: Optional[list[str]] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        mode: Literal["all", "latest"] = "all",
        verbose: bool = False,
        catalog_manager: Optional[Any] = None,
    ) -> list[str]:
        """
        Get baselines that actually have data for a product.

        Returns:
            List of baselines that have actual data (sorted alphabetically)
        """
        if candidates is None:
            if catalog_manager is None:
                from maap_client.catalog_query import CatalogQueryablesManager
                catalog_manager = CatalogQueryablesManager()
            queryables = catalog_manager.load(collection, refresh=True)
            candidates = queryables.list_baselines()

        if verbose:
            logger.info(f"Checking {collection} {product_type} baselines ({len(candidates)} candidates){format_time_range(start, end)}")

        existing = []
        for baseline in candidates:
            if self.search_has_any_product(collection, product_type, baseline, start, end):
                existing.append(baseline)
                if verbose:
                    logger.info(f"  {baseline}: EXISTS")
            else:
                if verbose:
                    logger.info(f"  {baseline}: not found")

        # Sort alphabetically (baselines already uppercase from list_baselines)
        existing_sorted = sorted(existing)

        if mode == "latest":
            return [existing_sorted[-1]] if existing_sorted else []
        return existing_sorted

    def search_product_info_range(
        self,
        collection: str,
        product_type: str,
        baseline: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        verbose: bool = False,
    ) -> Optional[tuple[GranuleInfo, GranuleInfo]]:
        """
        Find the first and last granules for a product+baseline.

        Uses binary search to efficiently find first/last days with data,
        then queries for the actual first and last files.

        Returns:
            Tuple of (first_granule, last_granule) if data exists, None otherwise
        """
        if verbose:
            logger.info(f"Finding info range for {collection} {product_type}/{baseline}...")

        t0, t1 = self._resolve_time_range(start, end)

        # Quick exit if no data at all
        if not self.search_has_any_product(collection, product_type, baseline, t0, t1):
            if verbose:
                logger.info("  No data found")
            return None

        # --- Find first day with data (binary search) ---
        lo, hi = t0, t1
        first_day = None

        while lo.date() <= hi.date():
            mid_day = (lo + (hi - lo) / 2).date()
            mid_end = datetime(
                mid_day.year, mid_day.month, mid_day.day, 23, 59, 59, tzinfo=timezone.utc
            )
            if self.search_has_any_product(collection, product_type, baseline, t0, mid_end):
                first_day = mid_day
                hi = datetime(
                    mid_day.year, mid_day.month, mid_day.day, 0, 0, 0, tzinfo=timezone.utc
                ) - timedelta(days=1)
            else:
                lo = datetime(
                    mid_day.year, mid_day.month, mid_day.day, tzinfo=timezone.utc
                ) + timedelta(days=1)

        # --- Find last day with data (binary search) ---
        lo, hi = t0, t1
        last_day = None

        while lo.date() <= hi.date():
            mid_day = (lo + (hi - lo) / 2).date()
            mid_start = datetime(mid_day.year, mid_day.month, mid_day.day, tzinfo=timezone.utc)
            if self.search_has_any_product(collection, product_type, baseline, mid_start, t1):
                last_day = mid_day
                lo = datetime(
                    mid_day.year, mid_day.month, mid_day.day, 0, 0, 0, tzinfo=timezone.utc
                ) + timedelta(days=1)
            else:
                hi = datetime(
                    mid_day.year, mid_day.month, mid_day.day, 0, 0, 0, tzinfo=timezone.utc
                ) - timedelta(days=1)

        if first_day is None or last_day is None:
            return None

        # --- Get first and last granule info ---
        ini_day_start = datetime(
            first_day.year, first_day.month, first_day.day,  0,  0,  0, tzinfo=timezone.utc)
        ini_day_end = datetime(
            first_day.year, first_day.month, first_day.day, 23, 59, 59, tzinfo=timezone.utc)
        end_day_start = datetime(
            last_day.year, last_day.month, last_day.day,  0,  0,  0, tzinfo=timezone.utc)
        end_day_end = datetime(
            last_day.year, last_day.month, last_day.day, 23, 59, 59, tzinfo=timezone.utc)
        
        first_day_urls = self.search_urls(
            collection, product_type, baseline, ini_day_start, ini_day_end)
        last_day_urls = self.search_urls(
            collection, product_type, baseline, end_day_start, end_day_end)

        if not first_day_urls or not last_day_urls:
            return None

        first_granule = GranuleInfo(**extract_info(first_day_urls[0]))
        last_granule = GranuleInfo(**extract_info(last_day_urls[-1]))

        return (first_granule, last_granule)

    def search_urls(
        self,
        collection: str,
        product_type: str,
        baseline: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        max_items: int = 50000,
        verbose: bool = False,
        format: Optional[str] = None,
    ) -> list[str]:
        """
        Search for download URLs for matching products.

        Uses day-by-day searching internally for reliability with time-bounded queries.
        For incremental processing or progress display, use search_urls_iter_day() instead.

        Returns:
            List of product URLs
        """
        start, end = self._resolve_time_range(start, end)

        period_days = (end - start).days

        # Single API call for short ranges (≤10 days)
        if period_days <= 10:
            if verbose:
                bl_str = f"/{baseline}" if baseline else ""
                logger.info(f"Searching {collection} {product_type}{bl_str}{format_time_range(start, end)}...")
            filter_parts = [f"productType = '{product_type}'"]
            if baseline:
                filter_parts.append(f"productVersion = '{baseline}'")
            filter_str = " AND ".join(filter_parts)
            datetime_arg = (start, end)
            search = self.client.search(
                collections=[collection],
                filter=filter_str,
                filter_lang="cql2-text",
                datetime=datetime_arg,
                method="GET",
                max_items=max_items,
            )
            urls = self._clean_search_results(search, product_type, start, end, format=format)
            if verbose:
                logger.info(f"  found {len(urls)}")

        # Day-by-day for large ranges (more efficient)
        else:
            urls = []
            for day_urls in self.search_urls_iter_day(
                collection=collection,
                product_type=product_type,
                start=start,
                end=end,
                baseline=baseline,
                max_items=max_items,
                verbose=verbose,
                format=format,
            ):
                urls.extend(day_urls)
            if verbose:
                logger.info(f"Total: {len(urls)} URLs")

        return urls

    def search_urls_by_orbit(
        self,
        collection: str,
        product_type: str,
        orbit_frame: str,
        baseline: Optional[str] = None,
        max_items: int = 100,
        verbose: bool = False,
        format: Optional[str] = None,
    ) -> list[str]:
        """
        Search for product URLs by orbit number and frame.

        Returns:
            List of product URLs matching the orbit+frame
        """
        # Check if product supports orbit/frame search
        if product_type in NO_ORBIT_PRODUCTS:
            logger.warning(
                f"{product_type} does not have orbit/frame metadata indexed. "
                f"Use --date or --start/--end instead."
            )
            return []

        orbit_frame = orbit_frame.strip().upper()
        frame = orbit_frame[-1]
        orbit_str = orbit_frame[:-1]

        if verbose:
            bl_str = f"/{baseline}" if baseline else ""
            logger.info(f"Searching {collection} {product_type}{bl_str} orbit {orbit_frame}...")

        filter_parts = [
            f"productType = '{product_type}'",
            f"orbitNumber = {int(orbit_str)}",
            f"frame = '{frame}'",
        ]
        if baseline:
            filter_parts.append(f"productVersion = '{baseline}'")

        filter_str = " AND ".join(filter_parts)
        logger.debug(f"Searching with filter: {filter_str}")

        search = self.client.search(
            collections=[collection],
            filter=filter_str,
            filter_lang="cql2-text",
            method="GET",
            max_items=max_items,
        )

        urls = self._clean_search_results(search, product_type, format=format)
        if verbose:
            logger.info(f"  found {len(urls)}")
        return urls

    def search_urls_iter_day(
        self,
        collection: str,
        product_type: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        baseline: Optional[str] = None,
        max_items: int = 50000,
        verbose: bool = False,
        format: Optional[str] = None,
    ) -> Iterator[list[str]]:
        """
        Generator that searches day-by-day over a time range.

        This approach is more reliable for large date ranges and allows
        incremental processing of results.

        Start/end are clamped to mission bounds using _resolve_time_range.

        Yields:
            List of URLs for each day in the range
        """
        start, end = self._resolve_time_range(start, end)
        total_days = (end.date() - start.date()).days + 1

        for i, (day_start, day_end) in enumerate(self._iter_day_ranges(start, end)):
            datetime_arg = to_stac_datetime(day_start, day_end)
            filter_parts = [f"productType = '{product_type}'"]
            if baseline:
                filter_parts.append(f"productVersion = '{baseline}'")
            filter_str = " AND ".join(filter_parts)
            search = self.client.search(
                collections=[collection],
                filter=filter_str,
                filter_lang="cql2-text",
                datetime=datetime_arg,
                method="GET",
                max_items=max_items,
            )
            urls = self._clean_search_results(search, product_type, day_start, day_end, format=format)

            if verbose:
                # Show baselines found by extracting from results
                if baseline:
                    bl_str = f"({baseline.upper()})"
                elif urls:
                    baselines_found = sorted(set(
                        extract_baseline(os.path.basename(url)) or "?"
                        for url in urls
                    ))
                    bl_str = f"({', '.join(baselines_found)})"
                else:
                    bl_str = ""
                start_str = day_start.strftime("%Y-%m-%dT%H:%M:%SZ")
                end_str = day_end.strftime("%Y-%m-%dT%H:%M:%SZ")
                width = len(str(total_days))
                logger.info(f"[{i+1:{width}d}/{total_days}] {start_str} -> {end_str}... found {len(urls)} {bl_str}")

            yield urls
