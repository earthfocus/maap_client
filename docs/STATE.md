# State Tracking and Pipeline Commands

This document explains how MAAP Client tracks the state of discovered URLs, downloads, and processed files to enable efficient pipeline workflows.

## Overview

State tracking enables three-phase workflows:
1. **Discovery**: Find URLs and record them
2. **Download**: Download files and record completions
3. **Processing**: Process files and record completions, then cleanup

Each phase is tracked independently, allowing you to:
- Resume interrupted operations
- Skip already-completed work
- Know exactly what's pending at each stage

## State File Structure

State files are stored in `{registry_dir}/` (default: `./registry/`, configurable via `~/.maap/config.toml`):

```
{registry_dir}/
├── urls/{mission}/{collection}/{product}/{baseline}/{year}/
│   ├── url_20251224.txt    # URLs discovered for Dec 24, 2025
│   ├── url_20251225.txt
│   └── ...
├── downloads/{mission}/{collection}/{product}/{baseline}/{year}/
│   ├── dwl_20251224.txt    # Downloaded files for Dec 24, 2025
│   ├── dwl_20251225.txt
│   └── ...
└── marked/{mission}/{collection}/{product}/{baseline}/{year}/
    ├── mrk_20251224.txt    # Processed files for Dec 24, 2025
    └── ...
```

### File Formats

| File | Format | Example |
|------|--------|---------|
| `url_*.txt` | `URL\|LOCAL_PATH` | `https://.../file.h5\|/data/.../file.h5` |
| `dwl_*.txt` | `URL\|LOCAL_PATH` | `https://.../file.h5\|/data/.../file.h5` |
| `mrk_*.txt` | `LOCAL_PATH` only | `/data/.../file.h5` |

### Why Year Subdirectories?

Files are partitioned by **sensing date** (extracted from filename) and organized by year:
- Keeps individual directories small (~365 files per year max)
- Fast lookups for recent data
- Scales well as mission grows

## How State Calculations Work

### Pending Downloads

```
pending_downloads = urls - downloads
```

For each date file:
1. Load `url_YYYYMMDD.txt` → set of URLs discovered
2. Load `dwl_YYYYMMDD.txt` → set of URLs downloaded
3. Subtract: URLs not yet downloaded = pending

### Pending Marks

```
pending_marks = downloads - marked
```

For each date file:
1. Load `dwl_YYYYMMDD.txt` → set of local paths downloaded
2. Load `mrk_YYYYMMDD.txt` → set of local paths processed
3. Subtract: paths not yet processed = pending

### Deletable Files

```
deletable = marked ∩ exists_on_disk
```

Files that are both marked AND still exist on disk.

## Architecture

### Registry and StateTracker

The state tracking system uses a two-layer architecture:

1. **`Registry`** (`registry.py`) - Low-level file path management and operations:
   - Path generation: `url_file_for_date()`, `dwl_file_for_date()`, `mrk_file_for_date()`
   - File operations: `count_lines()`, `touch()`, `read_pairs()`, `write_pairs()`
   - Directory listing: `list_url_files()`, `list_dwl_files()`, `list_mrk_files()`

2. **`StateTracker`** (`tracker.py`) - Workflow logic built on Registry:
   - URL management: `add_urls()`, `load_urls_with_paths()`
   - Download tracking: `mark_downloaded()`, `get_pending_downloads()`
   - Mark tracking: `mark()`, `get_pending_mark_paths()`
   - Statistics: `get_stats()`, `list_dates()`

```python
# StateTracker uses Registry internally
class StateTracker:
    def __init__(self, registry_dir, mission, collection, product_type, baseline, ...):
        self._registry = Registry(registry_dir, mission, collection, product_type, baseline)
        ...
```

### Skip Optimization

When saving URLs with `--registry-save`, the system checks if the existing file has the same URL count:

```python
# In save_urls():
if url_file.exists():
    existing_count = registry.count_lines(url_file)
    if existing_count == len(date_urls):
        registry.touch(url_file)  # Update mtime
        continue  # Skip writing
```

Benefits:
- **Faster re-runs**: No file I/O when data hasn't changed
- **Preserves mtime**: Touch updates modification time to show "checked"
- **Automatic**: No extra flags needed

