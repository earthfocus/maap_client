# MAAP Client CLI Reference

Complete command-line interface documentation for the MAAP EarthCARE data client.

## Global Options

These options are available for all commands:

```
-c, --config PATH     Configuration file path
-d, --data-dir PATH   Data directory (overrides config)
-v, --verbose         Increase verbosity (-v, -vv)
--quiet               Suppress non-error output
--version             Show version and exit
```

---

## Config Command

### `maap config`

Show the loaded configuration, including all paths and settings.

```bash
maap config
```

**Output includes:**
- All configured paths (data_dir, catalog_dir, built_catalog_dir, registry_dir, credentials_file)
- API URLs (catalog_url, token_url)
- Mission settings (name, start, end)
- Config file location

Use this to verify your `~/.maap/config.toml` is being loaded correctly.

---

## List Command

### `maap list`

Unified command to browse collections, products, baselines, and baseline info.

```bash
maap list [COLLECTION [PRODUCT [BASELINE]]] [OPTIONS]
```

**Arguments:**

| Level | Arguments | Description |
|-------|-----------|-------------|
| Collections | (none) | List all known collections |
| Products | `COLLECTION` | List products in a collection |
| Baselines | `COLLECTION PRODUCT` | List baselines for a product |
| Baseline info | `COLLECTION PRODUCT BASELINE` | Show baseline details |

**Options:**
| Option | Description |
|--------|-------------|
| `--verify` | Refresh from API to get latest products/baselines |
| `--latest-baseline` | Show only the latest baseline |

**Examples:**
```bash
# List all collections
maap list

# List products in a collection
maap list EarthCAREL2Validated_MAAP

# List baselines for a product (fast, from local catalog)
maap list EarthCAREL2Validated_MAAP CPR_CLD_2A

# List baselines with API verification (slower but accurate)
maap list EarthCAREL2Validated_MAAP CPR_CLD_2A --verify

# Show baseline info (time range, count, etc.)
maap list EarthCAREL2Validated_MAAP CPR_CLD_2A BC

# Get only the latest baseline
maap list EarthCAREL2Validated_MAAP CPR_CLD_2A --latest-baseline
```

---

## Catalog Commands

Manage local catalog metadata for faster browsing.

### `maap catalog update`

Download or update catalog queryables from the MAAP server.

```bash
maap catalog update [COLLECTION] [OPTIONS]
```

**Arguments:**
| Argument | Description |
|----------|-------------|
| `collection` | Collection name (optional, updates all if omitted) |

**Options:**
| Option | Description |
|--------|-------------|
| `-o, --out-dir PATH` | Output directory |

**Examples:**
```bash
# Update all collections
maap catalog update

# Update specific collection
maap catalog update EarthCAREL2Validated_MAAP

# Update to specific directory
maap catalog update -o ./my_catalogs
```

---

### `maap catalog build`

Build a metadata catalog JSON file for a collection with time ranges and product counts.

```bash
maap catalog build [COLLECTION [PRODUCT [BASELINE]]] [OPTIONS]
```

**Arguments:**
| Argument | Description |
|----------|-------------|
| `collection` | Collection name (optional, builds all if omitted) |
| `product` | Product type (optional, builds all products if omitted) |
| `baseline` | Baseline version (optional, builds all baselines if omitted) |

**Options:**
| Option | Description |
|--------|-------------|
| `--force` | Delete existing catalog and rebuild from scratch |
| `--latest-baseline` | Only build for the latest baseline |
| `--start` / `-s` | Start datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ) |
| `--end` / `-e` | End datetime |
| `--date` | Single date (expands to full day) |
| `--days-back` | Days to look back from now |
| `-o, --out-dir PATH` | Output directory for catalog file |

Note: `--date`, `--days-back`, and `--start/--end` are mutually exclusive.

**Examples:**
```bash
# Build full catalog for all collections
maap catalog build

# Build catalog for one collection
maap catalog build EarthCAREL2Validated_MAAP

# Build for specific product
maap catalog build EarthCAREL2Validated_MAAP CPR_CLD_2A

# Build for specific baseline
maap catalog build EarthCAREL2Validated_MAAP CPR_CLD_2A BC

# Update only latest baselines (faster)
maap catalog build EarthCAREL2Validated_MAAP --latest-baseline

# Build with time range filter
maap catalog build EarthCAREL2Validated_MAAP --start 2024-12-01 --end 2024-12-31

# Force rebuild from scratch
maap catalog build EarthCAREL2Validated_MAAP --force
```

---

## Search Command

### `maap search`

Search for product URLs using time-based or orbit-based queries.

```bash
maap search COLLECTION PRODUCT [BASELINE] [OPTIONS]
```

