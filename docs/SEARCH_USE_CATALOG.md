# Catalog Optimization Guide

## Overview

The **catalog system** is a local caching mechanism that stores metadata about available MAAP products. It enables faster searches by avoiding API calls to determine data availability and time ranges.

## What is the Catalog?

The catalog is a **JSON file** stored locally that contains:

- **Time ranges**: When data is available (`time_start`, `time_end`)
- **Product counts**: Total number of products
- **Orbit ranges**: First and last orbit+frame (if applicable)
- **Update timestamps**: When the catalog was last built

**Location:**
```
built_catalogs/{collection}_collection.json
```

**Example:**
```json
{
  "schema": "1.0",
  "generated_at": "2024-12-30T12:00:00Z",
  "collection": "EarthCAREL2Validated_MAAP",
  "client": {"name": "maap_client", "version": "0.1.0"},
  "products": {
    "CPR_CLD_2A": {
      "baselines": {
        "BC": {
          "time_start": "2024-06-12T04:52:41Z",
          "time_end": "2024-12-30T13:24:09Z",
          "count": 16789,
          "updated_at": "2024-12-30T12:00:00Z"
        }
      }
    }
  }
}
```

## Advantages

### 🚀 Performance

| Without Catalog | With Catalog (`--use-catalog`) |
|----------------|-------------------------------|
| API call to get time bounds (~1-3 sec) | Read from local file (~0.01 sec) |
| **Slower** | **⚡ 100x faster** |

### 📉 Reduced API Load

- Fewer requests to MAAP servers
- Less network bandwidth usage
- Lower server load

### 🔌 Offline Capability

Once built, catalogs work **without internet connection**:
```bash
# Build catalog (requires internet)
maap catalog build EarthCAREL2Validated_MAAP

# Use catalog (works offline!)
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2024-06-01 --end 2024-12-31 --use-catalog
```

### 📊 Quick Information Access

Get product information instantly without API queries:
```bash
# List baselines with time ranges and counts
maap list EarthCAREL2Validated_MAAP CPR_CLD_2A
```

**Output:**
```
BC
  Time: 2024-06-12T04:52:41Z to 2024-12-30T13:24:09Z
  Count: 16789
  Updated: 2024-12-30T12:00:00Z

BD
  Time: 2024-11-01T00:00:00Z to 2024-12-30T23:59:59Z
  Count: 4521
  Updated: 2024-12-30T12:00:00Z
```

## What the Catalog Offers

### 1. Faster Searches

**Without catalog:**
```bash
$ maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2024-06-01 --end 2024-12-31
Resolving temporal coverage for BC...  # ← API call (slow)
2024-06-12T04:52:41Z
2024-12-30T13:24:09Z
[1/202] ...
```

**With catalog:**
```bash
$ maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2024-06-01 --end 2024-12-31 --use-catalog
Using cached temporal coverage for BC...  # ← From file (fast!)
2024-06-12T04:52:41Z
2024-12-30T13:24:09Z
[1/202] ...
```

### 2. Smart Date Optimization

The catalog automatically:
- **Intersects** your requested dates with actual data availability
- **Skips** date ranges with no data
- **Optimizes** search to only query days that have products

**Example:**
```bash
# You request: 2024-01-01 to 2024-12-31
# Catalog knows: Data only exists 2024-06-12 to 2024-12-30
# Search runs: Only for days with actual data (saves ~160 days of queries!)
```

### 3. Quick Product Discovery

```bash
# List all products in a collection
maap list EarthCAREL2Validated_MAAP

# Show baselines for a product
maap list EarthCAREL2Validated_MAAP CPR_CLD_2A

# Get detailed info for a baseline
maap list EarthCAREL2Validated_MAAP CPR_CLD_2A BC
```

### 4. Batch Operations

Build catalogs for multiple collections efficiently:
```bash
# Build all collections
maap catalog build

# Build specific collection
maap catalog build EarthCAREL2Validated_MAAP

# Build only latest baselines (faster)
maap catalog build EarthCAREL2Validated_MAAP --latest-baseline
```

## How to Manage Catalogs

### Initial Setup

#### 1. Download Queryables (One-Time)

Download collection metadata from MAAP:
```bash
# Download all collections
maap catalog update

# Download specific collection
maap catalog update EarthCAREL2Validated_MAAP
```

**Result:**
```
catalogs/EarthCAREL2Validated_MAAP_queryables.json
```

#### 2. Build Catalog

Build the metadata catalog with time ranges and counts:
```bash
# Build entire collection
maap catalog build EarthCAREL2Validated_MAAP

# Build specific product
maap catalog build EarthCAREL2Validated_MAAP CPR_CLD_2A

# Build specific baseline
maap catalog build EarthCAREL2Validated_MAAP CPR_CLD_2A BC
```

**Result:**
```
built_catalogs/EarthCAREL2Validated_MAAP_collection.json
```

