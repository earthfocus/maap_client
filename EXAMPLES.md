# MAAP CLI Examples

All examples use `EarthCAREL0L1Products_MAAP` collection and `CPR_NOM_1B` product.

## Help

```bash
maap -h
maap --version
```

## Configuration

```bash
maap config
```

## Catalog Management

### Update Queryables

```bash
maap -v catalog update -h
maap -v catalog update
maap -v catalog update EarthCAREL0L1Products_MAAP
maap -v catalog update EarthCAREL0L1Products_MAAP -o ./my_catalogs
```

### Build Metadata Catalog

```bash

maap -v catalog build -h

# Build everything
maap -v catalog build

# Build entire collection
maap -v catalog build EarthCAREL0L1Products_MAAP

# Build specific product
maap -v catalog build EarthCAREL0L1Products_MAAP CPR_NOM_1B

# Build specific baseline
maap -v catalog build EarthCAREL0L1Products_MAAP CPR_NOM_1B DA

# Build only latest baseline
maap -v catalog build EarthCAREL0L1Products_MAAP CPR_NOM_1B --latest-baseline

# Build with time filters
maap -v catalog build EarthCAREL0L1Products_MAAP CPR_NOM_1B --days-back 7
maap -v catalog build EarthCAREL0L1Products_MAAP CPR_NOM_1B --date 2024-12-25
maap -v catalog build EarthCAREL0L1Products_MAAP CPR_NOM_1B --start 2024-12-01 --end 2024-12-31

# Build to custom output directory
maap -v catalog build EarthCAREL0L1Products_MAAP CPR_NOM_1B -o ./my_built_catalogs
```

## List (Browse)

```bash
maap -v list -h

# List all collections
maap -v list

# List products in collection
maap -v list EarthCAREL0L1Products_MAAP

# List products with API verification
maap -v list EarthCAREL0L1Products_MAAP --verify

# List baselines for product
maap -v list EarthCAREL0L1Products_MAAP CPR_NOM_1B

# List only latest baseline
maap -v list EarthCAREL0L1Products_MAAP CPR_NOM_1B --latest-baseline

# Show baseline info (time range, count)
maap -v list EarthCAREL0L1Products_MAAP CPR_NOM_1B DA
```

## Search

```bash
maap -v search -h

# Search with defaults (all baselines, mission start to now)
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B

# Search specific baseline
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA

# Search single date (expands to full day 00:00:00Z - 23:59:59Z)
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01

# Search exact datetime (adds 1 minute buffer)
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01T12:30:00Z

# Search date range
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --start 2025-01-01 --end 2025-01-07

# Search datetime range
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --start 2025-01-01T00:00:00Z --end 2025-01-01T06:00:00Z

# Search and save to flat URL file
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01 -o urls.txt

# Search and save to partitioned registry files (by sensing date)
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01 --registry-save

# Search all baselines and save to registry
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B --start 2025-01-01 --end 2025-01-07 --registry-save

# Limit results
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01 --max-items 100

# Use built catalog for time bounds optimization
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --use-catalog
```

## Download

```bash
maap -v download -h

# Download single URL
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B --url "https://catalog.maap.eo.esa.int/data/.../file.h5"

# Download single URL to specific directory
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B --url "https://..." -o ./downloads

# Download from URL file
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B --url-file urls.txt

# Download from registry files (after --registry-save)
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry

# Download from registry with date filter
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry --date 2025-01-01

# Download from registry with date range filter
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry --start 2025-01-01 --end 2025-01-07

# Dry run (show what would be downloaded)
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry --date 2025-01-01 --dry-run

# Limit downloads
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry --max-items 10
```

## Get (Search + Download)

```bash
maap -v get -h

# Search and download in one step
maap -v get EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01

# Get with date range
maap -v get EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --start 2025-01-01 --end 2025-01-03

# Get to flat output directory
maap -v get EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01 -o ./flat_downloads

# Dry run
maap -v get EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01 --dry-run

# Limit items
maap -v get EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01 --max-items 5
```

