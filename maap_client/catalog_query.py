"""Catalog queryables for MAAP API."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import requests

from maap_client.catalog import Catalog, CatalogManager
from maap_client.constants import (
    DEFAULT_CATALOG_DIR,
    DEFAULT_CATALOG_URL,
    DEFAULT_COLLECTIONS,
    DEFAULT_TIMEOUT,
)
from maap_client.exceptions import CatalogError, InvalidRequestError

logger = logging.getLogger(__name__)


class CatalogQueryables(Catalog):
    """Queryables catalog with collection and properties."""

    SORT_KEYS = False
    DEDUPE_STR_LISTS = True

    def __init__(
        self,
        collection: str = "",
        properties: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.collection = collection
        self.properties = properties or {}

    def list_products(self) -> list[str]:
        """List product types from queryables."""
        prop = self.properties.get("product:type", {})
        return prop.get("enum", []) if isinstance(prop, dict) else prop

    def list_baselines(self) -> list[str]:
        """List baseline versions from queryables (uppercase)."""
        prop = self.properties.get("version", {})
        baselines = prop.get("enum", []) if isinstance(prop, dict) else prop
        return sorted([b.upper() for b in baselines])

    def supports(self, queryable: str) -> bool:
        """Check if the collection declares a queryable, e.g. ``sat:orbit_state``."""
        return queryable in self.properties


class CatalogQueryablesManager(CatalogManager):
    """Manages catalog queryables download and parsing."""

    FILENAME_PATTERN = "{collection}_queryables.json"
    DEFAULT_DIR = Path(DEFAULT_CATALOG_DIR).expanduser()
    CATALOG_CLASS = CatalogQueryables

    def __init__(
        self,
        catalog_url: str = DEFAULT_CATALOG_URL,
        catalog_dir: Optional[Path] = None,
        collections: Optional[list[str]] = None,
    ):
        """
        Initialize catalog manager.

        Args:
            catalog_url: Base URL for MAAP catalog
            catalog_dir: Directory for storing queryables JSON files
            collections: Collections of download (when given none) and
                list_downloaded (default: DEFAULT_COLLECTIONS, the default
                mission's; MaapClient passes its configured mission's)
        """
        super().__init__(catalog_dir)
        self._catalog_url = catalog_url.rstrip("/")
        self.collections = list(collections) if collections is not None else list(DEFAULT_COLLECTIONS)
        self.last_failures: list[tuple[str, Exception]] = []

    def fetch(self, collection: str) -> dict[str, Any]:
        """
        Fetch raw queryables JSON schema directly from MAAP STAC API.

        MAAP has no queryables (404) for a collection without searchable
        items yet: that gives an empty schema (no products).

        Raises:
            InvalidRequestError: If MAAP does not know the collection
            CatalogError: If the queryables cannot be fetched
        """
        url = f"{self._catalog_url}/collections/{collection}"

        try:
            r = requests.get(f"{url}/queryables", timeout=DEFAULT_TIMEOUT)
            if r.status_code == 404:
                if requests.get(url, timeout=DEFAULT_TIMEOUT).status_code == 404:
                    raise InvalidRequestError(f"Unknown collection: {collection}")
                logger.info(f"{collection}: no searchable items yet")
                return {"properties": {}}
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            logger.error(f"[FAIL] {collection}: {e}")
            raise CatalogError(f"Failed to fetch queryables for {collection}: {e}")

    def download(
        self,
        collections: Optional[list[str]] = None,
        force: bool = False,
    ) -> dict[str, Path]:
        """
        Download queryables for collections.

        A collection whose queryables cannot be fetched is logged and recorded in
        ``self.last_failures`` as (collection, exception); the others are still
        downloaded. So is a collection MAAP does not know when collections is
        None (all of them); one given explicitly raises.

        Raises:
            InvalidRequestError: If an explicitly given collection is unknown to MAAP
        """
        explicit = collections is not None
        if collections is None:
            collections = self.collections

        self.last_failures = []
        results = {}

        for collection in collections:
            path = self.get_path(collection)

            if path.exists() and not force:
                logger.debug(f"[SKIP] {collection} already exists: {path}")
                results[collection] = path
                continue

            try:
                data = self.fetch(collection)
            except InvalidRequestError as e:
                if explicit:
                    raise
                logger.error(f"[FAIL] {e}")
                self.last_failures.append((collection, e))
                continue
            except CatalogError as e:
                self.last_failures.append((collection, e))
                continue
            catalog = CatalogQueryables.from_dict(data)
            catalog.collection = collection
            results[collection] = self.save(catalog)
            logger.info(f"[OK] {collection} -> {results[collection]}")

        return results

    def load(
        self,
        collection: str,
        refresh: bool = False,
    ) -> Optional[CatalogQueryables]:
        """
        Load queryables with optional refresh from API.

        Auto-fetches from API on first use and saves to disk for future sessions.

        Args:
            collection: Collection name
            refresh: If True, fetch from API even if cached
        """
        # Try cache and disk (unless refresh requested)
        if not refresh:
            catalog = super().load(collection)
            if catalog:
                catalog.collection = collection
                return catalog

        # Fetch from API
        data = self.fetch(collection)
        catalog = CatalogQueryables.from_dict(data)
        catalog.collection = collection

        self.save(catalog)
        self._cache[collection] = catalog
        return catalog

    def list_downloaded(self) -> list[str]:
        """List collections that have local queryables files."""
        downloaded = []
        for collection in self.collections:
            if self.get_path(collection).exists():
                downloaded.append(collection)
        return downloaded
