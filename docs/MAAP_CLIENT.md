# MaapClient Module Documentation

This document describes the `MaapClient` class - the main facade for accessing ESA MAAP satellite data.

## Overview

`MaapClient` is the high-level entry point for the `maap_client` package. It implements the **Facade Pattern**, providing a unified interface that orchestrates multiple internal managers:

- **CatalogQueryablesManager** - Browses collections, products, baselines
- **MaapSearcher** - Queries STAC API for product URLs
- **TokenManager** - Handles OAuth2 authentication
- **DownloadManager** - Downloads authenticated HDF5 files
- **GlobalStateTracker** - Tracks workflow state (URLs, downloads, marks)

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User Code                                      │
│                                                                             │
│    from maap_client import MaapClient                                       │
│    client = MaapClient()                                                    │
│    result = client.search(...)                                              │
│    client.download(result.urls, ...)                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MaapClient (Facade)                               │
│                                                                             │
│  Provides unified API for all MAAP operations:                              │
│  • Catalog browsing                                                         │
│  • Product searching                                                        │
│  • File downloading                                                         │
│  • State tracking                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
          │              │              │              │              │
          ▼              ▼              ▼              ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  Catalog    │ │   Maap      │ │   Token     │ │  Download   │ │   Global    │
│  Manager    │ │  Searcher   │ │  Manager    │ │  Manager    │ │   State     │
│             │ │             │ │             │ │             │ │  Tracker    │
│catalog_qry  │ │ search.py   │ │  auth.py    │ │ download.py │ │ tracker.py  │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
       │              │              │              │              │
       ▼              ▼              ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          MaapConfig (config.py)                             │
│                                                                             │
│  Configuration loaded from: CLI args → Env vars → TOML file → Defaults     │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Lazy Initialization

All internal managers are initialized **lazily** (on first access) to avoid unnecessary resource allocation:

```python
class MaapClient:
    def __init__(self, config: Optional[MaapConfig] = None):
        self._config = config or MaapConfig.load()
        self._catalog: Optional[CatalogQueryablesManager] = None      # Lazy
        self._searcher: Optional[MaapSearcher] = None       # Lazy
        self._token_manager: Optional[TokenManager] = None  # Lazy
        self._downloader: Optional[DownloadManager] = None  # Lazy
        self._state: Optional[GlobalStateTracker] = None    # Lazy
```

Managers are created when first accessed via properties:

| Property | Manager | Created When |
|----------|---------|--------------|
| `client.catalog` | CatalogQueryablesManager | First catalog operation |
| `client.searcher` | MaapSearcher | First search operation |
| `client.state` | GlobalStateTracker | First state operation |
| `_get_token_manager()` | TokenManager | First download (requires credentials) |
| `_get_downloader()` | DownloadManager | First download |

## Public API

### Initialization

```python
from maap_client import MaapClient, MaapConfig

# Default configuration (loads from env/TOML/defaults)
client = MaapClient()

# Custom configuration
config = MaapConfig(
    data_dir=Path("./my_data"),
    credentials_file=Path("./my_creds.txt"),
)
client = MaapClient(config=config)

# Access configuration
print(client.config.data_dir)
```

### Catalog Operations

| Method | Description | Returns |
|--------|-------------|---------|
| `list_collections()` | List all known MAAP collections | `list[str]` |
| `list_products(collection, from_built, verify)` | List product types for collection | `list[str]` |
| `list_baselines(collection, product, from_built, verify)` | List baselines for product | `list[str]` |
| `get_baseline_info(collection, product, baseline, ...)` | Get baseline metadata | `Optional[BaselineInfo]` |
| `update_catalogs(collections, force, out_dir)` | Download/update queryables | `dict[str, Path]` |
| `build_catalog(collection, product, baseline, ...)` | Build catalog from API | `dict[str, Path]` |

#### Examples

