# Catalog Build Module

The catalog build module (`maap_client/catalog_build.py`) creates JSON metadata files that summarize available data for each collection. These catalogs enable quick offline reference without querying the MAAP API.

## Class Hierarchy

All catalog classes inherit from the `Catalog` base class (in `catalog.py`):

```
Catalog (base class)
├── to_dict()       # Recursive serialization with datetime/nested object handling
├── from_dict()     # Type-hint-aware deserialization
├── get() / set()   # Dual-mode property access (properties dict or attributes)
│
├── CatalogQueryables (catalog_query.py)
│   └── from_json() - STAC schema parsing
│
├── CatalogCollection (catalog_build.py)
│   ├── list_products() -> list[str]
│   ├── get_product(name) -> ProductInfo
│   └── set_product(name, info)
│
├── ProductInfo (catalog_build.py)
│   ├── list_baselines() -> list[str]
│   ├── get_baseline(name) -> BaselineInfo
│   └── set_baseline(name, info)
│
└── BaselineInfo (catalog_build.py)
    └── time_range() -> tuple[datetime, datetime]
```

## Purpose

A built catalog provides a snapshot of:
- **Which products** are available in a collection
- **Which baselines** exist for each product
- **Time range** of available data (first to last sensing time)
- **Orbit/frame range** (first and last orbit identifiers)
- **Product count** (total number of files)

This is useful for:
- Quick data availability checks without API calls
- Planning download jobs based on available date ranges
- Monitoring data ingestion progress over time

## Output Format

Catalogs are saved to `{built_catalog_dir}/{collection}_collection.json` (default: `./built_catalogs/`, configurable via `~/.maap/config.toml`):

```json
{
  "schema": "1.0",
  "generated_at": "2025-12-27T10:00:00Z",
  "collection": "EarthCAREL2Validated_MAAP",
  "client": {
    "name": "maap_client",
    "version": "0.1.0"
  },
  "products": {
    "CPR_CLD_2A": {
      "baselines": {
        "BC": {
          "time_start": "2024-06-12T12:02:32Z",
          "time_end": "2025-12-27T03:24:46Z",
          "frame_start": "00228H",
          "frame_end": "08981B",
          "count": 50000,
          "updated_at": "2025-12-27T10:00:00Z"
        },
        "BA": {
          "time_start": "2024-06-18T00:15:00Z",
          "time_end": "2024-09-02T18:30:00Z",
          "frame_start": "00300A",
          "frame_end": "02500F",
          "count": 6094,
          "updated_at": "2025-12-27T10:00:00Z"
        }
      }
    }
  }
}
```

## How It Works

For each product+baseline combination, the build process:

### Step 1: Find Time Range via Binary Search

```
get_time_range(collection, product, baseline)
```

Uses binary search to efficiently find the first and last **days** with data:

```
Mission start ──────────────────────────────────── Now
                    ↓ binary search
              [first day with data] ... [last day with data]
```

Then queries those specific days to extract the exact sensing times from filenames:
- `time_start`: Sensing time of the first file
- `time_end`: Sensing time of the last file

If filename parsing fails (e.g., L0 products with different naming), falls back to day boundaries (`00:00:00` / `23:59:59`).

### Step 2: Get Count from STAC API

```
count = searcher.search_product_count(collection, product, baseline)
```

Calls the STAC API with `max_items=1` and reads the `numberMatched` header. This returns the total count without fetching all items - very efficient.

### Step 3: Extract Orbit/Frame from First and Last Files

```
first_urls = search_urls(..., start=first_day, end=first_day, max_items=1)
last_urls = search_urls(..., start=last_day, end=last_day, max_items=100)
```

Searches the **full first day** and **full last day** to find:
- First file → extract `frame_start` from filename (e.g., "00228H")
- Last file → extract `frame_end` from filename (e.g., "08981B")

