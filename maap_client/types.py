"""Type definitions for MAAP client."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import NamedTuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from maap_client.tracker import StateTracker


class GranuleInfo(NamedTuple):
    """Metadata extracted from an EarthCARE product filename.

    All fields except filename may be None if parsing fails.
    """

    filename: str
    mission: Optional[str]
    agency: Optional[str]
    baseline: Optional[str]
    product_type: Optional[str]
    sensing_time: Optional[datetime]
    creation_time: Optional[datetime]
    orbit_frame: Optional[str]


@dataclass
class SearchResult:
    """Result from search operation."""

    urls: list[str]
    baselines_found: list[str]  # Baselines that had data
    start: Optional[datetime]  # Actual start of search range
    end: Optional[datetime]  # Actual end of search range
    total_count: int  # Number of URLs found


@dataclass
class DownloadResult:
    """Result from download operation."""

    downloaded: dict[str, Path] = field(default_factory=dict)  # url -> local_path
    skipped: list[str] = field(default_factory=list)  # URLs skipped (already exist)
    errors: list[str] = field(default_factory=list)  # Error messages
    total_bytes: int = 0  # Total bytes downloaded
    elapsed_seconds: float = 0.0  # Time taken for downloads


@dataclass
class SyncResult:
    """Result from sync operation."""

    collection: str
    product_type: str
    baselines: list[str]  # List of baselines synced
    urls_found: int = 0
    urls_downloaded: int = 0
    urls_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    tracker: Optional["StateTracker"] = None  # For post-sync operations
