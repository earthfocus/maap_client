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

    def build(
        self,
        collection: str,
        products_filter: Optional[list[str]] = None,
        baselines_filter: Optional[list[str]] = None,
        latest_baseline: bool = False,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
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
            start: Optional start datetime for filtering which baselines to update
            end: Optional end datetime for filtering which baselines to update
            force: If True, delete existing catalog and rebuild from scratch
            verbose: Print progress messages

        Returns:
            The built/updated CatalogCollection

        Note:
            If start/end are specified, the catalog performs incremental updates:
            - New catalog: fetches metadata only for the specified range
            - Existing catalog: extends range if start < time_start or end > time_end,
              filling gaps and merging counts. Skips if range already covered.
        """
        now = to_zulu(datetime.now(timezone.utc))

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

                existing = product_info.get_baseline(baseline)
                ex_range = existing.time_range() if existing else None

                # Use mission boundaries for None values
                effective_start, effective_end = self._client.normalize_time_range(start, end)

                # Build list of (start, end, updates_start) ranges to fetch
                # updates_start: True=before, False=after, None=full (update both)
                to_fetch: list[tuple[Optional[datetime], Optional[datetime], Optional[bool]]] = []
                if ex_range:
                    t0, t1 = ex_range
                    if effective_start and effective_start < t0:
                        to_fetch.append((effective_start, t0 - timedelta(seconds=1), True))
                    if effective_end and effective_end > t1:
                        to_fetch.append((t1 + timedelta(seconds=1), effective_end, False))
                    if not to_fetch:
                        if verbose:
                            logger.info("    SKIP (already in catalog)")
                        continue
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
                        start_str = to_zulu(f_start) if f_start else "..."
                        end_str = to_zulu(f_end) if f_end else "..."
                        logger.info(f"    Fetching : {start_str} - {end_str}")

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

                if new_count > 0:
                    total = (existing.count if existing else 0) + new_count
                    product_info.set_baseline(baseline, BaselineInfo(
                        **result, count=total, updated_at=now,
                    ))
                    if verbose:
                        msg = f"added {new_count}, total={total}" if existing else f"count={total}"
                        logger.info(f"    OK ({msg})")
                elif verbose:
                    logger.info("    SKIP (no data)")

        return catalog
