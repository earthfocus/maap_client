"""Text-file based state tracking for download workflows."""

from datetime import datetime, date
from pathlib import Path
from typing import Optional
import logging
import os

from maap_client.paths import extract_sensing_time, filter_by_sensing_time, url_to_local_path
from maap_client.registry import Registry

logger = logging.getLogger(__name__)


def _to_date_range(
    start: Optional[datetime], end: Optional[datetime]
) -> tuple[Optional[date], Optional[date]]:
    """Extract date parts from optional datetimes."""
    return (start.date() if start else None, end.date() if end else None)


class StateTracker:
    """
    Text-file based state tracking for crontab workflows.

    Tracks using daily files:
    - url_YYYYMMDD.txt: Discovered URLs for each sensing date (one URL per line)
    - dwl_YYYYMMDD.txt: Successfully downloaded files (one URL per line)
    - mrk_YYYYMMDD.txt: Files that have been marked/processed (one path per line)
    - errors.txt: Failed downloads (URL|ERROR)
    """

    def __init__(
        self,
        registry_dir: Path,
        mission: str,
        collection: str,
        product_type: str,
        baseline: str,
        data_dir: Optional[Path] = None,
    ):
        """
        Initialize state tracker.

        Args:
            registry_dir: Base registry directory
            mission: Mission name (e.g., "EarthCARE")
            collection: Collection name
            product_type: Product type name
            baseline: Baseline version
            data_dir: Data directory for deriving local paths (for cleanup)
        """
        self._registry = Registry(
            registry_dir=registry_dir,
            mission=mission,
            collection=collection,
            product_type=product_type,
            baseline=baseline,
        )
        self._mission = mission
        self._collection = collection
        self._data_dir = data_dir

        # Create directories
        self._registry.create_directories()

    def _file_for_date(self, d: date, file_type: str) -> Path:
        """
        Get path to state file for a specific date, ensuring directory exists.

        Args:
            d: Date for the file
            file_type: One of "url", "dwl", "mrk"

        Returns:
            Path to the state file
        """
        getter = getattr(self._registry, f"{file_type}_file_for_date")
        file_path = getter(d)
        self._registry.ensure_dir(file_path)
        return file_path

    def _url_file_for_date(self, d: date) -> Path:
        """Get path to URL file for a specific date."""
        return self._file_for_date(d, "url")

    def _dwl_file_for_date(self, d: date) -> Path:
        """Get path to download file for a specific date."""
        return self._file_for_date(d, "dwl")

    def _mrk_file_for_date(self, d: date) -> Path:
        """Get path to marked file for a specific date."""
        return self._file_for_date(d, "mrk")

    @property
    def errors_file(self) -> Path:
        """Path to errors record."""
        return self._registry.errors_file

    def load_urls_with_paths(
        self, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> list[tuple[str, str]]:
        """
        Load all URL|PATH pairs, optionally filtered by date/time range.

        Args:
            start: Optional start datetime filter
            end: Optional end datetime filter

        Returns:
            List of (url, path) tuples
        """
        start_date, end_date = _to_date_range(start, end)
        pairs = self._registry.read_daily_pairs(
            self._registry.list_url_files(), "url_", start_date, end_date
        )
        results = [(url, path) for url, path, _ in pairs]
        # Filter by sensing time
        url_to_pair = {url: (url, path) for url, path in results}
        filtered_urls = filter_by_sensing_time(list(url_to_pair.keys()), start, end)
        return [url_to_pair[url] for url in filtered_urls]

    def add_urls(self, urls: list[str]) -> int:
        """
        Add multiple URLs, organizing by sensing date.

        Format: URL|PATH

        Args:
            urls: List of product URLs

        Returns:
            Number of new URLs added
        """
        # Group URLs by date
        urls_by_date: dict[date, list[str]] = {}
        for url in urls:
            dt = extract_sensing_time(url)
            if dt is None:
                logger.warning(f"Could not extract date from URL: {url}")
                continue
            sensing_date = dt.date()
            if sensing_date not in urls_by_date:
                urls_by_date[sensing_date] = []
            urls_by_date[sensing_date].append(url)

        new_count = 0

        # Write to date-specific files
        for sensing_date, date_urls in urls_by_date.items():
            url_file = self._url_file_for_date(sensing_date)
            existing = {url for url, _ in self._registry.read_pairs(url_file)}

            with open(url_file, "a") as f:
                for url in date_urls:
                    if url not in existing:
                        # Compute expected local path
                        local_path = ""
                        if self._data_dir:
                            path = url_to_local_path(url, self._data_dir, self._mission, self._collection)
                            if path:
                                local_path = str(path)
                        f.write(f"{url}|{local_path}\n")
                        existing.add(url)
                        new_count += 1

        return new_count

    def mark_downloaded(self, url: str, local_path: Optional[Path] = None) -> bool:
        """
        Mark a URL as successfully downloaded.

        The record is written to a date-specific file based on sensing time.
        Format: URL|PATH

        Args:
            url: Product URL
            local_path: Local file path (if None, computed from URL)

        Returns:
            True if marked successfully, False if date cannot be extracted
        """
        dt = extract_sensing_time(url)
        if dt is None:
            logger.warning(f"Could not extract date from URL: {url}")
            return False
        sensing_date = dt.date()

        # Use provided path or compute from URL
        path_str = ""
        if local_path:
            path_str = str(local_path)
        elif self._data_dir:
            computed = url_to_local_path(url, self._data_dir, self._mission, self._collection)
            if computed:
                path_str = str(computed)

        dwl_file = self._dwl_file_for_date(sensing_date)
        self._registry.append_line(dwl_file, f"{url}|{path_str}")
        return True

    def mark(self, path: str) -> bool:
        """
        Mark a file as processed.

        Writes the path to a date-specific marked file based on sensing time.

        Args:
            path: Local file path

        Returns:
            True if marked successfully, False if date cannot be extracted
        """
        dt = extract_sensing_time(path)  # Extracts basename internally
        if dt is None:
            logger.warning(f"Could not extract date from path: {path}")
            return False
        sensing_date = dt.date()

        mrk_file = self._mrk_file_for_date(sensing_date)
        self._registry.append_line(mrk_file, path)
        return True

    def mark_error(self, url: str, error: str) -> None:
        """
        Record a download error.

        Args:
            url: Product URL
            error: Error message
        """
        # Sanitize error message (remove newlines, limit length)
        error = error.replace("\n", " ").replace("|", ";")[:200]
        self._registry.append_line(self.errors_file, f"{url}|{error}")

    def get_error_urls(self) -> set[str]:
        """Get URLs that failed to download."""
        pairs = self._registry.read_pairs(self.errors_file)
        return {url for url, _ in pairs}

    def get_downloaded_urls(
        self, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> set[str]:
        """
        Get URLs that have been successfully downloaded.

        Args:
            start: Optional start datetime filter
            end: Optional end datetime filter

        Returns:
            Set of downloaded URLs
        """
        start_date, end_date = _to_date_range(start, end)
        pairs = self._registry.read_daily_pairs(
            self._registry.list_dwl_files(), "dwl_", start_date, end_date
        )
        urls = [url for url, _, _ in pairs]
        return set(filter_by_sensing_time(urls, start, end))

    def get_downloaded_paths(
        self, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> set[str]:
        """
        Get local paths of downloaded files.

        Args:
            start: Optional start datetime filter
            end: Optional end datetime filter

        Returns:
            Set of local file paths
        """
        start_date, end_date = _to_date_range(start, end)
        pairs = self._registry.read_daily_pairs(
            self._registry.list_dwl_files(), "dwl_", start_date, end_date
        )

        paths = []
        for url, stored_path, _ in pairs:
            local_path = stored_path
            if not local_path and self._data_dir:
                derived = url_to_local_path(url, self._data_dir, self._mission, self._collection)
                if derived:
                    local_path = str(derived)
            if local_path:
                paths.append(local_path)

        return set(filter_by_sensing_time(paths, start, end))

    def get_marked_paths(
        self, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> set[str]:
        """
        Get paths that have been marked/processed.

        Args:
            start: Optional start datetime filter
            end: Optional end datetime filter

        Returns:
            Set of marked file paths
        """
        start_date, end_date = _to_date_range(start, end)
        pairs = self._registry.read_daily_pairs(
            self._registry.list_mrk_files(), "mrk_", start_date, end_date
        )
        paths = [path for path, _, _ in pairs]
        return set(filter_by_sensing_time(paths, start, end))

    def get_pending_downloads(
        self, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> set[str]:
        """
        Get URLs discovered but not yet downloaded.

        Args:
            start: Optional start datetime filter
            end: Optional end datetime filter

        Returns:
            Set of URLs that need to be downloaded
        """
        all_urls = {url for url, _ in self.load_urls_with_paths(start, end)}
        downloaded = self.get_downloaded_urls(start, end)
        return all_urls - downloaded

    def get_pending_mark_paths(
        self, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> set[str]:
        """
        Get local paths of files that need marking.

        Args:
            start: Optional start datetime filter
            end: Optional end datetime filter

        Returns:
            Set of local file paths that need to be processed
        """
        downloaded_paths = self.get_downloaded_paths(start, end)
        marked = self.get_marked_paths(start, end)
        return downloaded_paths - marked

    def get_deletable_files(self) -> list[Path]:
        """
        Get local paths of files that have been marked and can be deleted.

        Returns:
            List of file paths that are safe to delete
        """
        marked_paths = self.get_marked_paths()

        deletable = []
        for path_str in marked_paths:
            path = Path(path_str)
            if path.exists():
                deletable.append(path)

        return deletable

    def cleanup_marked(self, dry_run: bool = False) -> list[Path]:
        """
        Delete files that have been marked.

        Args:
            dry_run: If True, don't actually delete files

        Returns:
            List of paths that were (or would be) deleted
        """
        deletable = self.get_deletable_files()

        if not dry_run:
            for path in deletable:
                try:
                    os.remove(path)
                    logger.info(f"Deleted: {path}")
                except OSError as e:
                    logger.error(f"Failed to delete {path}: {e}")

        return deletable

    def get_stats(
        self, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> dict[str, int]:
        """
        Get summary statistics.

        Args:
            start: Optional start datetime filter
            end: Optional end datetime filter

        Returns:
            Dictionary with counts for each state
        """
        # Read data once to minimize file I/O
        all_url_pairs = self.load_urls_with_paths(start, end)
        all_urls = {url for url, _ in all_url_pairs}
        downloaded = self.get_downloaded_urls(start, end)
        downloaded_paths = self.get_downloaded_paths(start, end)
        marked = self.get_marked_paths(start, end)
        errors = self.get_error_urls()  # errors.txt is not date-partitioned

        pending_downloads = all_urls - downloaded
        pending_marks = downloaded_paths - marked

        return {
            "total_urls": len(all_urls),
            "downloaded": len(downloaded),
            "marked": len(marked),
            "errors": len(errors),
            "pending_downloads": len(pending_downloads),
            "pending_marks": len(pending_marks),
        }

    def list_dates(self, state_type: str = "urls") -> list[date]:
        """
        List all dates that have state files.

        Args:
            state_type: "urls", "downloads", or "marked"

        Returns:
            Sorted list of dates
        """
        dates = []

        if state_type == "urls":
            files = self._registry.list_url_files()
            prefix = "url_"
        elif state_type == "downloads":
            files = self._registry.list_dwl_files()
            prefix = "dwl_"
        else:  # marked
            files = self._registry.list_mrk_files()
            prefix = "mrk_"

        for f in files:
            fdate = self._registry.extract_file_date(f.name, prefix)
            if fdate:
                dates.append(fdate)

        return sorted(dates)


class GlobalStateTracker:
    """
    Manager for accessing state trackers across collections/products.
    """

    def __init__(self, registry_dir: Path, mission: str, data_dir: Optional[Path] = None):
        """
        Initialize global state tracker.

        Args:
            registry_dir: Base registry directory
            mission: Mission name (e.g., "EarthCARE")
            data_dir: Data directory for deriving local paths (for cleanup)
        """
        self._registry_dir = registry_dir
        self._mission = mission
        self._data_dir = data_dir

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
        return StateTracker(
            registry_dir=self._registry_dir,
            mission=self._mission,
            collection=collection,
            product_type=product_type,
            baseline=baseline,
            data_dir=self._data_dir,
        )

    def list_tracked(self) -> list[tuple[str, str, str]]:
        """
        List all collection/product/baseline combinations being tracked.

        Returns:
            List of (collection, product_type, baseline) tuples
        """
        tracked = []

        # Look in downloads/{mission}/ for tracked items
        downloads_dir = self._registry_dir / "downloads" / self._mission
        if not downloads_dir.exists():
            return tracked

        for collection_dir in downloads_dir.iterdir():
            if not collection_dir.is_dir():
                continue
            for product_dir in collection_dir.iterdir():
                if not product_dir.is_dir():
                    continue
                for baseline_dir in product_dir.iterdir():
                    if not baseline_dir.is_dir():
                        continue
                    tracked.append(
                        (
                            collection_dir.name,
                            product_dir.name,
                            baseline_dir.name,
                        )
                    )

        return tracked

    def get_all_stats(self) -> dict[tuple[str, str, str], dict[str, int]]:
        """
        Get statistics for all tracked combinations.

        Returns:
            Dictionary mapping (collection, product, baseline) to stats
        """
        stats = {}
        for collection, product, baseline in self.list_tracked():
            tracker = self.get_tracker(collection, product, baseline)
            stats[(collection, product, baseline)] = tracker.get_stats()
        return stats
