"""Authenticated file downloads from MAAP."""

from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse
import logging
import os
import time
import requests

from maap_client.auth import TokenManager, get_auth_headers
from maap_client.constants import DEFAULT_CHUNK_SIZE, DEFAULT_MISSION
from maap_client.exceptions import DownloadError
from maap_client.paths import (
    extract_sensing_time,
    generate_data_path,
)

logger = logging.getLogger(__name__)

# Type for progress callback: (bytes_downloaded, total_bytes)
ProgressCallback = Callable[[int, int], None]


class DownloadManager:
    """Handles authenticated file downloads from MAAP."""

    def __init__(
        self,
        token_manager: TokenManager,
        data_dir: Path,
        mission: str = DEFAULT_MISSION,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ):
        """
        Initialize download manager.

        Args:
            token_manager: OAuth2 token manager
            data_dir: Base directory for downloads
            mission: Mission name for path generation
            chunk_size: Download chunk size in bytes
        """
        self._token_manager = token_manager
        self._data_dir = data_dir
        self._mission = mission
        self._chunk_size = chunk_size

    def download_file(
        self,
        url: str,
        output_path: Optional[Path] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Path:
        """
        Download a single file with authentication.

        Args:
            url: Product URL
            output_path: Optional explicit output path (if None, uses filename from URL)
            progress_callback: Optional callback for progress updates

        Returns:
            Path to downloaded file

        Raises:
            DownloadError: If download fails
        """
        if output_path is None:
            # Extract filename from URL
            parsed = urlparse(url)
            filename = os.path.basename(parsed.path)
            output_path = self._data_dir / filename

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Get auth headers
        headers = get_auth_headers(self._token_manager)

        logger.info(f"Downloading: {url}")
        logger.debug(f"  -> {output_path}")

        try:
            t0 = time.monotonic()
            with requests.get(url, headers=headers, stream=True, timeout=60) as r:
                r.raise_for_status()

                # Get total size if available
                total_size = int(r.headers.get("content-length", 0))
                downloaded = 0

                with open(output_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=self._chunk_size):
                        f.write(chunk)
                        downloaded += len(chunk)

                        if progress_callback and total_size:
                            progress_callback(downloaded, total_size)

            elapsed = time.monotonic() - t0

        except requests.HTTPError as e:
            raise DownloadError(url, str(e), e.response.status_code if e.response else None)
        except requests.RequestException as e:
            raise DownloadError(url, str(e))

        # Log transfer rate
        if elapsed > 0 and downloaded > 0:
            rate_mbps = (downloaded / (1024 * 1024)) / elapsed
            size_mb = downloaded / (1024 * 1024)
            logger.info(f"Download complete: {output_path} ({size_mb:.1f} MB, {rate_mbps:.1f} MB/s)")
        else:
            logger.info(f"Download complete: {output_path}")
        return output_path

    def batch_download(
        self,
        urls: list[str],
        collection: str,
        product_type: str,
        baseline: str,
        skip_existing: bool = True,
        on_download: Optional[Callable[[str, Path], None]] = None,
        verbose: bool = False,
    ) -> dict[str, Path]:
        """
        Download multiple files.

        Args:
            urls: List of product URLs
            collection: Collection name
            product_type: Product type name
            baseline: Baseline version
            skip_existing: Skip files that already exist
            on_download: Optional callback called after each successful download
                         with (url, local_path). Used for incremental state updates.
            verbose: Print progress messages

        Returns:
            Dictionary mapping URL to local path (only successful downloads)
        """
        results = {}
        total = len(urls)
        width = len(str(total))

        for i, url in enumerate(urls, 1):
            logger.info(f"[{i:>{width}}/{total}] Processing: {url}")

            # Determine output path
            parsed = urlparse(url)
            filename = os.path.basename(parsed.path)
            dt = extract_sensing_time(filename)

            if dt is None:
                logger.warning("  Skipping - cannot extract datetime from filename")
                continue

            output_path = generate_data_path(
                data_dir=self._data_dir,
                mission=self._mission,
                collection=collection,
                product_type=product_type,
                baseline=baseline,
                dt=dt,
                filename=filename,
            )

            # Skip if exists
            if skip_existing and output_path.exists():
                logger.info(f"  Skipping - already exists: {output_path}")
                if verbose:
                    logger.info(f"[{i:>{width}}/{total}] Already exists: {filename}")
                results[url] = output_path
                # Still call callback for existing files (state tracking)
                if on_download:
                    on_download(url, output_path)
                continue

            if verbose:
                logger.info(f"[{i:>{width}}/{total}] Downloading: {filename}")

            try:
                path = self.download_file(url, output_path)
                results[url] = path
                # Call callback after successful download
                if on_download:
                    on_download(url, path)
            except DownloadError as e:
                logger.error(f"  Download failed: {e}")
                if verbose:
                    logger.error(f"[{i:>{width}}/{total}] Error: {e}")
                continue

        return results


def download_single_file(
    url: str,
    output_path: Path,
    token_manager: TokenManager,
) -> Path:
    """
    Convenience function to download a single file.

    Args:
        url: Product URL
        output_path: Output file path
        token_manager: OAuth2 token manager

    Returns:
        Path to downloaded file
    """
    manager = DownloadManager(
        token_manager=token_manager,
        data_dir=output_path.parent,
    )
    return manager.download_file(url, output_path)
