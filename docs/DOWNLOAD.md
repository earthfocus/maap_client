# Download Module Documentation

This document describes the authenticated download functionality in `maap_client/download.py`.

## Overview

The `download.py` module handles authenticated file downloads from the MAAP data archive. It:

- Authenticates requests using OAuth2 Bearer tokens
- Streams large files efficiently
- Organizes downloads into structured directory hierarchies
- Supports batch downloads with progress callbacks

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       DownloadManager                           │
│                                                                 │
│  - Manages token lifecycle via TokenManager                     │
│  - Generates structured paths for downloads                     │
│  - Handles batch operations with callbacks                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       TokenManager                              │
│                                                                 │
│  get_token() → Bearer token for Authorization header            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MAAP Data Archive                            │
│                                                                 │
│  GET https://catalog.maap.eo.esa.int/data/.../file.h5           │
│  Authorization: Bearer <access_token>                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Structured File Path                          │
│                                                                 │
│  {data_dir}/{mission}/{collection}/{product}/{baseline}/        │
│  {year}/{month}/{day}/{filename}                                │
└─────────────────────────────────────────────────────────────────┘
```

## DownloadManager Class

### Initialization

```python
from pathlib import Path
from maap_client.auth import load_credentials, TokenManager
from maap_client.download import DownloadManager

credentials = load_credentials()
token_manager = TokenManager(credentials=credentials)

