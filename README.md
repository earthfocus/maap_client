# MAAP Client

A Python client for accessing ESA MAAP satellite data. Provides both a CLI (`maap`) and a Python library for browsing catalogs, searching products, and downloading authenticated HDF5 files. By default, it's configured for EarthCARE data, but supports other missions (Aeolus) through configuration.

## Table of Contents

- [Installation](#installation)
- [Setup](#setup)
  - [Get Credentials](#get-credentials)
- [Configuration](#configuration)
  - [Priority](#priority)
  - [Environment Variables](#environment-variables)
  - [Config File](#config-file)
- [Quickstart](#quickstart)
  - [1. Find Available Data](#1-find-available-data)
  - [2. Search for Files](#2-search-for-files)
  - [3. Download Files](#3-download-files)
- [Core Concepts](#core-concepts)
  - [Catalogs](#catalogs)
  - [Registry](#registry)
  - [Data Organization](#data-organization)
- [Time Filtering](#time-filtering)
- [Workflows](#workflows)
  - [Direct Download (get)](#direct-download-get)
  - [Two-Step Workflow (search + download)](#two-step-workflow-search--download)
  - [Incremental Sync](#incremental-sync)
- [Common Tasks](#common-tasks)
  - [Download One Day of Data](#download-one-day-of-data)
  - [Download a Specific Orbit/Frame](#download-a-specific-orbitframe)
  - [Sync Recent Data](#sync-recent-data)
  - [Build Catalog Cache](#build-catalog-cache)
  - [Check Pending Downloads](#check-pending-downloads)
  - [Mark Files as Processed](#mark-files-as-processed)
- [Python API](#python-api)
  - [Basic Usage](#basic-usage)
  - [Search with Result Types](#search-with-result-types)
  - [Download with Result Types](#download-with-result-types)
  - [Day-by-Day Search](#day-by-day-search)
  - [Sync Workflow](#sync-workflow)
  - [State Tracking](#state-tracking)
- [CLI Reference](#cli-reference)
  - [Commands Overview](#commands-overview)
  - [Search Options](#search-options)
  - [Download Options](#download-options)
  - [Get Options](#get-options)
  - [Sync Options](#sync-options)
- [Other Missions](#other-missions)
- [Default Collections](#default-collections)
- [Troubleshooting](#troubleshooting)
- [Links](#links)
- [Contact](#contact)

---

## Installation

```bash
pip install git+https://github.com/bernat-earthfocus/maap_client.git
```

Or for development:

```bash
git clone https://github.com/bernat-earthfocus/maap_client.git
cd maap_client
pip install -e .
```

---

## Setup

### Get Credentials

1. Go to https://portal.maap.eo.esa.int/ini/services/auth/token/90dToken.php
2. Login with your ESA credentials
3. Request a 90-day offline token
4. Create `~/.maap/credentials.txt`:

```
CLIENT_ID=offline-token
CLIENT_SECRET=p1eL7uonXs6MDxtGbgKdPVRAmnGxHpVE
OFFLINE_TOKEN=<your_token>
```

> The token expires after 90 days and must be renewed from the ESA portal.

---

## Configuration

> **Important:** Configure paths and API settings before using the client. The defaults work for most users, but you may want to customize the data directory or use a different mission. Run `maap config` to verify your current configuration.

### Priority

Configuration is resolved in order (highest to lowest):
1. CLI arguments
2. Environment variables
3. Config file (`~/.maap/config.toml`)
4. Built-in defaults

### Environment Variables

- `MAAP_DATA_DIR` - Download directory
- `MAAP_CATALOG_DIR` - Catalog queryables directory
- `MAAP_BUILT_CATALOG_DIR` - Built catalogs directory
- `MAAP_REGISTRY_DIR` - Registry/state files directory
- `MAAP_CREDENTIALS_FILE` - Credentials file path
- `MAAP_CATALOG_URL` - MAAP catalog API URL
- `MAAP_MISSION_START` - Mission start date
- `MAAP_MISSION_END` - Mission end date

### Config File

Create `~/.maap/config.toml`:

```toml
[paths]
data_dir = "/data/earthcare/data"
catalog_dir = "/data/earthcare/catalogs"
built_catalog_dir = "/data/earthcare/built_catalogs"
registry_dir = "/data/earthcare/registry"
credentials_file = "~/.maap/credentials.txt"

[api]
catalog_url = "https://catalog.maap.eo.esa.int/catalogue"
token_url = "https://iam.maap.eo.esa.int/realms/esa-maap/protocol/openid-connect/token"

[mission]
name = "EarthCARE"
start = "2024-05-28T00:00:00Z"
end = "2045-12-31T23:59:59Z"
# collections = [...]        # Replace default collections
```

---

## Quickstart

### 1. Find Available Data

```bash
# What collections are available?
maap list

# What products are in L1 Validated?
maap list EarthCAREL1Validated_MAAP

# What baselines exist for CPR_NOM_1B?
maap list EarthCAREL1Validated_MAAP CPR_NOM_1B

# Verify baselines from API (live query)
maap list EarthCAREL1Validated_MAAP CPR_NOM_1B --verify

# Specific information about a baseline
maap list EarthCAREL1Validated_MAAP CPR_NOM_1B DA
```

### 2. Search for Files

```bash
# Search for CPR_NOM_1B data from a specific date
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B DA --date 2024-12-01T23:50:27Z

# Search by date
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B DA --date 2024-12-01

# Search by specific orbit+frame
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B DA --orbit 08962F

# Search with time range
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B DA \
  --start 2024-12-01 --end 2024-12-02

# Search last 7 days
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B DA --days-back 7
```

Output shows URLs found:
```
https://catalog.maap.eo.esa.int/data/earthcare-pdgs-01/EarthCARE/CPR_NOM_1B/DA/2024/12/01/.../ECA_JXDA_CPR_NOM_1B_...h5
```

### 3. Download Files

```bash
# Search and save URLs to a file
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B DA --date 2024-12-01 --url-file urls.txt

# Download to a specific directory
maap download EarthCAREL1Validated_MAAP CPR_NOM_1B DA --url-file urls.txt --out-dir ./

# Or use 'get' to search + download in one step
maap get EarthCAREL1Validated_MAAP CPR_NOM_1B DA --date 2024-12-01
```

---

## Core Concepts

### Catalogs

The client uses two types of local catalogs for **offline reference** and **faster searches**:

#### Queryables Catalogs (`./catalogs/`)

Schema information downloaded from the MAAP API:
- Contains available **products** and **baselines** for each collection
- Enables `maap list` to work without API calls
- Auto-downloaded on first use; refresh with `maap catalog update`

```bash
# Update queryables for a collection
maap catalog update EarthCAREL1Validated_MAAP

# Update all collections
maap catalog update
```

#### Built Catalogs (`./built_catalogs/`)

Comprehensive metadata summaries you build locally:
- Contains **time ranges**, **orbit ranges**, and **file counts** per baseline
- Enables `--use-catalog` for faster time-bounded searches
- Great for knowing "what data exists" without querying the API

```bash
# Build catalog for a collection
maap catalog build EarthCAREL1Validated_MAAP

# Build for specific product/baseline
maap catalog build EarthCAREL1Validated_MAAP CPR_NOM_1B DA

# Use catalog for faster search
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B DA --use-catalog --date 2024-12-01
```

> Rebuild periodically to keep catalogs current with new data.

### Registry

The registry is a **text-file based tracking system** for managing download workflows. It maintains state using daily files organized by the **sensing date** extracted from each file's name.

#### How Files Are Tracked

Each file progresses through three states:

1. **Discovered** (`urls/`) - URLs found during search
2. **Downloaded** (`downloads/`) - Files successfully downloaded
3. **Marked** (`marked/`) - Files processed by your pipeline

The tracker computes what's pending automatically:
- **Pending downloads** = Discovered URLs − Downloaded URLs
- **Pending marks** = Downloaded files − Marked files

#### File Structure

```
registry/
├── urls/{mission}/{collection}/{product}/{baseline}/{year}/
│   └── url_YYYYMMDD.txt      # URL|LOCAL_PATH (one per line)
├── downloads/{mission}/{collection}/{product}/{baseline}/{year}/
│   └── dwl_YYYYMMDD.txt      # URL|LOCAL_PATH (one per line)
├── marked/{mission}/{collection}/{product}/{baseline}/{year}/
│   └── mrk_YYYYMMDD.txt      # PATH only (one per line)
└── downloads/.../errors.txt  # URL|ERROR for failed downloads
```

Files are date-partitioned by sensing time for efficient filtering and manageable file sizes.

#### Workflow

1. **Search and save**: `maap search ... --registry-save` → creates `url_*.txt` files
2. **Download**: `maap download --registry ...` → reads URLs, writes `dwl_*.txt` on success
3. **Process**: Your pipeline processes files, then calls `maap state mark <path>`
4. **Cleanup**: `maap state cleanup ...` deletes marked files to free disk space

### Data Organization

Downloaded files are organized to **mirror the mission archive structure**:

```
data/{mission}/{collection}/{product}/{baseline}/YYYY/MM/DD/filename.h5
```

Example:
```
data/EarthCARE/EarthCAREL2Validated_MAAP/CPR_CLD_2A/BC/2024/12/01/
  ECA_EXBC_CPR_CLD_2A_20241201T123456Z_20241201T135958Z_07282E.h5
```

**Benefits:**
- Matches ESA's archive organization - intuitive navigation
- Different baselines are always separate (no overwrites)
- Easy to find data for a specific date
- Path is deterministic: given metadata, the location is predictable

### Time Filtering

Time filtering uses the **sensing time** (start of validity period) extracted from each product's filename.

#### Filename Convention

Product filenames contain two timestamps:
```
ECA_JXDA_CPR_NOM_1B_20241201T123456Z_20241201T135958Z_07282E.h5
                    ^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^^^
                    sensing_start    creation_time
```

- **sensing_start**: When the observation began (start of validity period)
- **creation_time**: When the file was processed/created

#### How Filtering Works

The STAC API indexes products by their **validity period** (start to end). When you search for a date range, the API returns products whose validity period overlaps with your range.

This client adds a post-filter step using only the **sensing_start** timestamp, so that each product is assigned to exactly one date and stored in the correct daily folder:

1. Query the STAC API with your time range (returns products with overlapping validity)
2. Post-filter by **sensing_start** extracted from filenames
3. Return only products whose sensing_start falls within your specified range

**Example**: A product sensed at 23:50 on December 31st with validity extending into January 1st:
- STAC API returns it for a January 1st search (validity overlaps)
- Client excludes it because sensing_start is December 31st

#### Data Organization

Files are organized and tracked by their **sensing date**:
```
data/EarthCARE/.../CPR_CLD_2A/BC/2024/12/01/
  ECA_EXBC_CPR_CLD_2A_20241201T123456Z_...h5
```

---

## Workflows

Choose the right workflow for your use case:

### Direct Download (get)

**Best for:** One-off downloads, quick data retrieval

```bash
maap get EarthCAREL1Validated_MAAP CPR_NOM_1B DA --date 2024-12-01
```

- Searches and downloads in one step
- No state tracking
- No catalog optimization
- Simple and fast

### Two-Step Workflow (search + download)

**Best for:** Production pipelines, large datasets, scheduled jobs

```bash
# Step 1: Search and save to registry
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B DA --date 2024-12-01 --registry-save

# Step 2: Download when ready (with state tracking)
maap download EarthCAREL1Validated_MAAP CPR_NOM_1B DA --registry --date 2024-12-01
```

Advantages:
- **Registry**: Save URLs for later; track what's downloaded
- **Catalog**: Use `--use-catalog` for faster searches
- **Flexibility**: Separate search from download timing
- **Resumable**: If interrupted, only downloads remaining files

### Incremental Sync

**Best for:** Scheduled data synchronization (cron jobs)

```bash
# Sync last 3 days (default)
maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A DA

# Run daily in crontab
0 6 * * * /path/to/maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A DA
```

Combines search + registry + download:
- Automatic state tracking
- Skips already-downloaded files
- Designed for unattended operation

---

## Common Tasks

### Download One Day of Data

```bash
# Search and save to registry files (tracks what's been downloaded)
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B DA --date 2024-12-01 --registry-save

# Download from registry
maap download EarthCAREL1Validated_MAAP CPR_NOM_1B DA --registry --date 2024-12-01
```

Files are organized by collection, product, baseline, and date:
```
data/EarthCARE/EarthCAREL1Validated_MAAP/CPR_NOM_1B/DA/2024/12/01/*.h5
```

### Download a Specific Orbit/Frame

```bash
# Find by orbit (e.g., orbit 07655, frame C)
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B --orbit 07655C

# Download immediately with get
maap get EarthCAREL1Validated_MAAP CPR_NOM_1B --orbit 07655C --out-dir ./
```

### Sync Recent Data

The `sync` command searches and downloads in one step with state tracking:

```bash
# Sync last 3 days (default)
maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A DA

# Sync last 7 days
maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A DA --days-back 7

# Sync a specific date
maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A DA --date 2024-12-01

# Sync a date range
maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A DA --start 2024-12-01 --end 2024-12-15
```

For cron jobs:

```bash
# Add to crontab (runs daily at 6 AM, syncs last 3 days)
0 6 * * * /path/to/maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A DA >> /var/log/maap-sync.log 2>&1
```

### Build Catalog Cache

```bash
# Build metadata catalog for a collection (one-time)
maap catalog build EarthCAREL1Validated_MAAP

# Build for specific product/baseline
maap catalog build EarthCAREL1Validated_MAAP CPR_NOM_1B DA

# Use cache for faster search (may be stale)
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B DA --use-catalog
```

Rebuild periodically to keep the cache current.

### Check Pending Downloads

```bash
# Show state summary
maap state show EarthCAREL1Validated_MAAP CPR_NOM_1B DA

# List pending download URLs
maap state pending EarthCAREL1Validated_MAAP CPR_NOM_1B DA --type downloads

# List pending marks (files downloaded but not processed)
maap state pending EarthCAREL1Validated_MAAP CPR_NOM_1B DA --type marks
```

### Mark Files as Processed

```bash
# After processing files, mark them
maap state mark data/EarthCARE/.../file1.h5

# Preview cleanup (dry run)
maap state cleanup EarthCAREL1Validated_MAAP CPR_NOM_1B DA --dry-run

# Delete marked files to free space
maap state cleanup EarthCAREL1Validated_MAAP CPR_NOM_1B DA
```

---

## Python API

### Basic Usage

```python
from maap_client import MaapClient
from datetime import datetime, timezone

client = MaapClient()

# Browse collections and products
collections = client.list_collections()
products = client.list_products("EarthCAREL1Validated_MAAP")
baselines = client.list_baselines("EarthCAREL1Validated_MAAP", "CPR_NOM_1B")

# Verify baselines from API
baselines = client.list_baselines(
    "EarthCAREL1Validated_MAAP", "CPR_NOM_1B", verify=True
)
```

### Search with Result Types

```python
from maap_client import MaapClient, SearchResult
from datetime import datetime, timezone

client = MaapClient()

# Time-based search (returns SearchResult)
result: SearchResult = client.search(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
    start=datetime(2024, 12, 1, tzinfo=timezone.utc),
    end=datetime(2024, 12, 31, tzinfo=timezone.utc),
)
print(f"Found {result.total_count} URLs")
print(f"Baselines: {result.baselines_found}")

# Search all baselines (omit baseline parameter)
result = client.search(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    start=datetime(2024, 12, 1, tzinfo=timezone.utc),
)

# Orbit-based search
result = client.search(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    orbit="08962F",
)
```

### Download with Result Types

```python
from maap_client import MaapClient, DownloadResult

client = MaapClient()

# Download from search results
result: DownloadResult = client.download(
    urls=search_result.urls,
    collection="EarthCAREL2Validated_MAAP",
)
print(f"Downloaded {len(result.downloaded)} files")
print(f"Skipped {len(result.skipped)} existing files")
print(f"Errors: {result.errors}")

# Download to flat directory
result = client.download(
    urls=search_result.urls,
    collection="EarthCAREL2Validated_MAAP",
    out_dir=Path("./downloads"),
)

# Search + download in one step with get()
result = client.get(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
    start=datetime(2024, 12, 1, tzinfo=timezone.utc),
)
```

### Day-by-Day Search

For large date ranges, use the day-by-day generator for reliability:

```python
from maap_client import MaapClient
from datetime import datetime, timezone

client = MaapClient()

for day_urls in client.searcher.search_urls_iter_day(
    collection="EarthCAREL1Validated_MAAP",
    product_type="CPR_NOM_1B",
    baseline="DA",
    start=datetime(2024, 6, 1, tzinfo=timezone.utc),
    end=datetime(2024, 12, 31, tzinfo=timezone.utc),
    verbose=True,
):
    print(f"Found {len(day_urls)} URLs for this day")
    # Process or download day_urls
```

### Sync Workflow

```python
from maap_client import MaapClient, SyncResult
from datetime import datetime, timezone

client = MaapClient()

# Incremental sync with automatic state tracking
result: SyncResult = client.sync(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
)
print(f"Found {result.urls_found} URLs")
print(f"Downloaded {result.urls_downloaded} files")
print(f"Errors: {result.errors}")

# Sync with time range
result = client.sync(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
    start=datetime(2024, 12, 1, tzinfo=timezone.utc),
    end=datetime(2024, 12, 31, tzinfo=timezone.utc),
)
```

### State Tracking

```python
from maap_client import MaapClient

client = MaapClient()

# Get tracker for a product/baseline
tracker = client.get_tracker(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
)

# Check pending downloads
pending = tracker.get_pending_downloads()
print(f"Pending: {len(pending)} files")

# Check pending marks
pending_marks = tracker.get_pending_mark_paths()

# Mark files as processed (for cleanup)
tracker.mark("/path/to/file.h5")
```

---

## CLI Reference

### Commands Overview

```
maap list [collection [product [baseline]]]   Browse collections/products/baselines
maap search <coll> <prod> [bl] [options]      Search for product URLs
maap download <coll> <prod> [bl] [options]    Download products
maap get <coll> <prod> [bl] [options]         Search + download in one step
maap sync <coll> <prod> [bl] [options]        Incremental sync (for crontab)
maap state show <coll> <prod> <bl>            Show state summary
maap state pending <coll> <prod> <bl>         List pending items
maap state mark <paths>                       Mark files as processed
maap state cleanup <coll> <prod> <bl>         Delete marked files
maap catalog update [collection]              Update catalog queryables
maap catalog build [collection]               Build metadata cache
maap config                                   Show configuration
```

Use `maap <command> -h` for detailed help on any command.

### Search Options

```bash
maap search <collection> <product> [baseline] [options]

Filtering (mutually exclusive):
  --date YYYY-MM-DD        Single day (expands to 00:00:00-23:59:59)
  --start, -s DATETIME     Start of range (ISO format)
  --end, -e DATETIME       End of range (use with --start)
  --days-back, -d N        Days to look back from now
  --orbit NNNNNX           Search by orbit+frame (e.g., 07655C)

Output:
  --url-file, -o FILE      Save URLs to flat file
  --registry-save          Save URLs to registry files (by sensing date)

Other:
  --max-items, -n N        Maximum items to return (default: 50000)
  --use-catalog            Use built catalog (faster, may be stale)
```

### Download Options

```bash
maap download <collection> <product> [baseline] [options]

Source (mutually exclusive):
  (default)                Search MAAP API
  --url, -u URL            Download single URL
  --url-file, -f FILE      Download from URL file
  --registry               Download from registry files

Filtering (with --registry):
  --date YYYY-MM-DD        Filter by date
  --start, -s / --end, -e  Filter by range
  --days-back, -d N        Days to look back

Output:
  --out-dir, -o DIR        Custom output directory
  --dry-run                Show what would be downloaded

Other:
  --max-items, -n N        Maximum items to download
  --use-catalog            Use built catalog for time bounds
```

### Get Options

```bash
maap get <collection> <product> [baseline] [options]

Filtering (mutually exclusive):
  --date YYYY-MM-DD        Single day
  --start, -s / --end, -e  Time range
  --days-back, -d N        Days to look back
  --orbit NNNNNX           Orbit+frame

Output:
  --out-dir, -o DIR        Custom output directory
  --dry-run                Show what would be downloaded

Other:
  --max-items, -n N        Maximum items to get (default: 50000)
```

### Sync Options

```bash
maap sync <collection> <product> [baseline] [options]

Time selection (mutually exclusive):
  --days-back, -d N        Days to look back (default: 3)
  --date YYYY-MM-DD        Sync a single day
  --start, -s DATETIME     Start of range (ISO format)
  --end, -e DATETIME       End of range (defaults to now)

Other:
  --max-items, -n N        Max items per run (default: 50000)
  --out-dir, -o DIR        Custom output directory
```

---

## Other Missions

The client is designed for EarthCARE but can be configured for other ESA missions available on the MAAP platform, such as Aeolus.

### Configuration

To use a different mission, update `~/.maap/config.toml`:

```toml
[mission]
name = "Aeolus"
start = "2018-08-22T00:00:00Z"
end = "2023-04-30T23:59:59Z"
collections = [
    "AeolusL1BProducts",
    "AeolusL2AProducts",
    "AeolusL2BProducts",
    "AeolusL2CProducts",
    "AeolusAuxProducts",
]
```

Then use the CLI normally:

```bash
maap list AeolusL1BProducts
maap search AeolusL1BProducts ALD_U_N_1B --date 2023-04-22
```

> **Note:** Other missions may be compatible but could require manual adjustments due to different product naming conventions, file formats, and metadata structures.

---

## Default Collections

By default, the client is configured for EarthCARE mission data:

| Collection | Description |
|------------|-------------|
| EarthCAREL0L1Products_MAAP | Level 0/1 products |
| EarthCAREL1InstChecked_MAAP | L1 instrument-checked |
| EarthCAREL1Validated_MAAP | L1 validated |
| EarthCAREL2InstChecked_MAAP | L2 instrument-checked |
| EarthCAREL2Products_MAAP | L2 products |
| EarthCAREL2Validated_MAAP | L2 validated |
| EarthCAREAuxiliary_MAAP | Auxiliary data |
| EarthCAREOrbitData_MAAP | Orbit data |
| EarthCAREXMETL1DProducts10_MAAP | XMET L1D products |
| JAXAL2InstChecked_MAAP | JAXA L2 instrument-checked |
| JAXAL2Products_MAAP | JAXA L2 products |
| JAXAL2Validated_MAAP | JAXA L2 validated |

---

## Troubleshooting

**Token expired:**
```
AuthenticationError: Failed to refresh token: 401 Unauthorized
```
Get a new token from https://portal.maap.eo.esa.int/ini/services/auth/token/90dToken.php

**Credentials not found:**
```
CredentialsError: Credentials file not found
```
Create `~/.maap/credentials.txt` with your credentials.

**No data found:**
Check available baselines with `maap list <collection> <product>` and verify your date range.

**Timezone error:**
```
InvalidRequestError: 'start' must be timezone-aware
```
Always use timezone-aware datetimes in Python:
```python
from datetime import datetime, timezone
start = datetime(2024, 12, 1, tzinfo=timezone.utc)
```

**Catalog not found:**
```
FileNotFoundError: Built catalog not found for ...
```
Build the catalog first:
```bash
maap catalog build <collection>
```

---

## Links

- ESA MAAP Portal: https://portal.maap.eo.esa.int
- MAAP Catalog: https://catalog.maap.eo.esa.int
- Token Request: https://portal.maap.eo.esa.int/ini/services/auth/token/90dToken.php

---

## Contact

Report issues or comments to info [at] earthfocus [dot] io
