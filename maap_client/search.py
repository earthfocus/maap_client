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
- For large ranges, day-by-day searching is ~2x faster than a single API call
  for dense products; a sparse product (at most one item per day on average,
  from a numberMatched count of ~0.5s) is fetched in one paged search instead.

Product-specific rules (types not indexed by orbit, deduplicated versions,
types without baseline) are declared by each mission in maap_client.missions.

Assumptions:
- All MAAP STAC items have enclosure URLs, so matched() reflects downloadable count
"""

import json
import logging
import os
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterator, Literal, Mapping, Optional, Sequence

from pystac_client import Client
from pystac_client.exceptions import APIError
from pystac_client.stac_api_io import StacApiIO
from urllib3.util.retry import Retry

from maap_client.constants import (
    DEFAULT_CATALOG_URL,
    DEFAULT_MISSION,
    DEFAULT_MISSION_START,
    DEFAULT_MISSION_END,
    NO_BASELINE,
    STAC_RETRY_ALLOWED_METHODS,
    STAC_RETRY_BACKOFF_FACTOR,
    STAC_RETRY_STATUS_FORCELIST,
    STAC_RETRY_TOTAL,
)
from maap_client.exceptions import AuthenticationError, CredentialsError, InvalidRequestError
from maap_client.missions import get_mission
from maap_client.filters import filter_by_sensing_time, sort_by_sensing_time
from maap_client.paths import (
    extract_baseline,
    extract_info,
    parse_with_baseline,
)
from maap_client.types import GranuleInfo
from maap_client.utils import (
    format_time_range,
    normalize_baseline,
    normalize_format,
    normalize_time_range,
    parse_datetime,
    to_stac_datetime,
)

logger = logging.getLogger(__name__)

# How many skipped item ids the missing-format warning lists.
MISSING_FORMAT_IDS_SHOWN = 5


def select_asset_urls(assets: Mapping[str, str], formats: Sequence[str]) -> list[str]:
    """Pick the asset hrefs of one STAC item for a format priority list.

    The first token of formats that matches anything wins: 'zip' selects the
    'product' asset, 'all' every 'enclosure_*' asset, any other token every
    'enclosure_*' asset whose href extension equals it (case-insensitive).
    There is no fallback to another file: no match returns [].

    Args:
        assets: Asset key -> href of the item.
        formats: Format tokens in priority order.
    """
    enclosures = [href for key, href in assets.items() if key.startswith("enclosure")]
    for token in formats:
        if token == "zip":
            selected = [assets["product"]] if "product" in assets else []
        elif token == "all":
            selected = enclosures
        else:
            selected = [
                h for h in enclosures if os.path.splitext(h)[1].lstrip(".").lower() == token
            ]
        if selected:
            return selected
    return []


@contextmanager
def _rejected_as_invalid() -> Iterator[None]:
    """
    Turn a search MAAP rejects (HTTP 400, e.g. an unknown collection) into an
    InvalidRequestError carrying the server's message; retrying cannot help.
    """
    try:
        yield
    except APIError as e:
        if e.status_code != 400:
            raise
        try:
            message = json.loads(str(e))["error"]["message"]
        except (ValueError, KeyError, TypeError):
            message = str(e)
        raise InvalidRequestError(f"MAAP rejected the search: {message}") from e


class LoggingRetry(Retry):
    """urllib3 Retry that logs each attempt.

    Status-based retries are otherwise only visible at DEBUG level, so
    users never see that 502/503/429 responses are being retried.
    """

    def increment(self, method=None, url=None, response=None, error=None,
                  _pool=None, _stacktrace=None):
        new_retry = super().increment(
            method=method, url=url, response=response, error=error,
            _pool=_pool, _stacktrace=_stacktrace,
        )
        cause = f"HTTP {response.status}" if response is not None else repr(error)
        remaining = new_retry.total if new_retry.total is not None else 0
        attempt = STAC_RETRY_TOTAL - remaining
        logger.warning(f"STAC retry {attempt}/{STAC_RETRY_TOTAL} after {cause}: {url}")
        return new_retry


class MaapSearcher:
    """
    STAC search operations for MAAP catalog.
    """

    def __init__(
        self,
        catalog_url: Optional[str] = None,
        mission_start: Optional[str] = None,
        mission_end: Optional[str] = None,
        default_formats: Optional[tuple[str, ...]] = None,
        mission: str = DEFAULT_MISSION,
    ):
        """Initialize MAAP searcher.

        Args:
            catalog_url: STAC catalog URL. Defaults to DEFAULT_CATALOG_URL.
                Normalized to end in a slash, since MAAP answers the slashless
                root with a load-balancer 503.
            mission_start: Mission start datetime (ISO 8601). Defaults to DEFAULT_MISSION_START.
            mission_end: Mission end datetime (ISO 8601). Defaults to DEFAULT_MISSION_END.
            default_formats: Format priority list used when a search gives no explicit format.
                Defaults to the mission's default_formats.
            mission: Name of the mission searched (its products without orbit metadata).
        """
        self._mission = get_mission(mission)
        self._default_formats = default_formats or self._mission.default_formats
        self._catalog_url = (catalog_url or DEFAULT_CATALOG_URL).rstrip("/") + "/"
        self._mission_start = mission_start or DEFAULT_MISSION_START
        self._mission_end = mission_end or DEFAULT_MISSION_END
        self._client: Optional[Client] = None
        # Days skipped by the last day-by-day search, as (date, error) tuples.
        self.last_failed_days: list[tuple[date, str]] = []
        # Ids of items skipped by the last search because no asset matched the format.
        self.last_missing_format: list[str] = []

    @property
    def client(self) -> Client:
        """Lazy-load STAC client with transport-level retries for transient errors."""
        if self._client is None:
            retry = LoggingRetry(
                total=STAC_RETRY_TOTAL,
                backoff_factor=STAC_RETRY_BACKOFF_FACTOR,
                status_forcelist=list(STAC_RETRY_STATUS_FORCELIST),
                allowed_methods=list(STAC_RETRY_ALLOWED_METHODS),
            )
            self._client = Client.open(
                self._catalog_url, stac_io=StacApiIO(max_retries=retry)
            )
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

    def _formats(self, format: Optional[str]) -> tuple[str, ...]:
        """Format priority list for a search.

        The explicit format alone, else the mission default.
        """
        if format:
            return (normalize_format(format),)
        return self._default_formats

    def _extract_enclosures(self, search, format: Optional[str] = None) -> list[str]:
        """Extract the asset URLs selected by the format from STAC search results.

        Items with no asset matching the format are skipped and recorded in
        last_missing_format.
        """
        formats = self._formats(format)
        urls = []
        with _rejected_as_invalid():
            for item in search.items():
                assets = {key: asset.href for key, asset in item.assets.items()}
                selected = select_asset_urls(assets, formats)
                if selected:
                    urls.extend(selected)
                else:
                    self.last_missing_format.append(item.id)
        return urls

    def _warn_missing_format(self) -> None:
        """Log one warning summarising the items skipped by the last search."""
        if not self.last_missing_format:
            return
        shown = ", ".join(self.last_missing_format[:MISSING_FORMAT_IDS_SHOWN])
        more = len(self.last_missing_format) - MISSING_FORMAT_IDS_SHOWN
        suffix = f", ... (+{more} more)" if more > 0 else ""
        logger.warning(
            f"Skipped {len(self.last_missing_format)} item(s) with no asset in the requested "
            f"format: {shown}{suffix}"
        )

    @staticmethod
    def _build_filter(
        product_type: str,
        baseline: Optional[str] = None,
        orbit: Optional[int] = None,
        extra: Optional[dict[str, list[str]]] = None,
    ) -> str:
        """
        Build a CQL2-text filter string for MAAP STAC searches.

        extra maps mission queryables to accepted values; names with a
        namespace (``eofeos:repeat_cycle_id``) are double-quoted. NO_BASELINE
        adds no productVersion clause (those items have no version), so a
        NO_BASELINE count or existence check matches every item of the type:
        this assumes the types a mission declares without baseline never carry
        a version (verified on the fixture items, see no_baseline_products).
        """
        parts = [f"productType = '{product_type}'"]
        if baseline and normalize_baseline(baseline) != NO_BASELINE:
            parts.append(f"productVersion = '{baseline}'")
        if orbit is not None:
            parts.append(f"orbitNumber = {orbit}")
        for queryable, values in (extra or {}).items():
            if not values:
                continue
            name = f'"{queryable}"' if ":" in queryable else queryable
            if len(values) == 1:
                parts.append(f"{name} = '{values[0]}'")
            else:
                value_list = ", ".join(f"'{v}'" for v in values)
                parts.append(f"{name} IN ({value_list})")
        return " AND ".join(parts)

    def _clean_search_results(
        self,
        search,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        format: Optional[str] = None,
        baseline: Optional[str] = None,
    ) -> list[str]:
        """Process STAC search results into sorted URLs.

        With baseline NO_BASELINE only URLs whose parsed baseline is
        NO_BASELINE are kept (the query has no productVersion clause).

        Returns:
            List of sorted product URLs
        """
        # Extract enclosure URLs
        urls = self._extract_enclosures(search, format=format)
        if normalize_baseline(baseline) == NO_BASELINE:
            urls = [url for url in urls if extract_baseline(url) == NO_BASELINE]
        # Filter by sensing_time
        urls = filter_by_sensing_time(urls, start, end)
        # Sort by sensing_time
        urls = sort_by_sensing_time(urls)

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
            filter=self._build_filter(product_type, baseline=baseline),
            datetime=datetime_arg,
            method="GET",
            max_items=150,
        )

        with _rejected_as_invalid():
            matched = search.matched()
        if matched is None or matched == 0:
            if verbose:
                logger.info("  not found")
            return False
        if start is None:
            if verbose:
                logger.info("  EXISTS")
            return True

        self.last_missing_format = []
        urls = self._clean_search_results(search, start, end, baseline=baseline)
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
            Returns the server's ``numberMatched`` for the STAC ``datetime``
            metadata window. No post-filtering by filename sensing_time is
            done (that would require fetching every item), so with a time
            range the count may differ slightly at the window edges from
            sensing_time-filtered results, and it includes items whose
            filenames cannot be parsed.

        Returns:
            Number of matching products (0 if the server reports none)
        """
        if verbose:
            logger.info(f"Counting {collection} {product_type}/{baseline}{format_time_range(start, end)}...")

        matched = self._matched(
            collection, self._build_filter(product_type, baseline=baseline), start, end
        )
        if verbose:
            logger.info(f"  count: {matched}")
        return matched

    def _matched(
        self, collection: str, filter_str: str, start: Optional[datetime], end: Optional[datetime]
    ) -> int:
        """The server's numberMatched for a filter and datetime window (one request), 0 if none."""
        datetime_arg = (start, end) if start is not None and end is not None else None
        search = self.client.search(
            collections=[collection],
            filter=filter_str,
            datetime=datetime_arg,
            method="GET",
            max_items=150,
        )
        with _rejected_as_invalid():
            return search.matched() or 0

    def search_baselines(
        self,
        collection: str,
        product_type: str,
        candidates: list[str],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        mode: Literal["all", "latest"] = "all",
        verbose: bool = False,
    ) -> list[str]:
        """
        Get the candidate baselines (e.g. the collection's queryable
        versions) that actually have data for a product.

        Returns:
            List of baselines that have actual data (sorted alphabetically)
        """
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

        # The catalog groups items by baseline: an unreadable one is an error.
        for url in (first_day_urls[0], last_day_urls[-1]):
            parse_with_baseline(url)
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
        reverse: bool = False,
        on_day: Optional[Callable[[list[str]], None]] = None,
        extra: Optional[dict[str, list[str]]] = None,
    ) -> list[str]:
        """
        Search for download URLs for matching products.

        Ranges over 10 days are searched day by day, for reliability, unless
        the product is sparse there: a count (one fast request) of at most one
        item per day on average fetches the whole range in one paged search.
        For incremental processing or progress display, use search_urls_iter_day() instead.

        Args:
            reverse: If True, return URLs sorted newest-first by sensing time.
            on_day: Called with each day's URLs as found (day-by-day path only).
                Durability hook for incremental persistence.
            extra: Mission queryables -> accepted values (see _build_filter).

        Returns:
            List of product URLs
        """
        self.last_failed_days = []
        self.last_missing_format = []
        start, end = self._resolve_time_range(start, end)

        period_days = (end - start).days
        filter_str = self._build_filter(product_type, baseline=baseline, extra=extra)

        # Single API call for short ranges (≤10 days) and sparse products
        if period_days <= 10 or self._matched(collection, filter_str, start, end) <= period_days:
            if verbose:
                bl_str = f"/{baseline}" if baseline else ""
                logger.info(f"Searching {collection} {product_type}{bl_str}{format_time_range(start, end)}...")
            datetime_arg = (start, end)
            search = self.client.search(
                collections=[collection],
                filter=filter_str,
                filter_lang="cql2-text",
                datetime=datetime_arg,
                method="GET",
                max_items=max_items,
            )
            urls = self._clean_search_results(search, start, end, format=format, baseline=baseline)
            if verbose:
                logger.info(f"  found {len(urls)}")
            self._warn_missing_format()

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
                reverse=reverse,
                extra=extra,
            ):
                day_urls = day_urls[: max_items - len(urls)]
                urls.extend(day_urls)
                if on_day and day_urls:
                    on_day(day_urls)
                if len(urls) >= max_items:
                    break
            if verbose:
                logger.info(f"Total: {len(urls)} URLs")

        urls = sort_by_sensing_time(urls, reverse=reverse)

        return urls

    def search_urls_by_orbit(
        self,
        collection: str,
        product_type: str,
        orbit: int,
        baseline: Optional[str] = None,
        max_items: int = 100,
        verbose: bool = False,
        format: Optional[str] = None,
        extra: Optional[dict[str, list[str]]] = None,
    ) -> list[str]:
        """
        Search for product URLs by orbit number, optionally restricted by
        mission queryables (e.g. EarthCARE frames).

        Args:
            orbit: Absolute orbit number (e.g. 1525)
            extra: Mission queryables -> accepted values (see _build_filter).

        Returns:
            List of product URLs matching the orbit (and extra, if given)
        """
        # Check if product supports orbit/frame search
        if product_type in self._mission.no_orbit_products:
            logger.warning(
                f"{product_type} does not have orbit/frame metadata indexed. "
                f"Use --date or --start/--end instead."
            )
            return []

        if verbose:
            bl_str = f"/{baseline}" if baseline else ""
            extra_str = "".join(
                f" {name} {','.join(values)}" for name, values in (extra or {}).items()
            )
            logger.info(
                f"Searching {collection} {product_type}{bl_str} orbit {orbit}{extra_str}..."
            )

        filter_str = self._build_filter(product_type, baseline=baseline, orbit=orbit, extra=extra)
        logger.debug(f"Searching with filter: {filter_str}")

        search = self.client.search(
            collections=[collection],
            filter=filter_str,
            filter_lang="cql2-text",
            method="GET",
            max_items=max_items,
        )

        self.last_missing_format = []
        urls = self._clean_search_results(search, format=format, baseline=baseline)
        self._warn_missing_format()
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
        reverse: bool = False,
        extra: Optional[dict[str, list[str]]] = None,
    ) -> Iterator[list[str]]:
        """
        Generator that searches day-by-day over a time range.

        This approach is more reliable for large date ranges and allows
        incremental processing of results.

        Start/end are clamped to mission bounds using _resolve_time_range.

        Args:
            reverse: If True, iterate days from end to start (newest first).
            extra: Mission queryables -> accepted values (see _build_filter).

        Yields:
            List of URLs for each day in the range
        """
        start, end = self._resolve_time_range(start, end)
        self.last_failed_days = []
        self.last_missing_format = []
        failed_ranges: list[tuple[datetime, datetime]] = []
        total_days = (end.date() - start.date()).days + 1

        day_ranges = list(self._iter_day_ranges(start, end))
        if reverse:
            day_ranges.reverse()
        for i, (day_start, day_end) in enumerate(day_ranges):
            datetime_arg = to_stac_datetime(day_start, day_end)
            filter_str = self._build_filter(
                product_type, baseline=baseline, extra=extra
            )
            try:
                search = self.client.search(
                    collections=[collection],
                    filter=filter_str,
                    filter_lang="cql2-text",
                    datetime=datetime_arg,
                    method="GET",
                    max_items=max_items,
                )
                urls = self._clean_search_results(
                    search, day_start, day_end, format=format, baseline=baseline
                )
            except (AuthenticationError, CredentialsError, InvalidRequestError):
                raise
            except Exception as e:
                # Transport retries are exhausted: skip the day, keep the range.
                logger.warning(f"FAILED DAY {day_start.date().isoformat()}: {e}")
                failed_ranges.append((day_start, day_end))
                self.last_failed_days.append((day_start.date(), str(e)))
                continue

            if verbose:
                # Show baselines found by extracting from results
                if baseline:
                    bl_str = f"({baseline.upper()})"
                elif urls:
                    baselines_found = sorted(set(
                        extract_baseline(url) or "?"
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

        # Second pass: retry each failed day once. By the time a long range
        # finishes, transient blips have usually passed; only days failing
        # both passes are reported.
        if failed_ranges:
            logger.info(f"Retrying {len(failed_ranges)} failed day(s)...")
            self.last_failed_days = []
            for day_start, day_end in failed_ranges:
                datetime_arg = to_stac_datetime(day_start, day_end)
                filter_str = self._build_filter(
                    product_type, baseline=baseline, extra=extra
                )
                try:
                    search = self.client.search(
                        collections=[collection],
                        filter=filter_str,
                        filter_lang="cql2-text",
                        datetime=datetime_arg,
                        method="GET",
                        max_items=max_items,
                    )
                    urls = self._clean_search_results(
                        search, day_start, day_end, format=format, baseline=baseline
                    )
                except (AuthenticationError, CredentialsError, InvalidRequestError):
                    raise
                except Exception as e:
                    logger.warning(f"FAILED DAY (retry) {day_start.date().isoformat()}: {e}")
                    self.last_failed_days.append((day_start.date(), str(e)))
                    continue
                logger.info(f"Recovered day {day_start.date().isoformat()}")
                yield urls

        self._warn_missing_format()
