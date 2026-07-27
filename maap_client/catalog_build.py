"""Build per-collection metadata catalogs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, cast
import logging

from maap_client.catalog import Catalog, CatalogManager
from maap_client.constants import __version__, DEFAULT_BUILT_CATALOG_DIR
from maap_client.utils import parse_datetime, to_zulu


logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"


class ProductInfo(Catalog):
    """Per-product entry holding baselines (typed so Catalog.from_dict can recurse)."""

    SORT_KEYS = False
    DEDUPE_STR_LISTS = True
    SORT_NESTED_KEYS = ["baselines"]  # Sort baselines dict

    def __init__(
        self,
        baselines: Optional[dict[str, "BaselineInfo"]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.baselines = {} if baselines is None else baselines

    def get_baseline(self, name: str) -> Optional["BaselineInfo"]:
        """Return baseline info by name."""
        return self.baselines.get(name)

    def set_baseline(self, name: str, info: "BaselineInfo") -> None:
        """Set/update baseline info."""
        self.baselines[name] = info

    def list_baselines(self) -> list[str]:
        """List baseline names (sorted)."""
        return sorted(self.baselines.keys())
    

class BaselineInfo(Catalog):
    """Baseline info summary."""

    SORT_KEYS = False
    DEDUPE_STR_LISTS = True

    def __init__(
        self,
        time_start: Optional[datetime] = None,
        time_end: Optional[datetime] = None,
        frame_start: Optional[str] = None,
        frame_end: Optional[str] = None,
        count: int = 0,
        updated_at: Optional[datetime] = None,
        # periods: Optional[list[Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        self.time_start = time_start
        self.time_end = time_end
        self.frame_start = frame_start
        self.frame_end = frame_end
        self.count = count
        self.updated_at = updated_at
        # self.periods = [] if periods is None else periods

    def time_range(self) -> Optional[tuple[datetime, datetime]]:
        if self.time_start is None or self.time_end is None:
            return None

        start = parse_datetime(self.time_start) if isinstance(self.time_start, str) else self.time_start
        end = parse_datetime(self.time_end) if isinstance(self.time_end, str) else self.time_end
        return (start, end)

    def to_dict(
        self,
        sort_keys: bool | None = None,
        dedupe_str_lists: bool | None = None,
    ) -> dict[str, Any]:
        """Convert to dict, excluding null frame values."""
        d = super().to_dict(sort_keys=sort_keys, dedupe_str_lists=dedupe_str_lists)
        # Remove null frame values (Aeolus doesn't have orbit frames)
        if d.get("frame_start") is None:
            del d["frame_start"]
        if d.get("frame_end") is None:
            del d["frame_end"]
        return d


class CatalogCollection(Catalog):
    """Complete catalog for a collection with product metadata."""

    SORT_KEYS = False  # Preserve insertion order for top-level keys
    SORT_NESTED_KEYS = ["products", "baselines"]  # Sort these nested dicts

    def __init__(
        self,
        collection: str = "",
        schema: str = SCHEMA_VERSION,
        generated_at: Optional[str] = None,
        client: Optional[dict[str, str]] = None,
        products: Optional[dict[str, ProductInfo]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.schema = schema
        self.generated_at = generated_at
        self.collection = collection
        self.client = client or {}
        self.products = products or {}

    def get_product(self, name: str) -> Optional[ProductInfo]:
        if not isinstance(self.products, dict):
            return None
        p = self.products.get(name)
        return cast(Optional[ProductInfo], p) if isinstance(p, ProductInfo) else None

    def set_product(self, name: str, info: ProductInfo) -> None:
        if not isinstance(self.products, dict):
            self.products = {}
        self.products[name] = info

    def list_products(self) -> list[str]:
        return sorted(self.products.keys()) if isinstance(self.products, dict) else []


class CatalogCollectionManager(CatalogManager):
    """Manages catalog collection building, saving, and loading."""

    FILENAME_PATTERN = "{collection}_collection.json"
    DEFAULT_DIR = Path(DEFAULT_BUILT_CATALOG_DIR).expanduser()
    CATALOG_CLASS = CatalogCollection

    def __init__(
        self,
        client: Any,
        catalog_dir: Optional[Path] = None,
    ):
        """
        Initialize catalog collection manager.

        Args:
            client: MaapClient instance for API operations
            catalog_dir: Directory for storing collection catalog JSON files
        """
        super().__init__(catalog_dir)
        self._client = client
        self.last_failures: list[tuple[str, str, str]] = []

    def build(
        self,
        collection: str,
        products_filter: Optional[list[str]] = None,
        baselines_filter: Optional[list[str]] = None,
        latest_baseline: bool = False,
        force: bool = False,
        verbose: bool = False,
    ) -> CatalogCollection:
        """
        Build or update a catalog for a collection.

        Args:
            collection: Collection name
            products_filter: Optional list of product names to include (if None, include all)
            baselines_filter: Optional list of baseline names to include (if None, include all)
            latest_baseline: If True, only update the latest baseline per product
            force: If True, delete existing catalog and rebuild from scratch
            verbose: Print progress messages

        Returns:
            The built/updated CatalogCollection

        Note:
            The catalog always represents the full mission time range. Each
            pass fetches only the uncovered gap windows (mission start ->
            time_start and time_end -> now) to update the time/frame edges,
            then re-counts the baseline against the server's total matched
            (no time filter), so counts self-heal when reprocessing inserts
            granules inside the already-covered range. A recount of 0 for a
            baseline with existing data is treated as a transient failure
            and never overwrites the entry. The catalog is checkpointed to
            disk after every baseline that changes, so previously fetched
            work survives crashes. A baseline whose fetch fails (after
            transport retries) is skipped and recorded in
            ``self.last_failures`` as a (product, baseline, error) tuple,
            and the build continues. Use force=True only to rebuild from
            scratch (stale edges after server-side granule deletions).
        """
        now = to_zulu(datetime.now(timezone.utc))
        self.last_failures = []

        # Delete existing catalog if force rebuild
        if force:
            catalog_path = self.get_path(collection)
            if catalog_path.exists():
                if verbose:
                    logger.info(f"Removing existing catalog: {catalog_path}")
                catalog_path.unlink()

        # Load existing catalog if it exists
        existing_catalog = self.load(collection)

        # Create new catalog or update existing
        if existing_catalog:
            catalog = existing_catalog
            catalog.generated_at = now
        else:
            catalog = CatalogCollection(
                collection=collection,
                schema=SCHEMA_VERSION,
                generated_at=now,
                client={
                    "name": "maap_client",
                    "version": __version__,
                },
                products={},
            )

        # Get all products for the collection (queryables)
        products = self._client.list_products(collection, from_built=False, verify=False)

        # Apply products filter if specified
        if products_filter:
            products = [p for p in products if p in products_filter]

        for product in products:
            if verbose:
                logger.info(f"Processing {product}...")

            # Get all baselines from queryables (without verification - we'll verify during metadata fetch)
            all_baselines = self._client.list_baselines(collection, product, from_built=False, verify=False)

            # Get or create product entry
            product_info = catalog.get_product(product)
            if product_info is None:
                product_info = ProductInfo()
                catalog.set_product(product, product_info)

            # Determine which baselines to update
            if baselines_filter:
                # Use specified baselines only (case-insensitive comparison)
                filter_upper = [f.upper() for f in baselines_filter]
                baselines_to_update = [b for b in all_baselines if b.upper() in filter_upper]
           
            # Note that new baselines added to queryables won't be picked up with
            # --latest-baseline until a full rebuild 
            # "update the latest baseline I already know about"
            elif latest_baseline:
                existing_baselines = product_info.list_baselines()
                if existing_baselines:
                    # Use existing catalog baselines, pick alphabetically latest
                    baselines_to_update = [existing_baselines[-1]]
                else:
                    # No existing catalog - get verified baselines and pick the last one (alphabetically latest)
                    verified_baselines = self._client.list_baselines(collection, product, from_built=False, verify=True)
                    if verified_baselines:
                        # Already sorted
                        # baselines_to_update = [sorted(verified_baselines)[-1]]
                        baselines_to_update = [verified_baselines[-1]]
                    else:
                        baselines_to_update = []
            else:
                baselines_to_update = all_baselines

            # Iterate on baselines to update
            for baseline in baselines_to_update:
                if verbose:
                    logger.info(f"  Checking {baseline}...")

                try:
                    existing = product_info.get_baseline(baseline)
                    ex_range = existing.time_range() if existing else None

                    # Use mission boundaries (full mission range)
                    effective_start, effective_end = self._client.normalize_time_range(None, None)

                    # Build list of (start, end, updates_start) ranges to fetch
                    # updates_start: True=before, False=after, None=full (update both)
                    to_fetch: list[tuple[datetime, datetime, Optional[bool]]] = []
                    if ex_range:
                        t0, t1 = ex_range
                        if effective_start < t0:
                            to_fetch.append((effective_start, t0 - timedelta(seconds=1), True))
                        if effective_end > t1:
                            to_fetch.append((t1 + timedelta(seconds=1), effective_end, False))
                    else:
                        to_fetch.append((effective_start, effective_end, None))  # Full fetch

                    # Fetch ranges and merge results
                    new_count = 0
                    result = dict(
                        time_start=existing.time_start if existing else None,
                        time_end=existing.time_end if existing else None,
                        frame_start=existing.frame_start if existing else None,
                        frame_end=existing.frame_end if existing else None,
                    )
                    for f_start, f_end, updates_start in to_fetch:
                        # Log the time range being fetched
                        if verbose:
                            logger.info(f"    Fetching : {to_zulu(f_start)} - {to_zulu(f_end)}")

                        if not self._client.searcher.search_has_any_product(
                            collection, product, baseline, f_start, f_end
                        ):
                            continue
                        info = self._client.get_baseline_info(
                            collection, product, baseline, f_start, f_end, from_built=False
                        )
                        if info:
                            new_count += info.count
                            if updates_start is None or updates_start:  # full or before
                                result["time_start"] = info.time_start
                                result["frame_start"] = info.frame_start
                            if updates_start is None or not updates_start:  # full or after
                                result["time_end"] = info.time_end
                                result["frame_end"] = info.frame_end

                    # Authoritative recount: the server's total matched for
                    # productType+productVersion, no time filter. Skipped for
                    # queryables baselines with no entry and no data (saves a
                    # request; behavior identical to before).
                    recount = 0
                    if existing is not None or new_count > 0:
                        # search_product_count maps a missing numberMatched to 0,
                        # so recount is always an int.
                        recount = self._client.searcher.search_product_count(
                            collection, product, baseline
                        )
                except Exception as e:
                    # Transport retries are exhausted by now: record and move on
                    # so one bad baseline doesn't discard the rest of the pass.
                    logger.warning(f"    FAILED ({product}/{baseline}): {e}")
                    self.last_failures.append((product, baseline, str(e)))
                    continue

                if existing is not None and recount == 0:
                    # A transiently-empty matched must never wipe the catalog.
                    logger.warning(
                        f"    RECOUNT returned 0 for {product}/{baseline} "
                        f"with existing data; keeping catalog entry"
                    )
                    self.last_failures.append(
                        (product, baseline, "recount returned 0 with existing data")
                    )
                    continue

                count = recount if recount > 0 else new_count
                if count == 0:
                    if verbose:
                        logger.info("    SKIP (no data)")
                    continue
                if recount == 0:
                    # New baseline whose windows saw data but the recount says
                    # 0: keep the window sum this pass.
                    logger.warning(
                        f"    RECOUNT returned 0 for {product}/{baseline}; "
                        f"using window count {new_count}"
                    )

                changed = (
                    existing is None
                    or existing.count != count
                    or existing.time_start != result["time_start"]
                    or existing.time_end != result["time_end"]
                    or existing.frame_start != result["frame_start"]
                    or existing.frame_end != result["frame_end"]
                )
                if not changed:
                    if verbose:
                        logger.info("    SKIP (no change)")
                    continue

                product_info.set_baseline(baseline, BaselineInfo(
                    **result, count=count, updated_at=now,
                ))
                # Checkpoint: persist progress so a later failure never
                # discards baselines already fetched in this run.
                self.save(catalog)
                if verbose:
                    if existing is None:
                        logger.info(f"    OK (count={count})")
                    elif new_count > 0:
                        logger.info(f"    OK (added {new_count}, count={count})")
                    else:
                        logger.info(
                            f"    count adjusted {existing.count} -> {count} "
                            f"(in-range backfill)"
                        )

        return catalog