**Arguments:**
| Argument | Description |
|----------|-------------|
| `collection` | Collection name |
| `product` | Product type |
| `baseline` | Baseline version (optional, searches all if omitted) |

**Filtering Options (mutually exclusive):**
| Option | Description |
|--------|-------------|
| `--start` / `-s` | Start datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ) |
| `--end` / `-e` | End datetime (use with `--start`) |
| `--date` | Single date (expands to 00:00:00Z-23:59:59Z) |
| `--days-back` / `-d` | Days to look back from now |
| `--orbit` | Orbit+frame for orbit-based search (e.g., '01525F') |

**Output Options:**
| Option | Description |
|--------|-------------|
| `--url-file` / `-o` | Write URLs to file (flat format, one URL per line) |
| `--registry-save` | Save URLs to partitioned registry files (by sensing date) |

**Other Options:**
| Option | Description |
|--------|-------------|
| `--max-items` / `-n` | Maximum items to return (default: 50000) |
| `--use-catalog` | Use built catalog for time bounds (faster, may be stale) |

**Examples:**
```bash
# Search with defaults (MISSION_START to now, all baselines)
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B

# Search for a single day (--date expands to 00:00:00Z-23:59:59Z)
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A --date 2024-12-01

# Search with date range
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A --start 2024-12-01 --end 2024-12-31

# Search specific baseline
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2024-12-01 --end 2024-12-31

# Search and save URLs to registry (grouped by baseline)
maap search EarthCAREL1Validated_MAAP CPR_NOM_1B --start 2024-06-12 --registry-save

# Search by orbit
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A --orbit 08962F

# Save to flat file
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A --start 2024-12-01 --url-file urls.txt

# Look back 7 days
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A --days-back 7
```

---

## Get Command

### `maap get`

Search and download products in one step. Combines `search` and `download` for convenience.

```bash
maap get COLLECTION PRODUCT [BASELINE] [OPTIONS]
```

**Arguments:**
| Argument | Description |
|----------|-------------|
| `collection` | Collection name |
| `product` | Product type |
| `baseline` | Baseline version (optional, searches all if omitted) |

**Filtering Options (mutually exclusive):**
| Option | Description |
|--------|-------------|
| `--start` / `-s` | Start datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ) |
| `--end` / `-e` | End datetime (use with `--start`) |
| `--date` | Single date (expands to 00:00:00Z-23:59:59Z) |
| `--days-back` / `-d` | Days to look back from now |
| `--orbit` | Orbit+frame for orbit-based search (e.g., '01525F') |

**Output Options:**
| Option | Description |
|--------|-------------|
| `--out-dir` / `-o` | Output directory (flat, no structured paths) |
| `--dry-run` | Show what would be downloaded |

**Other Options:**
| Option | Description |
|--------|-------------|
| `--max-items` / `-n` | Maximum items to get (default: 50000) |

**Examples:**
```bash
# Get products for a single day
maap get EarthCAREL2Validated_MAAP CPR_CLD_2A --date 2024-12-01

# Get products for a date range
maap get EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2024-12-01 --end 2024-12-07

# Get by orbit
maap get EarthCAREL2Validated_MAAP CPR_CLD_2A --orbit 08962F

# Dry run to preview
maap get EarthCAREL2Validated_MAAP CPR_CLD_2A --date 2024-12-01 --dry-run

# Download to specific directory
maap get EarthCAREL2Validated_MAAP CPR_CLD_2A --date 2024-12-01 --out-dir ./downloads
```

---

## Download Command

### `maap download`

Download products by URL, from a URL file, or from saved registry files.

```bash
maap download COLLECTION PRODUCT [BASELINE] [OPTIONS]
```

**Arguments:**
| Argument | Description |
|----------|-------------|
| `collection` | Collection name |
| `product` | Product type |
| `baseline` | Baseline version (optional) |

**Download Source (mutually exclusive, optional):**

If none specified, searches MAAP API directly.

| Option | Description |
|--------|-------------|
| `--url` / `-u` | Download a single URL |
| `--url-file` / `-f` | Download URLs from a file (one per line) |
| `--registry` | Download from saved registry files |

**Filtering Options (only with `--registry`):**
| Option | Description |
|--------|-------------|
| `--start` / `-s` | Start datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ) |
| `--end` / `-e` | End datetime |
| `--date` | Single date (expands to full day) |
| `--days-back` / `-d` | Days to look back from now |

**Output Options:**
| Option | Description |
|--------|-------------|
| `--out-dir` / `-o` | Output directory |
| `--dry-run` | Show what would be downloaded |

**Other Options:**
| Option | Description |
|--------|-------------|
| `--max-items` / `-n` | Maximum items to download |
| `--use-catalog` | Use built catalog for time bounds |

