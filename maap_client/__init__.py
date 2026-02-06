"""MAAP Client - ESA MAAP data access."""

import logging

# Library-friendly logging: prevents "No handler found" warnings when used as a library
logging.getLogger("maap_client").addHandler(logging.NullHandler())

from maap_client.catalog import Catalog
from maap_client.catalog_build import BaselineInfo
from maap_client.client import MaapClient
from maap_client.config import MaapConfig
from maap_client.constants import DEFAULT_COLLECTIONS, __version__
from maap_client.exceptions import (
    AuthenticationError,
    InvalidRequestError,
    MaapError,
)
from maap_client.types import DownloadResult, GranuleInfo, SearchResult, SyncResult

# Backward compatibility alias
COLLECTIONS = DEFAULT_COLLECTIONS

__all__ = [
    # Version
    "__version__",
    # Main client
    "MaapClient",
    "MaapConfig",
    # Constants
    "COLLECTIONS",
    # Catalog
    "Catalog",
    "BaselineInfo",
    # Result types
    "SearchResult",
    "DownloadResult",
    "SyncResult",
    "GranuleInfo",
    # Exceptions
    "MaapError",
    "InvalidRequestError",
    "AuthenticationError",
]