Why full day instead of narrow window? If `get_time_range()` couldn't parse the exact sensing time and fell back to `00:00:00` or `23:59:59`, a narrow 2-hour window around that fallback time would miss the actual files. Searching the full day guarantees we find them.

## Visual Summary

```
                    Binary Search
                         ↓
Day 1    Day 2    ...    Day N-1    Day N
  ↓                                   ↓
[file1, file2, ...]              [..., fileN-1, fileN]
  ↓                                             ↓
  └── First file ────────────────── Last file ──┘
      time_start                    time_end
      frame_start                   frame_end

STAC API → count (from numberMatched header)
```

## CLI Usage

```bash
# Build catalog for a collection
maap catalog build EarthCAREL2Validated_MAAP

# Build for specific product
maap catalog build EarthCAREL2Validated_MAAP CPR_CLD_2A

# Update only the latest baseline per product (faster for incremental updates)
maap catalog build EarthCAREL2Validated_MAAP --latest-baseline

# Specify output directory
maap catalog build EarthCAREL2Validated_MAAP --out-dir ./catalogs/
```

## Incremental Updates

When `--latest-baseline` is used:
1. Loads existing catalog from disk
2. For each product, identifies the baseline with the most recent `time_end`
3. Only re-fetches metadata for that baseline
4. Preserves metadata for other baselines

This is useful for keeping catalogs up-to-date when new data arrives, without re-querying all historical baselines.

## Python API

### Via MaapClient (Recommended)

```python
from maap_client import MaapClient

client = MaapClient()

# Build catalog (returns dict of collection → path)
paths = client.build_catalog(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",        # Optional: limit to specific product
    latest_baseline=False,
    verbose=True,
)

# Get baseline info from built catalog
info = client.get_baseline_info(
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
    from_built=True,
)
if info:
    print(f"Count: {info.count}")
    print(f"Time: {info.time_start} to {info.time_end}")
```

### Direct Catalog Classes

```python
from maap_client.catalog_build import CatalogCollection, ProductInfo, BaselineInfo

# Access catalog data using class methods
for product_name in catalog.list_products():
    product_info = catalog.get_product(product_name)
    for baseline_name in product_info.list_baselines():
        baseline_info = product_info.get_baseline(baseline_name)
        print(f"{product_name}/{baseline_name}: {baseline_info.count} files")
        print(f"  Time: {baseline_info.time_start} to {baseline_info.time_end}")
        print(f"  Frames: {baseline_info.frame_start} to {baseline_info.frame_end}")

# Get time range tuple from BaselineInfo
tr = baseline_info.time_range()
if tr:
    print(f"Data available: {tr[0]} to {tr[1]}")
```

### Creating Catalogs Programmatically

```python
from maap_client.catalog_build import CatalogCollection, ProductInfo, BaselineInfo

# Create a new catalog
catalog = CatalogCollection(collection="MyCollection")

# Add product with baseline
product = ProductInfo()
product.set_baseline("BC", BaselineInfo(
    time_start="2024-06-12T12:02:32Z",
    time_end="2025-12-27T03:24:46Z",
    count=50000,
))
catalog.set_product("CPR_CLD_2A", product)

# Serialize to dict (for JSON)
data = catalog.to_dict()

# Deserialize from dict
catalog2 = CatalogCollection.from_dict(data)
```

## Handling Edge Cases

### L0 Products with Different Naming

Level 0 products may have filenames that don't follow the standard EarthCARE naming convention. In this case:
- `extract_sensing_time()` returns `None`
- `get_time_range()` falls back to day boundaries
- `extract_orbit_frame_str()` returns `None`
- Catalog shows `null` for `frame_start`/`frame_end`

The time range and count are still accurate since they come from the STAC API.

### New Baselines

When a new baseline is released, running `maap catalog build` will automatically discover and include it. The `--latest-baseline` flag will still update the newest baseline.

### Data Gaps

If data has gaps (e.g., no files for certain days), the catalog still correctly shows the overall time range. The binary search finds the actual first and last days with data, not just the mission bounds.