```python
from maap_client import MaapClient

client = MaapClient()

# List all collections
collections = client.list_collections()
# ['EarthCAREL0L1Products_MAAP', 'EarthCAREL1Validated_MAAP', ...]

# List products in a collection
products = client.list_products("EarthCAREL2Validated_MAAP")
# ['CPR_CLD_2A', 'MSI_AOT_2A', 'ACM_CAP_2A', ...]

# List baselines (fast, from catalog)
baselines = client.list_baselines("EarthCAREL2Validated_MAAP", "CPR_CLD_2A")
# ['AA', 'AB', 'BA', 'BB', 'BC', ...]

# List baselines with actual data (slower, queries API)
baselines = client.list_baselines("EarthCAREL2Validated_MAAP", "CPR_CLD_2A", verify=True)
# ['BC', 'BD']  # Only baselines that have products

# Get baseline info (time range, count, etc.)
info = client.get_baseline_info("EarthCAREL2Validated_MAAP", "CPR_CLD_2A", "BC")
if info:
    print(f"Count: {info.count}")
    print(f"Range: {info.time_start} to {info.time_end}")
```

### Search Operations

| Method | Description | Returns |
|--------|-------------|---------|
| `search(collection, product, baseline, start, end, orbit, ...)` | Search for URLs | `SearchResult` |
| `search_product_count(collection, product, baseline, start, end)` | Count products (fast) | Via searcher |

The `search()` method supports both time-based and orbit-based search (mutually exclusive).

#### SearchResult

```python
@dataclass
class SearchResult:
    urls: list[str]           # List of download URLs
    baselines_found: list[str]  # Unique baselines in results
    start: Optional[datetime]   # Actual search start
    end: Optional[datetime]     # Actual search end
    total_count: int           # Total URLs found
```

#### Examples

```python
from datetime import datetime, timezone
from maap_client import MaapClient

client = MaapClient()

# Search with time range (returns SearchResult)
result = client.search(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
    start=datetime(2024, 12, 1, tzinfo=timezone.utc),
    end=datetime(2024, 12, 7, tzinfo=timezone.utc),
)
print(f"Found {result.total_count} URLs")
print(f"Baselines: {result.baselines_found}")

# Search by orbit+frame
result = client.search(
    collection="EarthCAREL1Validated_MAAP",
    product_type="CPR_NOM_1B",
    orbit="01525F",
    baseline="BC",
)

# Search all baselines (omit baseline parameter)
result = client.search(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    start=datetime(2024, 12, 1, tzinfo=timezone.utc),
    end=datetime(2024, 12, 7, tzinfo=timezone.utc),
)
print(f"Found baselines: {result.baselines_found}")
```

### Download Operations

| Method | Description | Returns |
|--------|-------------|---------|
| `download(urls, collection, out_dir, track_state, ...)` | Download files | `DownloadResult` |
| `download_from_registry(collection, product, baseline, ...)` | Download from registry | `DownloadResult` |

#### DownloadResult

```python
@dataclass
class DownloadResult:
    downloaded: dict[str, Path]  # URL → local path
    skipped: list[str]           # URLs skipped (existing or dry-run)
    errors: list[str]            # Error messages
    total_bytes: int             # Total bytes downloaded
    elapsed_seconds: float       # Total time
```

#### Examples

```python
from maap_client import MaapClient

client = MaapClient()

# Download from search results
result = client.search(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
    start=datetime(2024, 12, 1, tzinfo=timezone.utc),
    end=datetime(2024, 12, 7, tzinfo=timezone.utc),
)

download_result = client.download(
    urls=result.urls,
    collection="EarthCAREL2Validated_MAAP",
    track_state=True,    # Update state files
    verbose=True,        # Print progress
)
print(f"Downloaded {len(download_result.downloaded)} files")
# Files saved to: data/EarthCARE/EarthCAREL2Validated_MAAP/CPR_CLD_2A/BC/2024/12/01/

# Download to specific directory (flat, no structured paths)
download_result = client.download(
    urls=result.urls,
    collection="EarthCAREL2Validated_MAAP",
    out_dir=Path("./my_downloads"),
)

# Download from registry
download_result = client.download_from_registry(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
    start=datetime(2024, 12, 1, tzinfo=timezone.utc),
    end=datetime(2024, 12, 31, tzinfo=timezone.utc),
)
```

### High-Level Operations

| Method | Description | Returns |
|--------|-------------|---------|
| `get(collection, product, baseline, start, end, orbit, ...)` | Search + download in one step | `DownloadResult` |
| `sync(collection, product, baseline, start, end, ...)` | Incremental: search + registry + download | `SyncResult` |

#### SyncResult

```python
@dataclass
class SyncResult:
    collection: str
    product_type: str
    baselines: list[str]
    urls_found: int = 0
    urls_downloaded: int = 0
    errors: list[str]
    tracker: Optional[StateTracker] = None  # For post-sync operations
```

