# Catalogs and Caching

This document explains the two types of catalogs in MAAP Client and how caching works to speed up operations.

## Two Types of Catalogs

### 1. Queryables (from `maap catalog update`)

**What they are:** Schema definitions that describe what fields can be queried in STAC searches.

**Location:** `{catalog_dir}/{collection}_queryables.json` (default: `./catalogs/`)

**Usage:** Rarely used directly. These are metadata about the API structure, not the data itself.

```bash
maap catalog update                              # Update all
maap catalog update EarthCAREL2Validated_MAAP    # Update specific
```

### 2. Built Catalogs (from `maap catalog build`)

**What they are:** Summaries of available data including time ranges, product counts, and baseline versions.

**Location:** `{built_catalog_dir}/{collection}_collection.json` (default: `./built_catalogs/`)

**Usage:** Used by `--use-catalog` option to speed up operations.

```bash
maap catalog build EarthCAREL2Validated_MAAP
maap catalog build EarthCAREL2Validated_MAAP CPR_CLD_2A
maap catalog build EarthCAREL2Validated_MAAP --latest-baseline
```

## How Caching Works

### Without `--use-catalog`

Commands query the MAAP API to determine data bounds before searching:

```
┌─────────────┐     ┌──────────┐     ┌─────────────┐
│ maap search │ ──▶ │ MAAP API │ ──▶ │ Get bounds  │
└─────────────┘     └──────────┘     └─────────────┘
                          │
                          ▼
                    ┌──────────┐
                    │ MAAP API │ ──▶ Search URLs
                    └──────────┘
```

This requires **two API calls**: one to find data bounds, one to search.

### With `--use-catalog`

Commands use the local built catalog for bounds:

```
┌─────────────┐     ┌───────────────┐
│ maap search │ ──▶ │ Local catalog │ ──▶ Get bounds (instant)
└─────────────┘     └───────────────┘
                          │
                          ▼
                    ┌──────────┐
                    │ MAAP API │ ──▶ Search URLs
                    └──────────┘
```

This requires **one API call**: just the search.

## Commands That Support `--use-catalog`

| Command | Effect of `--use-catalog` |
|---------|------------------------|
| `maap search` | Uses cached data bounds to optimize search range |
| `maap download --registry` | Uses cached data bounds to filter date range |

## When to Use Caching

### Use `--use-catalog` when:
- You're running many searches and want faster startup
- You know the catalog is recent enough for your needs
- You're scripting/automating and want consistent behavior

### Don't use `--use-catalog` when:
- You need the absolute latest data bounds
- You're checking if new data has arrived
- The catalog hasn't been built yet

## Keeping Catalogs Fresh

Built catalogs are snapshots - they become stale as new data arrives. Refresh them periodically:

```bash
# Full rebuild (slower, complete)
maap catalog build EarthCAREL2Validated_MAAP

# Update only latest baselines (faster)
maap catalog build EarthCAREL2Validated_MAAP --latest-baseline

# Update specific products only
maap catalog build EarthCAREL2Validated_MAAP CPR_CLD_2A
```

### Recommended refresh schedule:
- **Daily operations:** Rebuild weekly or when you notice stale bounds
- **Automated pipelines:** Rebuild before each batch run, or use API queries (no cache)

## Example Workflow

```bash
# 1. Build catalog once
maap catalog build EarthCAREL2Validated_MAAP

# 2. Use cache for repeated operations
maap list EarthCAREL2Validated_MAAP CPR_CLD_2A BC
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --use-catalog --registry-save

# 3. Rebuild periodically to catch new data
maap catalog build EarthCAREL2Validated_MAAP --latest-baseline
```

## Catalog File Format

Built catalogs are JSON files with this structure:

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
        }
      }
    }
  }
}
```

## Python Classes

The catalog system uses a unified class hierarchy based on the `Catalog` base class:

```
Catalog (catalog.py - base class)
├── CatalogQueryables (catalog_query.py) - Schema definitions from STAC API
├── CatalogCollection (catalog_build.py) - Built catalog with product metadata
│   └── products: dict[str, ProductInfo]
├── ProductInfo (catalog_build.py) - Per-product entry with baselines
│   └── baselines: dict[str, BaselineInfo]
└── BaselineInfo (catalog_build.py) - Time range, counts, orbit info
```

See `docs/CATALOG_BUILD.md` for Python API usage.

## Summary

| Catalog Type | Command | Purpose | Used By |
|--------------|---------|---------|---------|
| Queryables | `maap catalog update` | API schema info | Internal |
| Built Catalog | `maap catalog build` | Data summaries | `--use-catalog` option |

**Key point:** The actual search for product URLs **always queries the MAAP API**. Caching only speeds up finding the available date range.