**Output:**
```
Building catalog for EarthCAREL2Validated_MAAP...
  CPR_CLD_2A
    Baseline BC... 16789 products (2024-06-12T04:52:41Z to 2024-12-30T13:24:09Z)
    Baseline BD... 4521 products (2024-11-01T00:00:00Z to 2024-12-30T23:59:59Z)
  BM__RAD_2B
    Baseline BC... 15234 products (2024-06-12T05:12:33Z to 2024-12-30T12:45:21Z)
Wrote catalog to built_catalogs/EarthCAREL2Validated_MAAP_collection.json
Summary: 2 products, 3 baselines
```

### Regular Updates

#### Update Catalogs Periodically

**Recommended frequency:** Weekly or when new baselines are released

```bash
# Update entire collection
maap catalog build EarthCAREL2Validated_MAAP

# Update only recent data (faster)
maap catalog build EarthCAREL2Validated_MAAP --days-back 7

# Update only latest baselines (fastest)
maap catalog build EarthCAREL2Validated_MAAP --latest-baseline --days-back 7
```

#### Incremental Updates

Update only new data without rebuilding from scratch:
```bash
# Update last 7 days
maap catalog build EarthCAREL2Validated_MAAP CPR_CLD_2A BC --days-back 7

# Update specific date range
maap catalog build EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2024-12-20 --end 2024-12-31
```

### Using Catalogs

#### In Searches

Enable catalog optimization with `--use-catalog`:
```bash
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2024-06-01 --end 2024-12-31 --use-catalog
```

**Requirements for optimization:**
- ✅ Baseline explicitly specified
- ✅ Date range > 30 days
- ✅ `--use-catalog` flag present
- ✅ Catalog file exists

**Note:** For short periods (≤ 30 days), catalog isn't used even with the flag.

#### Checking Catalog Status

```bash
# View catalog contents
maap list EarthCAREL2Validated_MAAP CPR_CLD_2A BC
```

**Output:**
```
BC
  Time: 2024-06-12T04:52:41Z to 2024-12-30T13:24:09Z
  Count: 16789
  Orbit: 00228H to 08981B
  Updated: 2024-12-30T12:00:00Z
```

## Best Practices

### 1. Build Catalogs for Frequently Used Collections

```bash
# One-time setup for your main collections
maap catalog update EarthCAREL2Validated_MAAP
maap catalog build EarthCAREL2Validated_MAAP

maap catalog update EarthCAREL1Validated_MAAP
maap catalog build EarthCAREL1Validated_MAAP
```

### 2. Update Weekly (Cron Job)

```bash
#!/bin/bash
# Update catalogs weekly
maap catalog build EarthCAREL2Validated_MAAP --latest-baseline --days-back 7
maap catalog build EarthCAREL1Validated_MAAP --latest-baseline --days-back 7
```

### 3. Use `--use-catalog` for Large Date Ranges

```bash
# Large range (214 days) - catalog helps significantly
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2024-06-01 --end 2024-12-31 --use-catalog

# Small range (1 day) - catalog not needed
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --date 2024-12-25
```

### 4. Check Catalog Age

```bash
# View when catalog was last updated
maap list EarthCAREL2Validated_MAAP CPR_CLD_2A BC
```

If `Updated` timestamp is > 7 days old, consider rebuilding.

## Catalog vs No Catalog

| Feature | Without Catalog | With Catalog |
|---------|----------------|--------------|
| **Speed** | API call required (~1-3s) | Local read (~0.01s) |
| **Network** | Internet required | Works offline |
| **Accuracy** | Always current | May be slightly stale |
| **Setup** | None | Initial build required |
| **Maintenance** | None | Periodic updates recommended |

## When to Use Catalog

### ✅ Use `--use-catalog` when:
- Searching large date ranges (> 30 days)
- Running automated/scheduled searches
- Working offline
- Reducing API load
- Speed is important

### ❌ Don't use `--use-catalog` when:
- Searching short periods (≤ 30 days)
- Need absolutely current data
- Haven't built catalog yet
- Catalog is very stale (> 30 days old)

## Troubleshooting

### Catalog Not Found

```bash
$ maap search ... --use-catalog
No cache found for CPR_CLD_2A/BC, querying API...
```

**Solution:** Build the catalog first
```bash
maap catalog build EarthCAREL2Validated_MAAP
```

### Stale Catalog

Catalog shows old data or missing recent products.

**Solution:** Rebuild the catalog
```bash
maap catalog build EarthCAREL2Validated_MAAP
```

### Catalog Not Being Used

Even with `--use-catalog`, searches are slow.

**Possible reasons:**
1. Date range ≤ 30 days (optimization doesn't apply)
2. No baseline specified (optimization requires explicit baseline)
3. Catalog file doesn't exist

**Check:**
```bash
ls built_catalogs/EarthCAREL2Validated_MAAP_collection.json
```

## Summary

The catalog system provides:
- ⚡ **100x faster searches** for large date ranges
- 📉 **Reduced API load** on MAAP servers
- 🔌 **Offline capability** once built
- 📊 **Quick product information** access

**Management:**
1. **Setup:** `maap catalog update && maap catalog build`
2. **Update:** Weekly with `--days-back 7`
3. **Use:** Add `--use-catalog` to search commands

**Best for:** Large date ranges, automated workflows, offline work