#### Examples

```python
from datetime import datetime, timezone
from maap_client import MaapClient

client = MaapClient()

# Get: search + download in one step
result = client.get(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
    start=datetime(2024, 12, 1, tzinfo=timezone.utc),
    end=datetime(2024, 12, 7, tzinfo=timezone.utc),
)
print(f"Downloaded {len(result.downloaded)} files")

# Sync: incremental with state tracking
# Default: syncs last 3 days if no start/end specified
sync_result = client.sync(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
)
print(f"Found {sync_result.urls_found} URLs")
print(f"Downloaded {sync_result.urls_downloaded} files")

# Sync with specific date range
sync_result = client.sync(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
    start=datetime(2024, 12, 1, tzinfo=timezone.utc),
    end=datetime(2024, 12, 31, tzinfo=timezone.utc),
)

# Sync all baselines (omit baseline parameter)
sync_result = client.sync(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
)
print(f"Synced baselines: {sync_result.baselines}")
```

### Registry Operations

| Method | Description | Returns |
|--------|-------------|---------|
| `save_to_registry(urls, collection, product_type)` | Save URLs to registry files | `tuple[int, list[Path]]` |
| `load_from_registry(collection, product_type, baseline, start, end)` | Load URLs from registry | `list[str]` |

Registry files are organized by sensing date and baseline:
```
registry/urls/{mission}/{collection}/{product}/{baseline}/{year}/url_YYYYMMDD.txt
```

#### Examples

```python
from maap_client import MaapClient

client = MaapClient()

# Save search results to registry (auto-groups by baseline)
result = client.search(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    start=datetime(2024, 12, 1, tzinfo=timezone.utc),
    end=datetime(2024, 12, 31, tzinfo=timezone.utc),
)
new_count, files = client.save_to_registry(
    urls=result.urls,
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
)
print(f"Saved {new_count} new URLs to {len(files)} registry files")

# Load from registry
urls = client.load_from_registry(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",  # Optional, discovers from registry if None
    start=datetime(2024, 12, 1, tzinfo=timezone.utc),
    end=datetime(2024, 12, 31, tzinfo=timezone.utc),
)
```

### State Operations

| Method | Description | Returns |
|--------|-------------|---------|
| `get_tracker(collection, product, baseline)` | Get state tracker | `StateTracker` |
| `state` (property) | Get global state manager | `GlobalStateTracker` |

#### Examples

```python
from maap_client import MaapClient

client = MaapClient()

# Get tracker for specific product
tracker = client.get_tracker(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
)

# Track URLs
tracker.add_urls(urls)

# Get pending downloads
pending = tracker.get_pending_downloads()

# Mark as downloaded
tracker.mark_downloaded(url, local_path)

# Check status
stats = tracker.get_stats()
print(f"URLs: {stats['total_urls']}, Downloaded: {stats['downloaded']}")
```

### Utility Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `normalize_time_range(start, end)` | Clamp time range to mission bounds | `tuple[datetime, datetime]` |

```python
# Normalize time range to mission bounds
start, end = client.normalize_time_range(
    start=datetime(2020, 1, 1, tzinfo=timezone.utc),  # Before mission
    end=datetime(2099, 12, 31, tzinfo=timezone.utc),  # After mission
)
# Returns mission_start to min(now, mission_end)
```

## Data Flow

### Search and Download Workflow

```
                    search() / sync()
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        MaapSearcher                             │
│                                                                 │
│  POST https://catalog.maap.eo.esa.int/catalogue/search          │
│  {                                                              │
│    "collections": ["EarthCAREL2Validated_MAAP"],                │
│    "filter": {                                                  │
│      "op": "and",                                               │
│      "args": [                                                  │
│        {"op": "=", "args": [{"property": "productType"}, "X"]}, │
│        {"op": "=", "args": [{"property": "productVersion"}, "Y"]│
│      ]                                                          │
│    },                                                           │
│    "datetime": "2024-12-01T00:00:00Z/2024-12-31T23:59:59Z"      │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    SearchResult (urls, baselines_found, ...)
                              │
                              ▼
                    download(result.urls, ...)
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       DownloadManager                           │
│                                                                 │
│  1. TokenManager.get_token() -> Bearer token                    │
│  2. GET url with Authorization header                           │
│  3. Stream to: data/mission/collection/product/baseline/y/m/d/  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        StateTracker                             │
│                                                                 │
│  registry/urls/.../url_YYYYMMDD.txt     <- URL added             │
│  registry/downloads/.../dwl_YYYYMMDD.txt <- Downloaded marked   │
└─────────────────────────────────────────────────────────────────┘
```