## Efficiency Considerations

### Current Implementation

The current implementation loads state files on-demand and uses Python sets for lookups:

```python
# O(n) to load file, O(1) per lookup
urls = set(load_urls())
downloaded = set(load_downloaded())
pending = urls - downloaded  # O(n) set difference
```

### Scaling Analysis

| Data Volume | URLs per Day | Days per Year | Total URLs/Year |
|-------------|--------------|---------------|-----------------|
| Current     | ~50          | 365           | ~18,000         |
| 5 years     | ~50          | 1,825         | ~90,000         |
| 10 years    | ~50          | 3,650         | ~180,000        |

**Per product+baseline**. With ~50 products × ~3 baselines = 150 combinations, total state entries could reach millions.

### Why It's Still Efficient

1. **Date partitioning**: Operations typically query recent dates only
   - `maap sync --days-back 3` only loads 3 files
   - `maap state pending` can filter by date range

2. **Year directories**: Each year has ~365 small files, not one giant file

3. **Set operations**: O(1) lookups after initial O(n) load

4. **Lazy loading**: Files only loaded when needed

### Potential Future Optimizations

If performance becomes an issue:

1. **SQLite backend**: Replace text files with SQLite database
   - Indexed queries
   - Atomic transactions
   - No full-file loads

2. **Bloom filters**: For quick "definitely not present" checks

3. **Caching**: Keep frequently-accessed state in memory

4. **Date range indexes**: Track min/max dates per product to skip empty ranges

## Pipeline Commands

### `maap sync`

Automated discovery + download for recent data. Designed for cron jobs.

```bash
maap sync COLLECTION PRODUCT [BASELINE] [OPTIONS]
```

**What it does:**
1. Search for URLs in time window (now - days_back)
2. Record all discovered URLs to state
3. Filter out already-downloaded files
4. Download new files (up to max-items)
5. Record successful downloads to state

**Options:**
| Option | Default | Description |
|--------|---------|-------------|
| `--days-back N` | 3 | Days to look back (mutually exclusive with `--start`) |
| `--date DATE` | - | Single date (YYYY-MM-DD) |
| `--start DATE` | - | Start date for backfilling (mutually exclusive with `--days-back`) |
| `--end DATE` | now | End date (use with `--start`) |
| `--max-items N` | 50000 | Max files per run |
| `--out-dir PATH` | config | Output directory |

**Example cron job:**
```bash
# Every hour, sync last 3 days
0 * * * * maap sync EarthCAREL2Validated_MAAP CPR_CLD_2A BC >> /var/log/maap.log 2>&1
```

### `maap state show`

Display state summary for a product+baseline.

```bash
maap state show COLLECTION PRODUCT BASELINE [--date DATE | --start DATE] [--end DATE]
```

**Output:**
```
State for EarthCAREL2Validated_MAAP / CPR_CLD_2A / BC:
  Total URLs:        50,000
  Downloaded:        48,500
  Marked:            45,000
  Pending downloads:  1,450
  Pending marks:      3,500
```

Use `--date`, `--start` and `--end` to filter by date range.

### `maap state pending`

List items pending at each stage.

```bash
# Pending downloads (URLs)
maap state pending COLLECTION PRODUCT BASELINE --type downloads

# Pending downloads for a date range
maap state pending COLLECTION PRODUCT BASELINE --type downloads --start 2025-01-01 --end 2025-01-31

# Pending marks (local paths)
maap state pending COLLECTION PRODUCT BASELINE --type marks
```

**Use in scripts:**
```bash
# Download all pending
maap state pending COLLECTION PRODUCT BASELINE --type downloads | while read url; do
    maap download COLLECTION PRODUCT BASELINE --url "$url"
done

# Process all pending
maap state pending COLLECTION PRODUCT BASELINE --type marks | while read path; do
    process_file "$path" && \
    maap state mark "$path"
done
```

### `maap state mark`

Mark files as processed. Paths are automatically parsed to determine collection/product/baseline.

```bash
# Single file
maap state mark /data/EarthCARE/.../file.h5

# Multiple files
maap state mark file1.h5 file2.h5 file3.h5

# From a list
maap state mark --file processed.txt
```

