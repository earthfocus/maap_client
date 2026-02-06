# Search Documentation

This document describes both the **CLI search command** (`maap search`) and the **Python search module** (`maap_client/search.py`).

## Table of Contents

1. [CLI Command Reference](#cli-command-reference)
   - [Basic Usage](#basic-usage)
   - [All Options](#all-options)
   - [Examples](#examples)
   - [Output Modes](#output-modes)
   - [Catalog Optimization](#catalog-optimization)
2. [Python API Reference](#python-api-reference)
   - [MaapSearcher Class](#maapsearcher-methods)
   - [Method Reference](#method-reference-table)

---

# CLI Command Reference

## Basic Usage

```bash
maap search <collection> <product> [baseline] [options]
```

**Required Arguments:**
- `collection`: Collection name (e.g., `EarthCAREL2Validated_MAAP`)
- `product`: Product type (e.g., `CPR_CLD_2A`)

**Optional Arguments:**
- `baseline`: Baseline version (e.g., `BC`, `BD`). If omitted, searches all baselines.

## All Options

### Time Filtering (Mutually Exclusive)

Choose ONE of these time filtering options:

| Option | Description | Example |
|--------|-------------|---------|
| `--date DATE` | Search a single day (YYYY-MM-DD) or exact datetime | `--date 2025-12-25` |
| `--start START` | Start datetime (use with `--end`) | `--start 2024-06-01` |
| `--end END` | End datetime (use with `--start`) | `--end 2024-12-31` |
| `--orbit ORBIT` | Orbit+frame search (e.g., '08962F') | `--orbit 08962F` |

**Default behavior:** If no time filter specified, searches from mission start to current date.

### Output Options

| Option | Description | Default |
|--------|-------------|---------|
| `--url-file FILE`, `-o FILE` | Save URLs to a flat file | Print to stdout |
| `--registry-save` | Save URLs to partitioned registry files | Disabled |

### Other Options

| Option | Description | Default |
|--------|-------------|---------|
| `--max-items N`, `-n N` | Maximum items per time-based search | 50000 |
| `--use-catalog` | Use built catalog for time bounds (faster) | Disabled |
| `--quiet` | Suppress non-error output | Verbose output |
| `-v`, `--verbose` | Increase verbosity (-v, -vv) | Normal |

## Examples

### Basic Search

```bash
# Search all baselines for a single day
maap search EarthCAREL0L1Products_MAAP CPR_NOM_1B --date 2025-12-25
```

**Output:**
```
Searching EarthCAREL0L1Products_MAAP/CPR_NOM_1B...
2025-12-25T00:00:00Z
2025-12-25T23:59:59Z
[1/1] 2025-12-25T00:00:00Z -> 2025-12-25T23:59:59Z... found 124
https://catalog.maap.eo.esa.int/stac/.../file1.h5
https://catalog.maap.eo.esa.int/stac/.../file2.h5
...
```

### Search with Baseline

```bash
# Search specific baseline
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --date 2025-12-25
```

**Output:**
```
Searching EarthCAREL2Validated_MAAP/CPR_CLD_2A/BC...
2025-12-25T00:00:00Z
2025-12-25T23:59:59Z
[1/1] 2025-12-25T00:00:00Z -> 2025-12-25T23:59:59Z... found 87 (BC)
https://catalog.maap.eo.esa.int/stac/.../file1.h5
...
```

### Date Range Search

```bash
# Search with start and end dates
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B --start 2024-06-01 --end 2024-12-31
```

**Output:**
```
Searching EarthCAREL1Validated_MAAP/CPR_NOM_1B...
2024-06-01T00:00:00Z
2024-12-31T00:00:00Z
[1/214] 2024-06-01T00:00:00Z -> 2024-06-01T23:59:59Z... found 142
[2/214] 2024-06-02T00:00:00Z -> 2024-06-02T23:59:59Z... found 139
...
[214/214] 2024-12-31T00:00:00Z -> 2024-12-31T23:59:59Z... found 145
https://catalog.maap.eo.esa.int/stac/.../file1.h5
...
```

### Orbit-Based Search

```bash
# Search by orbit and frame
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B --orbit 08962F
```

**Output:**
```
Found 5 URLs for orbit 08962F
https://catalog.maap.eo.esa.int/stac/.../file1.h5
...
```

### Save to File

```bash
# Save URLs to a file instead of printing to stdout
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --date 2025-12-25 --url-file urls.txt
```

**Output:**
```
Searching EarthCAREL2Validated_MAAP/CPR_CLD_2A/BC...
2025-12-25T00:00:00Z
2025-12-25T23:59:59Z
[1/1] 2025-12-25T00:00:00Z -> 2025-12-25T23:59:59Z... found 87 (BC)
Wrote 87 URLs to urls.txt
```

**File format (urls.txt):**
```
https://catalog.maap.eo.esa.int/stac/.../file1.h5
https://catalog.maap.eo.esa.int/stac/.../file2.h5
...
```

### Save to Registry

```bash
# Save URLs to partitioned registry files (organized by date)
maap search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --start 2024-06-12 --registry-save
```

**Output:**
```
Searching EarthCAREL0L1Products_MAAP/CPR_NOM_1B/DA...
2024-06-12T00:00:00Z
2024-12-30T22:59:25Z
Resolving temporal coverage for DA...
2024-06-12T00:00:00Z
2024-12-30T13:13:18Z
[1/202] 2024-06-12T00:00:00Z -> 2024-06-12T23:59:59Z... found 80 (DA)
[2/202] 2024-06-13T00:00:00Z -> 2024-06-13T23:59:59Z... found 142 (DA)
...
Saved 28456 new URLs (28456 total) to 202 files in registry/urls/EarthCARE/EarthCAREL0L1Products_MAAP/CPR_NOM_1B/DA
```

**Registry structure:**
```
registry/urls/EarthCARE/EarthCAREL0L1Products_MAAP/CPR_NOM_1B/DA/
├── 2024/
│   ├── url_20240612.txt
│   ├── url_20240613.txt
│   └── ...
└── 2025/
    └── url_20251225.txt
```

**Registry file format (URL|PATH):**
```
https://.../file1.h5|/data/EarthCARE/.../2024/06/12/file1.h5
https://.../file2.h5|/data/EarthCARE/.../2024/06/12/file2.h5
...
```

### Use Catalog Optimization

```bash
# Use pre-built catalog for faster searches (requires catalog to be built first)
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2024-06-01 --end 2024-12-31 --use-catalog
```

**Output:**
```
Searching EarthCAREL2Validated_MAAP/CPR_CLD_2A/BC...
Using cached temporal coverage for BC...
2024-06-12T04:52:41Z
2024-12-30T13:24:09Z
[1/202] 2024-06-12T04:52:41Z -> 2024-06-12T23:59:59Z... found 81 (BC)
...
```

## Output Modes

### 1. Standard Output (default)

Prints URLs to stdout:

```bash
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --date 2025-12-25
```

**Use case:** Pipe to other commands
```bash
maap search ... | head -10
maap search ... | wc -l
maap search ... | xargs -I {} curl -O {}
```

### 2. URL File (`--url-file`)

Saves URLs to a flat file:

```bash
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --date 2025-12-25 --url-file urls.txt
```

**File format:**
```
URL
URL
...
```

**Use case:**
- Share URL list with others
- Download later: `maap download --url-file urls.txt -c EarthCAREL2Validated_MAAP`

### 3. Registry Save (`--registry-save`)

Saves URLs to partitioned registry files organized by sensing date:

```bash
maap search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --start 2024-06-01 --registry-save
```

**File format:**
```
URL|LOCAL_PATH
URL|LOCAL_PATH
...
```

**Structure:**
```
registry/urls/{mission}/{collection}/{product}/{baseline}/{year}/url_YYYYMMDD.txt
```

**Use case:**
- Track what's available on the server
- Download from state: `maap download --registry -c ... -p ... -b ...`
- Incremental updates (avoids duplicates)

## Catalog Optimization

### What is `--use-catalog`?

The `--use-catalog` flag enables the use of pre-built catalog files to optimize search performance.

**Without `--use-catalog` (default):**
```bash
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2024-06-01 --end 2024-12-31
```
1. Makes API call to `search_product_info_range()` to get actual data bounds
2. Intersects API-returned bounds with user dates
3. Searches within the intersection

⏱️ **Slower** (API roundtrip) but always up-to-date

**With `--use-catalog`:**
```bash
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2024-06-01 --end 2024-12-31 --use-catalog
```
1. Reads time bounds from local catalog file: `built_catalogs/EarthCAREL2Validated_MAAP_collection.json`
2. Uses cached `time_start` and `time_end` values (no API call!)
3. Intersects cached bounds with user dates
4. Searches within the intersection
5. If catalog not found → falls back to API query

⚡ **Faster** (no API call) but may be stale if catalog not recently updated

### Catalog File Format

```json
{
  "collection": "EarthCAREL2Validated_MAAP",
  "products": {
    "CPR_CLD_2A": {
      "baselines": {
        "BC": {
          "time_start": "2024-06-12T04:52:41Z",
          "time_end": "2024-12-30T13:24:09Z",
          "count": 16789,
          "updated_at": "2024-12-30T12:00:00Z"
        },
        "BD": {
          "time_start": "2024-11-01T00:00:00Z",
          "time_end": "2024-12-30T23:59:59Z",
          "count": 4521,
          "updated_at": "2024-12-30T12:00:00Z"
        }
      }
    }
  }
}
```

### When Catalog Optimization Applies

✅ **Optimization IS used when:**
- Baseline is explicitly specified
- Date range > 30 days
- `--use-catalog` flag is present
- Catalog file exists for the collection

❌ **Optimization is NOT used when:**
- No baseline specified (searches all baselines)
- Short period (≤ 30 days)
- No `--use-catalog` flag
- Catalog file doesn't exist (falls back to API)

### Building Catalogs

Before using `--use-catalog`, build the catalog:

```bash
# Build catalog for a collection
maap catalog build EarthCAREL2Validated_MAAP

# Build for specific product
maap catalog build EarthCAREL2Validated_MAAP CPR_CLD_2A

# Build for specific baseline
maap catalog build EarthCAREL2Validated_MAAP CPR_CLD_2A BC
```

See [CATALOG_BUILD.md](CATALOG_BUILD.md) for catalog building details.

### Benefits of `--use-catalog`

| Benefit | Description |
|---------|-------------|
| ⚡ **Faster** | No API roundtrip to get time bounds |
| 📉 **Reduced API load** | Fewer requests to MAAP servers |
| 🔌 **Works offline** | Once catalog is built, searches work without network |

### Limitations of `--use-catalog`

| Limitation | Description |
|------------|-------------|
| ⚠️ **May be stale** | Catalog needs periodic updates via `maap catalog build` |
| 🎯 **Requires baseline** | Only works when baseline is explicitly specified |
| 🔄 **Cache miss fallback** | Falls back to API query if catalog not found |

### Example: Cache Hit vs Cache Miss

**Cache Hit** (catalog exists):
```bash
$ maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2024-06-01 --end 2024-12-31 --use-catalog
Searching EarthCAREL2Validated_MAAP/CPR_CLD_2A/BC...
Using cached temporal coverage for BC...  # ← Cache hit!
2024-06-12T04:52:41Z
2024-12-30T13:24:09Z
[1/202] ...
```

**Cache Miss** (catalog doesn't exist):
```bash
$ maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2024-06-01 --end 2024-12-31 --use-catalog
Searching EarthCAREL2Validated_MAAP/CPR_CLD_2A/BC...
No cache found for CPR_CLD_2A/BC, querying API...  # ← Cache miss, falls back
Resolving temporal coverage for BC...
2024-06-12T04:52:41Z
2024-12-30T13:24:09Z
[1/202] ...
```

## Mutual Exclusivity

Some options cannot be used together:

| Option 1 | Option 2 | Why |
|----------|----------|-----|
| `--date` | `--start` | Date already specifies time range |
| `--orbit` | `--date` | Orbit search doesn't use time filtering |
| `--orbit` | `--start` | Orbit search doesn't use time filtering |

**Example (ERROR):**
```bash
$ maap search EarthCAREL2Validated_MAAP CPR_CLD_2A --date 2025-12-25 --start 2024-06-01
Error: argument --start: not allowed with argument --date
```

## Default Behavior

When no time filter is specified:

```bash
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC
```

Defaults to:
- **Start**: Mission start date (`2024-05-28T00:00:00Z`)
- **End**: Current datetime

---

# Python API Reference

## Overview

The `search.py` module provides STAC (SpatioTemporal Asset Catalog) search operations for querying the MAAP catalog. It includes:

- `MaapSearcher` - Main search class

Time ranges are represented as `tuple[datetime, datetime]` (start, end).

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         MaapSearcher                            │
│                                                                 │
│  Wraps pystac_client for STAC API queries                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MAAP STAC Catalog API                        │
│                                                                 │
│  POST https://catalog.maap.eo.esa.int/catalogue/search          │
│                                                                 │
│  CQL2 filters:                                                  │
│  - productType = 'CPR_CLD_2A'                                   │
│  - productVersion = 'BC'                                        │
│  - orbitNumber = 7282                                           │
│  - frame = 'E'                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      STAC Items                                 │
│                                                                 │
│  Each item has:                                                 │
│  - id: unique item identifier                                   │
│  - datetime: sensing time                                       │
│  - properties: productType, productVersion, orbitNumber, etc.   │
│  - assets: enclosure_h5 → download URL                          │
└─────────────────────────────────────────────────────────────────┘
```

## Data Structures

### Time Range

Time ranges are represented as simple tuples: `tuple[datetime, datetime]` where index 0 is the start and index 1 is the end.

**Usage:**

```python
from datetime import datetime, timezone

# Time range as a tuple
time_range = (
    datetime(2024, 12, 1, tzinfo=timezone.utc),
    datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
)
start, end = time_range  # Unpack
print(f"{time_range[0]} to {time_range[1]}")
```

## MaapSearcher Methods

### Initialization

```python
from maap_client.search import MaapSearcher

searcher = MaapSearcher()
# or
searcher = MaapSearcher(catalog_url="https://catalog.maap.eo.esa.int/catalogue")
```

### search_has_any_product()

Check if any data exists for a product+baseline.

```python
def search_has_any_product(
    self,
    collection: str,
    product_type: str,
    baseline: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> bool:
```

```python
exists = searcher.search_has_any_product(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
)
# Returns: True/False
```

### search_baselines()

Get baselines that actually have data, with optional mode to get only the latest.

```python
def search_baselines(
    self,
    collection: str,
    product_type: str,
    candidates: Optional[list[str]] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    mode: Literal["all", "latest"] = "all",
) -> list[str]:
```

```python
# Get all baselines with data
baselines = searcher.search_baselines(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
)
# Returns: ['BC', 'BD']  # Only baselines with actual data

# Get latest baseline only
latest = searcher.search_baselines(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    mode="latest",
)
# Returns: ['BD']  # Single-element list with latest baseline
```

### search_product_info_range()

Find the first and last granules for a product+baseline.

```python
def search_product_info_range(
    self,
    collection: str,
    product_type: str,
    baseline: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    verbose: bool = False,
) -> Optional[tuple[GranuleInfo, GranuleInfo]]:
```

Uses **binary search** to efficiently find first/last days with data. Returns a tuple of `(first_granule, last_granule)` with full metadata including sensing time, orbit, and baseline.

```python
info_range = searcher.search_product_info_range(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
)
# Returns: (first_granule, last_granule) or None
if info_range:
    first, last = info_range
    print(f"Data from {first.sensing_time} to {last.sensing_time}")
```

### search_urls()

Get download URLs for matching products.

```python
def search_urls(
    self,
    collection: str,
    product_type: str,
    baseline: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    max_items: int = 50000,
) -> list[str]:
```

```python
urls = searcher.search_urls(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
    start=start,
    end=end,
)
# Returns: ['https://...file1.h5', 'https://...file2.h5', ...]
```

**Note:** Results are sorted by sensing time (extracted from filename).

### search_product_count()

Count matching products without fetching all items.

```python
def search_product_count(
    self,
    collection: str,
    product_type: str,
    baseline: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> int:
```

```python
count = searcher.search_product_count(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
)
# Returns: 50000
```

### search_urls_by_orbit()

Search by orbit number and frame.

```python
def search_urls_by_orbit(
    self,
    collection: str,
    product_type: str,
    orbit_frame: str | OrbitFrame,
    baseline: Optional[str] = None,
) -> list[str]:
```

```python
urls = searcher.search_urls_by_orbit(
    collection="EarthCAREL1Validated_MAAP",
    product_type="CPR_NOM_1B",
    orbit_frame="07282E",
    baseline="BC",
)
```

### search_urls_iter_day()

Generator for day-by-day searching.

```python
def search_urls_iter_day(
    self,
    collection: str,
    product_type: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    baseline: Optional[str] = None,
    max_items: int = 50000,
    verbose: bool = False,
) -> Iterator[list[str]]:
```

```python
for day_urls in searcher.search_urls_iter_day(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    start=datetime(2024, 6, 1, tzinfo=timezone.utc),
    end=datetime(2024, 12, 31, tzinfo=timezone.utc),
    baseline="BC",
):
    print(f"Found {len(day_urls)} URLs for this day")
    # Process incrementally...
```

## Method Reference Table

| Method | Input | Output | Use Case |
|--------|-------|--------|----------|
| `search_has_any_product()` | product+baseline | `bool` | Check if data exists |
| `search_baselines()` | product (+mode) | `list[str]` | List baselines with data |
| `search_product_info_range()` | product+baseline | `Optional[tuple[GranuleInfo, GranuleInfo]]` | Find first/last granules |
| `search_urls()` | product+baseline+time | `list[str]` | Get download URLs |
| `search_product_count()` | product+baseline+time | `int` | Count without fetching |
| `search_urls_by_orbit()` | product+orbit | `list[str]` | Search by orbit |
| `search_urls_iter_day()` | product+baseline+time | `Iterator[list[str]]` | Incremental day-by-day search |

## STAC Query Details

### Filter Syntax

The module uses CQL2 filters for STAC queries:

```python
# Product + baseline filter
filter = "productType = 'CPR_CLD_2A' AND productVersion = 'BC'"

# With orbit
filter = "productType = 'CPR_CLD_2A' AND orbitNumber = 7282 AND frame = 'E'"
```

### Enclosure URL Extraction

Products have various asset types. The module looks for enclosure assets:

```python
def get_enclosure_url(item) -> Optional[str]:
    # Priority: enclosure_h5, enclosure_zip, enclosure, then any enclosure_*
```

### Sensing Time Filtering

By default, results are filtered by sensing time (first timestamp in filename):

```python
# STAC API returns files where ANY part overlaps the time range
# Post-filtering ensures sensing START is within range
if filter_by_sensing_time and time_range:
    sensing_start = extract_sensing_time(filename)
    if sensing_start < time_range.start or sensing_start > time_range.end:
        continue  # Skip
```

## Dependencies

| Import | From | Purpose |
|--------|------|---------|
| `pystac_client.Client` | pystac_client | STAC API client |
| `DEFAULT_CATALOG_URL`, `DEFAULT_MISSION_START`, `DEFAULT_MISSION_END` | constants.py | Defaults |
| `CatalogError` | exceptions.py | Error handling |
| `extract_sensing_time` | paths.py | Parse filenames |
| `to_zulu`, `parse_datetime` | utils.py | Datetime conversion |

## Design Decisions

### Why pystac_client?

1. **Standard**: Official STAC client library
2. **Pagination**: Handles large result sets automatically
3. **Validation**: Validates responses against STAC spec
4. **Flexibility**: Supports various STAC API extensions

### Why Day-by-Day Search?

1. **Reliability**: Single large queries can timeout
2. **Incremental**: Process results as they arrive
3. **Resumable**: If day 50 fails, days 1-49 are done
4. **Progress**: Users see feedback for long searches

### Why Binary Search for Time Range?

Finding data bounds could require O(n) queries. Binary search:
1. **Efficiency**: O(log n) queries instead
2. **Accuracy**: Finds exact first/last days
3. **Robust**: Handles sparse data gracefully

### Why Filter by Sensing Time?

STAC datetime matches if ANY part of the file overlaps:
```
Query: 2024-12-01 to 2024-12-01
File:  sensing 2024-11-30T23:30:00 to 2024-12-01T00:30:00
       ↑ overlaps, but sensing START is Nov 30!
```

Post-filtering ensures files are returned based on when sensing actually started.

## File Location

| File | Purpose |
|------|---------|
| `maap_client/search.py` | This module |