## Exports

The module exports these public symbols (via `__all__`):

```python
from maap_client import (
    __version__,      # Package version string
    COLLECTIONS,      # List of known collection names
    MaapClient,       # Main facade class
    MaapConfig,       # Configuration dataclass
    SearchResult,     # Search result type
    DownloadResult,   # Download result type
    SyncResult,       # Sync result type
    GranuleInfo,      # Granule metadata
    BaselineInfo,     # Baseline metadata
)
```

## Dependencies

The `client.py` imports from these internal modules:

| Import | From Module | Purpose |
|--------|-------------|---------|
| `MaapConfig` | config.py | Configuration |
| `load_credentials`, `TokenManager` | auth.py | Authentication |
| `CatalogQueryablesManager` | catalog_query.py | Catalog browsing |
| `CatalogCollectionManager`, `BaselineInfo` | catalog_build.py | Built catalogs |
| `MaapSearcher` | search.py | STAC queries |
| `DownloadManager` | download.py | File downloads |
| `GlobalStateTracker`, `StateTracker` | tracker.py | State management |
| `Registry` | registry.py | Registry file operations |
| `extract_baseline`, `extract_product` | paths.py | Filename parsing |
| `SearchResult`, `DownloadResult`, `SyncResult` | types.py | Result types |

## Error Handling

MaapClient methods may raise these exceptions:

| Exception | When | Example |
|-----------|------|---------|
| `InvalidRequestError` | Invalid parameters | `start > end`, non-timezone-aware datetime |
| `CredentialsError` | Credentials file missing/invalid | `download()` with bad creds |
| `AuthenticationError` | Token exchange fails | Expired OFFLINE_TOKEN |
| `CatalogError` | Catalog API errors | Invalid collection name |
| `DownloadError` | Download fails | HTTP 403/404 |

```python
from maap_client import MaapClient
from maap_client.exceptions import (
    InvalidRequestError,
    CredentialsError,
    AuthenticationError,
)

client = MaapClient()

try:
    result = client.download(urls, collection="...")
except InvalidRequestError as e:
    print(f"Invalid parameters: {e}")
except CredentialsError as e:
    print(f"Setup credentials.txt first: {e}")
except AuthenticationError as e:
    print(f"Token expired, renew at ESA portal: {e}")
```

## File Locations

| File | Purpose |
|------|---------|
| `maap_client/client.py` | MaapClient facade (this module) |
| `maap_client/__init__.py` | Re-exports from submodules |
| `maap_client/config.py` | MaapConfig dataclass |
| `maap_client/auth.py` | TokenManager, credentials |
| `maap_client/catalog_query.py` | CatalogQueryablesManager |
| `maap_client/catalog_build.py` | CatalogCollectionManager |
| `maap_client/search.py` | MaapSearcher |
| `maap_client/download.py` | DownloadManager |
| `maap_client/tracker.py` | StateTracker |
| `maap_client/registry.py` | Registry |
| `maap_client/types.py` | Result types |

## Design Decisions

### Why a Facade Pattern?

1. **Simplicity**: Users interact with one class instead of managing multiple managers
2. **Encapsulation**: Internal implementation can change without breaking user code
3. **Configuration sharing**: All managers share the same `MaapConfig` instance
4. **Lazy loading**: Resources allocated only when needed

### Why Lazy Initialization?

1. **Fast startup**: Creating a `MaapClient()` is instant
2. **Conditional resources**: TokenManager only created if downloading (needs credentials)
3. **Memory efficiency**: Unused managers never allocate

### Why Result Types?

1. **Type safety**: Clear structure for return values
2. **Metadata**: Include stats like `total_count`, `baselines_found`, `elapsed_seconds`
3. **Composability**: Pass results between methods (e.g., `search().urls` to `download()`)

### Why Day-by-Day Search in sync()?

The `sync()` method iterates day-by-day because:

1. **Large date ranges**: Single queries for 6+ months can timeout or hit API limits
2. **Incremental processing**: Process results as they come, don't wait for everything
3. **Fault tolerance**: If day 50 fails, days 1-49 are already processed
4. **Progress visibility**: Users see progress for long-running syncs