downloader = DownloadManager(
    token_manager=token_manager,
    data_dir=Path("./data"),
    mission="EarthCARE",
    chunk_size=8192,  # Optional, default 8KB
)
```

### download_file()

Download a single file with authentication.

```python
def download_file(
    self,
    url: str,
    output_path: Optional[Path] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> Path:
```

**Parameters:**
- `url`: Product URL to download
- `output_path`: Where to save (if None, uses filename from URL)
- `progress_callback`: Optional `(bytes_downloaded, total_bytes) -> None`

**Returns:** Path to downloaded file

**Raises:** `DownloadError` if download fails

```python
# Basic usage
path = downloader.download_file(
    url="https://catalog.maap.eo.esa.int/data/.../file.h5",
    output_path=Path("./my_file.h5"),
)

# With progress callback
def show_progress(downloaded, total):
    pct = (downloaded / total) * 100 if total else 0
    print(f"Downloaded {pct:.1f}%")

path = downloader.download_file(url, progress_callback=show_progress)
```

### download_url_auto()

Download with automatic path detection from URL.

```python
def download_url_auto(
    self,
    url: str,
    collection: Optional[str] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> Optional[Path]:
```

Attempts to parse product metadata from URL and generate structured path automatically.

```python
path = downloader.download_url_auto(
    url="https://catalog.maap.eo.esa.int/data/.../CPR_CLD_2A/BC/2024/12/15/file.h5",
    collection="EarthCAREL2Validated_MAAP",  # Optional hint
)
```

### batch_download()

Download multiple files with state tracking support.

```python
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
```

**Parameters:**
- `urls`: List of URLs to download
- `collection`, `product_type`, `baseline`: For path generation
- `skip_existing`: Skip files that already exist
- `on_download`: Callback `(url, local_path) -> None` after each download
- `verbose`: Print progress messages

**Returns:** Dictionary mapping URL to local path (successful downloads only)

```python
# Basic batch download
results = downloader.batch_download(
    urls=urls,
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
    verbose=True,
)
print(f"Downloaded {len(results)} files")

# With state tracking callback
def mark_downloaded(url, path):
    tracker.mark_downloaded(url, path)

results = downloader.batch_download(
    urls=urls,
    collection="...",
    product_type="...",
    baseline="...",
    on_download=mark_downloaded,
)
```

## Convenience Function

### download_single_file()

Simple function for one-off downloads.

```python
from maap_client.download import download_single_file

path = download_single_file(
    url="https://...",
    output_path=Path("./file.h5"),
    token_manager=token_manager,
)
```

## Progress Callback

The `ProgressCallback` type is:

```python
ProgressCallback = Callable[[int, int], None]
# Args: (bytes_downloaded, total_bytes)
```

**Example implementations:**

```python
# Simple percentage
def simple_progress(downloaded, total):
    if total:
        print(f"{(downloaded/total)*100:.1f}%")

# Progress bar (with tqdm)
from tqdm import tqdm

pbar = None
def tqdm_progress(downloaded, total):
    global pbar
    if pbar is None:
        pbar = tqdm(total=total, unit='B', unit_scale=True)
    pbar.update(downloaded - pbar.n)
```

## Download Flow

```
batch_download(urls, ...)
        │
        ▼
┌─────────────────────────────────────────┐
│ For each URL:                           │
│                                         │
│ 1. Extract filename from URL            │
│ 2. Extract sensing time from filename   │
│ 3. Generate structured output path      │
│ 4. Check if file exists (skip if yes)   │
│ 5. Get auth token via TokenManager      │
│ 6. Stream download with Authorization   │
│ 7. Call on_download callback if set     │
└─────────────────────────────────────────┘
        │
        ▼
    dict[url, path]
```

## Error Handling

### DownloadError

Raised when download fails. Contains context:

```python
class DownloadError(MaapError):
    def __init__(self, url: str, message: str, status_code: int | None = None):
        self.url = url
        self.status_code = status_code
```

**Common status codes:**

| Code | Meaning | Action |
|------|---------|--------|
| 401 | Unauthorized | Check credentials, token may be expired |
| 403 | Forbidden | Check permissions |
| 404 | Not Found | File may have been removed |
| 500-504 | Server Error | Retry later |

```python
from maap_client.exceptions import DownloadError

try:
    path = downloader.download_file(url)
except DownloadError as e:
    print(f"Failed: {e.url}")
    print(f"Status: {e.status_code}")

    if e.status_code == 401:
        print("Token may have expired")
    elif e.status_code == 404:
        print("File not found")
```

## Dependencies

| Import | From | Purpose |
|--------|------|---------|
| `TokenManager`, `get_auth_headers` | auth.py | Authentication |
| `DEFAULT_CHUNK_SIZE`, `MISSION` | constants.py | Defaults |
| `DownloadError` | exceptions.py | Error handling |
| `url_to_local_path`, `extract_sensing_time`, `generate_data_path` | paths.py | Path generation |

## Configuration

| Setting | Source | Default |
|---------|--------|---------|
| `data_dir` | MaapConfig | `./data` |
| `mission` | MaapConfig | `EarthCARE` |
| `chunk_size` | constants.py | 8192 bytes |
| `timeout` | Hardcoded | 60 seconds |

## Usage via MaapClient

Most users should use `MaapClient` which wraps `DownloadManager`:

```python
from maap_client import MaapClient

client = MaapClient()

# Download multiple files (URLs from search results)
result = client.download(
    urls=urls,
    collection="EarthCAREL2Validated_MAAP",
    track_state=True,
    verbose=True,
)
print(f"Downloaded {len(result.downloaded)} files")

# Download with state tracking from registry
result = client.download_from_registry(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
    verbose=True,
)
```

## Design Decisions

### Why Stream Downloads?

1. **Memory efficiency**: Don't load entire file into memory
2. **Progress tracking**: Can report progress during download
3. **Large files**: HDF5 files can be hundreds of MB

### Why 8KB Chunks?

1. **Balance**: Good trade-off between syscalls and memory
2. **Standard**: Common default in HTTP clients
3. **Configurable**: Can be changed if needed

### Why Structured Paths?

1. **Organization**: Easy to browse by date/product
2. **Uniqueness**: No filename collisions
3. **Compatibility**: Works with file-based tools (rsync, find)
4. **Cleanup**: Easy to delete old data by date

### Why Callbacks for State?

1. **Decoupling**: Download logic separate from state logic
2. **Flexibility**: Can use any state tracking system
3. **Incremental**: State updated after each file, not at end
4. **Resumable**: If batch fails, completed files are tracked

## File Location

| File | Purpose |
|------|---------|
| `maap_client/download.py` | This module |