**Examples:**
```bash
# Download single URL
maap download EarthCAREL2Validated_MAAP CPR_CLD_2A --url https://catalog.maap.eo.esa.int/data/.../file.h5

# Download from URL file
maap download EarthCAREL2Validated_MAAP CPR_CLD_2A --url-file urls.txt

# Download from registry files (after --registry-save)
maap download EarthCAREL2Validated_MAAP CPR_CLD_2A BC --registry \
    --start 2025-01-01 --end 2025-01-31

# Download from registry for a single day
maap download EarthCAREL2Validated_MAAP CPR_CLD_2A BC --registry --date 2025-01-15

# Download to specific directory
maap download EarthCAREL2Validated_MAAP CPR_CLD_2A --url-file urls.txt --out-dir ./downloads

# Preview what would be downloaded
maap download EarthCAREL2Validated_MAAP CPR_CLD_2A --registry --start 2025-01-01 --dry-run
```

**Workflow: Search then Download:**

```bash
# Option 1: Search and save to flat file, then download
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A --start 2025-12-24 --end 2025-12-25 --url-file urls.txt
maap download EarthCAREL2Validated_MAAP CPR_CLD_2A --url-file urls.txt

# Option 2: Search and save to registry, then download from registry
maap search EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2025-01-01 --end 2025-01-31 --registry-save
maap download EarthCAREL2Validated_MAAP CPR_CLD_2A BC --registry --start 2025-01-01 --end 2025-01-31

# Option 3: Use 'get' for search+download in one step
maap get EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2025-01-01 --end 2025-01-07
```

---

## Sync Command

### `maap sync`

Incremental sync designed for crontab/scheduled workflows. Automatically tracks discovered URLs and downloaded files to avoid redundant work.

```bash
maap sync COLLECTION PRODUCT [BASELINE] [OPTIONS]
```

**Arguments:**
| Argument | Description |
|----------|-------------|
| `collection` | Collection name |
| `product` | Product type |
| `baseline` | Baseline version (optional; if omitted, syncs all baselines) |

**Time Range Options (mutually exclusive):**
| Option | Description |
|--------|-------------|
| `--date` | Single date (YYYY-MM-DD) |
| `--days-back` / `-d` | Days to look back from now |
| `--start` / `-s` | Start datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ) |
| `--end` / `-e` | End datetime (use with `--start`; defaults to now) |

Default: last 3 days if no time option specified.

**Other Options:**
| Option | Description |
|--------|-------------|
| `--max-items` / `-n` | Maximum items per run (default: 50000) |
| `--out-dir` / `-o` | Output directory |

**What sync does automatically:**

1. **Searches** for products in the specified time window
2. **Records** all discovered URLs to state files (`url_YYYYMMDD.txt`)
3. **Filters** out already-downloaded files using state tracking
4. **Downloads** only new files (up to max-items)
5. **Records** successful downloads to state files (`dwl_YYYYMMDD.txt`)

This makes sync **idempotent** - you can run it repeatedly (e.g., every hour via cron) and it will only download new files.

**Examples:**
```bash
# Basic sync (last 3 days by default)
maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A BC

# Sync a specific day
maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A BC --date 2024-12-25

# Look back 7 days
maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A BC --days-back 7

# Explicit date range (for backfilling)
maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2025-01-01 --end 2025-01-31

# Start to now (backfill from a specific date)
maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2025-06-01

# Sync all baselines
maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A

# Limit downloads per run (useful for rate limiting)
maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A BC --max-items 100
```

**Crontab example:**
```bash
# Run every hour, sync last 3 days of data
0 * * * * /path/to/maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A BC >> /var/log/maap-sync.log 2>&1
```

---

## State Commands

Manage download state tracking for pipeline workflows.

### State File Structure

State files are organized by collection/product/baseline with year subdirectories:

```
registry/
├── urls/{mission}/{collection}/{product}/{baseline}/{year}/
│   ├── url_20251224.txt    # Discovered URLs for Dec 24
│   ├── url_20251225.txt    # Discovered URLs for Dec 25
│   └── ...
├── downloads/{mission}/{collection}/{product}/{baseline}/{year}/
│   ├── dwl_20251224.txt    # Downloaded files for Dec 24
│   ├── dwl_20251225.txt    # Downloaded files for Dec 25
│   └── ...
└── marked/{mission}/{collection}/{product}/{baseline}/{year}/
    ├── mrk_20251224.txt    # Marked files for Dec 24
    └── ...
```

**File formats:**
- `url_*.txt` - `URL|LOCAL_PATH` format (sensing date determines file)
- `dwl_*.txt` - `URL|LOCAL_PATH` format (sensing date determines file)
- `mrk_*.txt` - `LOCAL_PATH` only (sensing date determines file)

