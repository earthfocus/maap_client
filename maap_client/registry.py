"""Registry file path management and low-level operations."""

import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from maap_client.paths import (
    filter_by_sensing_time,
    generate_registry_path,
    extract_sensing_time,
    url_to_local_path,
)


def read_pairs_file(file_path: Path) -> list[tuple[str, str]]:
    """
    Read file and return list of (first, second) tuples.

    Standalone function for reading state files without needing a Registry instance.

    Handles:
    - URL|PATH format: returns (url, path)
    - Single value: returns (value, "")
    - Ignores blank lines and comments (#)
    """
    if not file_path.exists():
        return []

    results = []
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|", 1)
            first = parts[0]
            second = parts[1] if len(parts) > 1 else ""
            results.append((first, second))
    return results


class Registry:
    """
    Low-level file operations for registry tracking files.

    Handles path generation and basic file operations (read, write, count, touch)
    without workflow/business logic. StateTracker builds on top of this class.

    File structure:
        registry_dir/urls/{mission}/{collection}/{product}/{baseline}/{year}/url_YYYYMMDD.txt
        registry_dir/downloads/{mission}/{collection}/{product}/{baseline}/{year}/dwl_YYYYMMDD.txt
        registry_dir/marked/{mission}/{collection}/{product}/{baseline}/{year}/mrk_YYYYMMDD.txt
    """

    def __init__(
        self,
        registry_dir: Path,
        mission: str,
        collection: str,
        product_type: str,
        baseline: str,
    ):
        """
        Initialize registry for a specific collection/product/baseline.

        Args:
            registry_dir: Base registry directory
            mission: Mission name (e.g., "EarthCARE")
            collection: Collection name
            product_type: Product type name
            baseline: Baseline version
        """
        self._registry_dir = registry_dir
        self._mission = mission
        self._collection = collection
        self._product_type = product_type
        self._baseline = baseline

        # Pre-compute base directories
        self._urls_dir = generate_registry_path(
            registry_dir, "urls", mission, collection, product_type, baseline
        )
        self._downloads_dir = generate_registry_path(
            registry_dir, "downloads", mission, collection, product_type, baseline
        )
        self._marked_dir = generate_registry_path(
            registry_dir, "marked", mission, collection, product_type, baseline
        )

    # --- Properties ---

    @property
    def urls_dir(self) -> Path:
        """Base directory for URL files."""
        return self._urls_dir

    @property
    def downloads_dir(self) -> Path:
        """Base directory for download files."""
        return self._downloads_dir

    @property
    def marked_dir(self) -> Path:
        """Base directory for marked files."""
        return self._marked_dir

    @property
    def errors_file(self) -> Path:
        """Path to errors record file."""
        return self._downloads_dir / "errors.txt"

    # --- Path generation ---

    def url_file_for_date(self, d: date) -> Path:
        """Get path to URL file for a specific date."""
        year_dir = self._urls_dir / str(d.year)
        return year_dir / f"url_{d.strftime('%Y%m%d')}.txt"

    def dwl_file_for_date(self, d: date) -> Path:
        """Get path to download file for a specific date."""
        year_dir = self._downloads_dir / str(d.year)
        return year_dir / f"dwl_{d.strftime('%Y%m%d')}.txt"

    def mrk_file_for_date(self, d: date) -> Path:
        """Get path to marked file for a specific date."""
        year_dir = self._marked_dir / str(d.year)
        return year_dir / f"mrk_{d.strftime('%Y%m%d')}.txt"

    # --- File operations ---

    @staticmethod
    def ensure_dir(file_path: Path) -> None:
        """Ensure parent directory exists."""
        file_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def exists(file_path: Path) -> bool:
        """Check if file exists."""
        return file_path.exists()

    @staticmethod
    def count_lines(file_path: Path) -> int:
        """
        Count non-empty, non-comment lines in a file.

        Returns 0 if file doesn't exist.
        """
        if not file_path.exists():
            return 0
        count = 0
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    count += 1
        return count

    @staticmethod
    def touch(file_path: Path) -> None:
        """Update file modification time to now."""
        if file_path.exists():
            file_path.touch()

    @staticmethod
    def read_pairs(file_path: Path) -> list[tuple[str, str]]:
        """
        Read file and return list of (first, second) tuples.

        Handles:
        - URL|PATH format: returns (url, path)
        - Single value: returns (value, "")
        - Ignores blank lines and comments (#)
        """
        return read_pairs_file(file_path)

    @staticmethod
    def extract_file_date(filename: str, prefix: str) -> Optional[date]:
        """
        Extract date from state filename with format {prefix}YYYYMMDD.txt.

        Args:
            filename: Filename to parse
            prefix: Expected prefix (e.g., "url_", "dwl_", "mrk_")

        Returns:
            Date object or None if parsing fails
        """
        pattern = rf"{re.escape(prefix)}(\d{{8}})\.txt$"
        match = re.search(pattern, filename)
        if match:
            return datetime.strptime(match.group(1), "%Y%m%d").date()
        return None

    @staticmethod
    def read_daily_pairs(
        files: list[Path],
        prefix: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[tuple[str, str, Optional[date]]]:
        """
        Read and date-filter multiple daily state files.

        Args:
            files: List of state files to process
            prefix: Filename prefix for date extraction (e.g., "url_", "dwl_", "mrk_")
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of (first, second, file_date) tuples
        """
        results: list[tuple[str, str, Optional[date]]] = []
        for f in files:
            fdate = Registry.extract_file_date(f.name, prefix)
            if fdate:
                if start_date and fdate < start_date:
                    continue
                if end_date and fdate > end_date:
                    continue
            for first, second in Registry.read_pairs(f):
                results.append((first, second, fdate))
        return results

    @staticmethod
    def write_pairs(file_path: Path, pairs: list[tuple[str, str]]) -> None:
        """Write pairs to file, overwriting existing content."""
        Registry.ensure_dir(file_path)
        with open(file_path, "w") as f:
            for first, second in pairs:
                if second:
                    f.write(f"{first}|{second}\n")
                else:
                    f.write(f"{first}\n")

    @staticmethod
    def append_pair(file_path: Path, first: str, second: str = "") -> None:
        """Append a single pair to file."""
        Registry.ensure_dir(file_path)
        with open(file_path, "a") as f:
            if second:
                f.write(f"{first}|{second}\n")
            else:
                f.write(f"{first}\n")

    @staticmethod
    def append_line(file_path: Path, line: str) -> None:
        """Append a line to a file."""
        Registry.ensure_dir(file_path)
        with open(file_path, "a") as f:
            f.write(line + "\n")

    # --- Listing ---

    def list_url_files(self) -> list[Path]:
        """List all URL files."""
        if not self._urls_dir.exists():
            return []
        return sorted(self._urls_dir.glob("**/url_*.txt"))

    def list_dwl_files(self) -> list[Path]:
        """List all download files."""
        if not self._downloads_dir.exists():
            return []
        return sorted(self._downloads_dir.glob("**/dwl_*.txt"))

    def list_mrk_files(self) -> list[Path]:
        """List all marked files."""
        if not self._marked_dir.exists():
            return []
        return sorted(self._marked_dir.glob("**/mrk_*.txt"))

    # --- Directory management ---

    def create_directories(self) -> None:
        """Create all registry directories."""
        self._urls_dir.mkdir(parents=True, exist_ok=True)
        self._downloads_dir.mkdir(parents=True, exist_ok=True)
        self._marked_dir.mkdir(parents=True, exist_ok=True)

    # --- URL saving ---

    def save_urls(
        self,
        urls: list[str],
        data_dir: Optional[Path] = None,
    ) -> tuple[int, list[Path]]:
        """
        Save URLs to date-partitioned files with deduplication.

        Groups URLs by sensing date, handles skip-if-same-count optimization,
        merges with existing URLs, and computes local paths.

        Args:
            urls: List of URLs to save
            data_dir: Data directory for computing local paths (URL|PATH format)

        Returns:
            Tuple of (new_urls_count, files_written)
        """
        # Group URLs by sensing date
        urls_by_date: dict[date, list[str]] = {}
        for url in urls:
            filename = os.path.basename(url)
            dt = extract_sensing_time(filename)
            if dt is None:
                continue
            sensing_date = dt.date()
            if sensing_date not in urls_by_date:
                urls_by_date[sensing_date] = []
            urls_by_date[sensing_date].append(url)

        new_count = 0
        files_written: list[Path] = []

        # Write to date-specific files
        for sensing_date, date_urls in urls_by_date.items():
            url_file = self.url_file_for_date(sensing_date)

            # Skip if file exists with same count - just touch mtime
            if url_file.exists():
                existing_count = self.count_lines(url_file)
                if existing_count == len(date_urls):
                    self.touch(url_file)
                    files_written.append(url_file)
                    continue

            # Ensure directory exists
            self.ensure_dir(url_file)

            # Load existing URLs (if file exists)
            existing: set[str] = set()
            existing_lines: dict[str, str] = {}  # url -> full line
            if url_file.exists():
                for first, second in self.read_pairs(url_file):
                    existing.add(first)
                    existing_lines[first] = f"{first}|{second}" if second else first

            # Merge and count new URLs
            new_urls = [u for u in date_urls if u not in existing]
            if new_urls:
                # Build lines for new URLs with paths
                for url in new_urls:
                    local_path = ""
                    if data_dir:
                        path = url_to_local_path(
                            url, data_dir, self._mission, self._collection
                        )
                        if path:
                            local_path = str(path)
                    existing_lines[url] = f"{url}|{local_path}"

                # Sort by URL and rewrite file
                all_lines = [existing_lines[u] for u in sorted(existing_lines.keys())]
                with open(url_file, "w") as f:
                    for line in all_lines:
                        f.write(line + "\n")
                new_count += len(new_urls)
                files_written.append(url_file)

        return new_count, files_written

    def load_urls(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[str]:
        """
        Load URLs from registry files for this collection/product/baseline.

        Args:
            start: Optional start datetime filter
            end: Optional end datetime filter

        Returns:
            List of URLs (deduplicated, from URL|PATH format)
        """
        start_date = start.date() if start else None
        end_date = end.date() if end else None

        urls: list[str] = []
        seen: set[str] = set()

        for url_file in self.list_url_files():
            # Filter by date if specified
            file_date = self.extract_file_date(url_file.name, "url_")
            if file_date:
                if start_date and file_date < start_date:
                    continue
                if end_date and file_date > end_date:
                    continue

            # Read URLs from file
            for url, _ in self.read_pairs(url_file):
                if url not in seen:
                    seen.add(url)
                    urls.append(url)

        return filter_by_sensing_time(urls, start, end)