### `maap state cleanup`

Delete source files that have been marked.

```bash
# Preview what would be deleted
maap state cleanup COLLECTION PRODUCT BASELINE --dry-run

# Actually delete
maap state cleanup COLLECTION PRODUCT BASELINE
```

## Complete Pipeline Example

```bash
#!/bin/bash
COLLECTION="EarthCAREL2Validated_MAAP"
PRODUCT="CPR_CLD_2A"
BASELINE="BC"

# Phase 1: Discover URLs (search saves to registry)
maap search $COLLECTION $PRODUCT $BASELINE \
    --start 2025-01-01 --end 2025-12-31 \
    --registry-save

# Phase 2: Download pending files
for url in $(maap state pending $COLLECTION $PRODUCT $BASELINE --type downloads); do
    maap download $COLLECTION $PRODUCT $BASELINE --url "$url"
done

# Phase 3: Process downloaded files
for path in $(maap state pending $COLLECTION $PRODUCT $BASELINE --type marks); do
    if process_file "$path"; then
        maap state mark "$path"
    fi
done

# Phase 4: Cleanup processed source files
maap state cleanup $COLLECTION $PRODUCT $BASELINE
```

Or use `maap sync` which combines phases 1-2:

```bash
# Automated: runs discovery + download
maap sync $COLLECTION $PRODUCT $BASELINE --days-back 30

# Then just handle processing + cleanup
for path in $(maap state pending $COLLECTION $PRODUCT $BASELINE --type marks); do
    process_file "$path" && maap state mark "$path"
done
maap state cleanup $COLLECTION $PRODUCT $BASELINE
```

## State File Examples

### url_20251225.txt
```
https://catalog.maap.eo.esa.int/data/.../ECA_EXBC_CPR_CLD_2A_20251225T001234Z_20251225T012345Z_08962F.h5|/data/EarthCARE/EarthCAREL2Validated_MAAP/CPR_CLD_2A/BC/2025/12/25/ECA_EXBC_CPR_CLD_2A_20251225T001234Z_20251225T012345Z_08962F.h5
https://catalog.maap.eo.esa.int/data/.../ECA_EXBC_CPR_CLD_2A_20251225T023456Z_20251225T034567Z_08963A.h5|/data/EarthCARE/EarthCAREL2Validated_MAAP/CPR_CLD_2A/BC/2025/12/25/ECA_EXBC_CPR_CLD_2A_20251225T023456Z_20251225T034567Z_08963A.h5
```

### dwl_20251225.txt
```
https://catalog.maap.eo.esa.int/data/.../ECA_EXBC_CPR_CLD_2A_20251225T001234Z_20251225T012345Z_08962F.h5|/data/EarthCARE/EarthCAREL2Validated_MAAP/CPR_CLD_2A/BC/2025/12/25/ECA_EXBC_CPR_CLD_2A_20251225T001234Z_20251225T012345Z_08962F.h5
```

### mrk_20251225.txt
```
/data/EarthCARE/EarthCAREL2Validated_MAAP/CPR_CLD_2A/BC/2025/12/25/ECA_EXBC_CPR_CLD_2A_20251225T001234Z_20251225T012345Z_08962F.h5
```

## Troubleshooting

### "State shows 0 URLs but I know there's data"

Check that URLs were saved with `--registry-save`:
```bash
maap search COLLECTION PRODUCT BASELINE --start DATE --end DATE --registry-save
```

### "Pending downloads is wrong"

State files might be out of sync. Check your state directory (run `maap config` to see the path):
```bash
ls -la {registry_dir}/urls/EarthCARE/COLLECTION/PRODUCT/BASELINE/
ls -la {registry_dir}/downloads/EarthCARE/COLLECTION/PRODUCT/BASELINE/
```

### "Cleanup deleted files I still need"

Only run cleanup AFTER confirming processing succeeded:
```bash
# Safe pattern
process_file "$path" && maap state mark "$path"

# Unsafe pattern (marks before confirming success)
maap state mark "$path"
process_file "$path"  # If this fails, file is already marked!
```