## Sync (Crontab Workflows)

```bash
maap -v sync -h

# Sync with default (last 3 days)
maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B DA

# Sync specific number of days back
maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --days-back 7

# Sync single date
maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01

# Sync date range
maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --start 2025-01-01 --end 2025-01-07

# Sync all baselines
maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B --days-back 3

# Sync to custom output directory
maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --days-back 1 -o ./sync_data

# Limit downloads per sync
maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --days-back 7 --max-items 100
```

## State Management

```bash
# Show state summary
maap -v state show EarthCAREL0L1Products_MAAP CPR_NOM_1B DA

# Show state for specific date
maap -v state show EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01

# Show state for date range
maap -v state show EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --start 2025-01-01 --end 2025-01-07

# List pending downloads
maap -v state pending EarthCAREL0L1Products_MAAP CPR_NOM_1B DA

# List pending downloads for specific date
maap -v state pending EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01

# List pending marks (downloaded but not yet marked as processed)
maap -v state pending EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --type marks

# Mark files as processed
maap -v state mark /path/to/file1.h5 /path/to/file2.h5

# Mark files as processed from file list
maap -v state mark -f processed_files.txt

# Cleanup marked files (delete originals)
maap -v state cleanup EarthCAREL0L1Products_MAAP CPR_NOM_1B DA

# Cleanup dry run
maap -v state cleanup EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --dry-run
```

## Common Workflows

### Workflow 1: Initial Data Discovery

```bash
# 1. Update queryables catalog
maap -v catalog update EarthCAREL0L1Products_MAAP

# 2. List available products
maap -v list EarthCAREL0L1Products_MAAP

# 3. List baselines for product
maap -v list EarthCAREL0L1Products_MAAP CPR_NOM_1B

# 4. Build metadata catalog
maap -v catalog build EarthCAREL0L1Products_MAAP CPR_NOM_1B DA

# 5. View baseline info
maap -v list EarthCAREL0L1Products_MAAP CPR_NOM_1B DA
```

### Workflow 2: Search and Download

```bash
# 1. Search for data
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01

# 2. Save URLs to registry
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01 --registry-save

# 3. Download from registry
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry --date 2025-01-01

# 4. Check state
maap -v state show EarthCAREL0L1Products_MAAP CPR_NOM_1B DA
```

### Workflow 3: Crontab Sync

```bash
# Daily cron job to sync last 3 days
# 0 6 * * * maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --days-back 3

maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --days-back 3
```

### Workflow 4: Backfill Historical Data

```bash
# 1. Search and save URLs for date range
maap -v search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --start 2024-06-01 --end 2024-12-31 --registry-save

# 2. Download in batches
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry --start 2024-06-01 --end 2024-06-30
maap -v download EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry --start 2024-07-01 --end 2024-07-31
# ... continue for each month

# 3. Monitor progress
maap -v state show EarthCAREL0L1Products_MAAP CPR_NOM_1B DA
```

### Workflow 5: Processing Pipeline

```bash
# 1. Download data
maap -v sync EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --days-back 1

# 2. Get pending files for processing (downloaded but not yet marked)
maap -v state pending EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --type marks > to_process.txt

# 3. (Process files externally)

# 4. Mark as processed
maap -v state mark -f processed_files.txt

# 5. Cleanup marked originals (optional)
maap -v state cleanup EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --dry-run
maap -v state cleanup EarthCAREL0L1Products_MAAP CPR_NOM_1B DA
```

## Global Options

All commands support these global options:

```bash
# Verbose output (debug)
maap -vv search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01

# Quiet mode (errors only)
maap --quiet search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --date 2025-01-01

# Custom config file
maap -v -c /path/to/config.toml search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA

# Custom data directory
maap -v -d /path/to/data search EarthCAREL0L1Products_MAAP CPR_NOM_1B DA --registry-save
```
