"""Catalog queryables for MAAP API."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import requests

from maap_client.catalog import Catalog, CatalogManager
from maap_client.constants import DEFAULT_CATALOG_URL, DEFAULT_COLLECTIONS, DEFAULT_CATALOG_DIR, DEFAULT_TIMEOUT
from maap_client.exceptions import CatalogError

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
        prop = self.properties.get("productType", {})
        return prop.get("enum", []) if isinstance(prop, dict) else prop

    def list_baselines(self) -> list[str]:
        """List baseline versions from queryables (uppercase)."""
        prop = self.properties.get("productVersion", {})
        baselines = prop.get("enum", []) if isinstance(prop, dict) else prop
        return sorted([b.upper() for b in baselines])

    def supports_orbit(self) -> bool:
        """Check if collection supports orbit-based search."""
        return "orbitNumber" in self.properties


class CatalogQueryablesManager(CatalogManager):
    """Manages catalog queryables download and parsing."""

    FILENAME_PATTERN = "{collection}_queryables.json"
    DEFAULT_DIR = Path(DEFAULT_CATALOG_DIR).expanduser()
    CATALOG_CLASS = CatalogQueryables

    def __init__(
        self,
        catalog_url: str = DEFAULT_CATALOG_URL,
        catalog_dir: Optional[Path] = None,
    ):
        """
        Initialize catalog manager.

        Args:
            catalog_url: Base URL for MAAP catalog
            catalog_dir: Directory for storing queryables JSON files
        """
        super().__init__(catalog_dir)
        self._catalog_url = catalog_url.rstrip("/")

    def fetch(self, collection: str) -> dict[str, Any]:
        """Fetch raw queryables JSON schema directly from MAAP STAC API."""
        url = f"{self._catalog_url}/collections/{collection}/queryables"

        try:
            r = requests.get(url, timeout=DEFAULT_TIMEOUT)
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
        """Download queryables for collections."""
        if collections is None:
            collections = DEFAULT_COLLECTIONS

        results = {}

        for collection in collections:
            path = self.get_path(collection)

            if path.exists() and not force:
                logger.debug(f"[SKIP] {collection} already exists: {path}")
                results[collection] = path
                continue

            data = self.fetch(collection)
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
        for collection in DEFAULT_COLLECTIONS:
            if self.get_path(collection).exists():
                downloaded.append(collection)
        return downloaded