### Why State Tracking?

State tracking enables **pipeline workflows** where:

1. **Discovery** is separate from **download** - search and save URLs without downloading
2. **Download** is separate from **processing** - track what's downloaded vs processed
3. **Cleanup** is safe - delete source files only after processing is confirmed
4. **Resumability** - interrupted downloads can resume without re-downloading
5. **Auditability** - clear record of what was discovered, downloaded, and processed

---

### `maap state show`

Show state summary for a product+baseline.

```bash
maap state show COLLECTION PRODUCT BASELINE [OPTIONS]
```

**Options:**
| Option | Description |
|--------|-------------|
| `--date` | Single date filter |
| `--start` / `-s` | Start date filter (ISO format) |
| `--end` / `-e` | End date filter (ISO format) |

**Output includes:**
- Total URLs discovered
- Downloaded count
- Marked count
- Pending downloads
- Pending marks

**Examples:**
```bash
# Show all state
maap state show EarthCAREL2Validated_MAAP CPR_CLD_2A BC

# Show state for a date range
maap state show EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2025-01-01 --end 2025-01-31

# Show state for a single day
maap state show EarthCAREL2Validated_MAAP CPR_CLD_2A BC --date 2025-01-15
```

---

### `maap state pending`

List URLs that are pending download or marking.

```bash
maap state pending COLLECTION PRODUCT BASELINE [OPTIONS]
```

**Options:**
| Option | Description |
|--------|-------------|
| `--type {downloads,marks}` | Type of pending items (default: downloads) |
| `--date` | Single date filter |
| `--start` / `-s` | Start date filter (ISO format) |
| `--end` / `-e` | End date filter (ISO format) |

**Examples:**
```bash
# List all pending downloads
maap state pending EarthCAREL2Validated_MAAP CPR_CLD_2A BC

# List pending downloads for a date range
maap state pending EarthCAREL2Validated_MAAP CPR_CLD_2A BC --start 2025-01-01 --end 2025-01-31

# List pending marks
maap state pending EarthCAREL2Validated_MAAP CPR_CLD_2A BC --type marks
```

---

### `maap state mark`

Mark files as processed. This is used by your processing pipeline to indicate that a file has been successfully processed and the original can be deleted.

```bash
maap state mark [PATHS...] [OPTIONS]
```

**Arguments:**
| Argument | Description |
|----------|-------------|
| `paths` | Local file paths to mark as processed |

**Options:**
| Option | Description |
|--------|-------------|
| `-f, --file PATH` | File containing paths to mark (one per line) |

**Examples:**
```bash
# Mark single file as processed
maap state mark /path/to/file.h5

# Mark multiple files
maap state mark /path/to/file1.h5 /path/to/file2.h5

# Mark files from a list
maap state mark --file processed_paths.txt
```

---

### `maap state cleanup`

Delete original files that have been marked.

```bash
maap state cleanup COLLECTION PRODUCT BASELINE [OPTIONS]
```

**Options:**
| Option | Description |
|--------|-------------|
| `--dry-run` | Show what would be deleted without deleting |

**Examples:**
```bash
# Preview cleanup
maap state cleanup EarthCAREL2Validated_MAAP CPR_CLD_2A BC --dry-run

# Actually delete marked files
maap state cleanup EarthCAREL2Validated_MAAP CPR_CLD_2A BC
```

---

## Pipeline Workflow Example

A typical automated pipeline using state tracking:

```bash
#!/bin/bash
COLLECTION="EarthCAREL2Validated_MAAP"
PRODUCT="CPR_CLD_2A"
BASELINE="BC"

# 1. Sync recent data (search + download with state tracking)
maap sync $COLLECTION $PRODUCT $BASELINE --days-back 3

# 2. Process downloaded files (your custom processing)
maap state pending $COLLECTION $PRODUCT $BASELINE --type marks | while read path; do
    if process_file "$path"; then
        maap state mark "$path"
    fi
done

# 3. Cleanup processed files to save space
maap state cleanup $COLLECTION $PRODUCT $BASELINE
```

Or for simple use cases, just use `maap sync` in a cron job:

```bash
# Cron job: every hour
0 * * * * maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A BC --days-back 3
```

---

## Command Comparison

| Command | Purpose | State Tracking |
|---------|---------|----------------|
| `search` | Find URLs, optionally save to registry | Optional (`--registry-save`) |
| `download` | Download files | Optional (with `--registry`) |
| `get` | Search + download in one step | No |
| `sync` | Incremental search + download | Yes (automatic) |

**When to use which:**

- **`get`**: Quick one-off downloads, no state tracking needed
- **`search` + `download`**: Fine-grained control over search and download phases
- **`sync`**: Automated pipelines, cron jobs, incremental updates
