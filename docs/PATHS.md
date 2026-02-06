# Paths Module Documentation

This document describes the path generation and filename parsing utilities in `maap_client/paths.py`.

## Overview

The `paths.py` module provides utilities for:

- Generating structured file paths for downloads and registry tracking
- Parsing EarthCARE and Aeolus filenames to extract metadata
- Converting URLs to local file paths

## Filename Formats

### EarthCARE Format

EarthCARE product filenames follow a structured format:

```
ECA_XXBB_PPP_TTT_LL_YYYYMMDDTHHMMSSZ_YYYYMMDDTHHMMSSZ_OOOOOF.h5
│   ││││ │││ │││ ││ │                │                │
│   ││││ │││ │││ ││ │                │                └─ Orbit (5 digits) + Frame (1 letter)
│   ││││ │││ │││ ││ │                └─ Creation time (UTC)
│   ││││ │││ │││ ││ └─ Sensing time (UTC)
│   ││││ │││ │││ └─ Processing level (1A, 1B, 2A, 2B)
│   ││││ │││ └─ Subtype (NOM, APC, RAD, CLD, etc.)
│   ││││ └─ Instrument (CPR, MSI, BBR, ATL, BM_)
│   ││└─ Baseline version (AA, AB, BA, BC, etc.)
│   └─ Agency (EX=ESA, JX=JAXA)
└─ Mission prefix
```

**Example**:
```
ECA_EXBC_CPR_CLD_2A_20241215T143000Z_20241215T160000Z_07282E.h5
    │ ││ │   │   │  │                │                │
    │ ││ │   │   │  │                │                └─ Orbit 07282, Frame E
    │ ││ │   │   │  │                └─ Creation: 2024-12-15T16:00:00Z
    │ ││ │   │   │  └─ Sensing: 2024-12-15T14:30:00Z
    │ ││ │   │   └─ Level 2A
    │ ││ │   └─ Cloud product
    │ ││ └─ CPR instrument
    │ │└─ Baseline BC
    │ └─ ESA product
    └─ Mission ECA
```

### Aeolus Format

Aeolus product filenames follow a different structure:

```
AE_CCCC_PPP_T_N_LL_YYYYMMDDTHHMMSSMMM_DDDDDDDDD_OOOOOO_VVVV.DBL
│  │    │   │ │ ││ │                  │         │      │
│  │    │   │ │ ││ │                  │         │      └─ File version (4 digits)
│  │    │   │ │ ││ │                  │         └─ Orbit number (6 digits)
│  │    │   │ │ ││ │                  └─ Duration in milliseconds (9 digits)
│  │    │   │ │ ││ └─ Sensing time with milliseconds (UTC)
│  │    │   │ │ └─ Processing level (1A, 1B, 2A, 2B)
│  │    │   │ └─ N=Near real-time
│  │    │   └─ Type (U=Unified)
│  │    └─ Product (ALD=L1/L2 standard)
│  └─ File class (OPER, RPRO, OFFL, TEST)
└─ Mission prefix
```

**Example**:
```
AE_OPER_ALD_U_N_1B_20230422T165721033_005543989_027018_0001.DBL
   │    │   │ │ │  │                  │         │      │
   │    │   │ │ │  │                  │         │      └─ Version 0001
   │    │   │ │ │  │                  │         └─ Orbit 027018
   │    │   │ │ │  │                  └─ Duration 5543989ms
   │    │   │ │ │  └─ Sensing: 2023-04-22T16:57:21.033Z
   │    │   │ │ └─ Level 1B
   │    │   │ └─ Near real-time
   │    │   └─ Unified type
   │    └─ ALD product
   └─ Operational class
```

**Key differences:**
- **Baseline**: EarthCARE embeds baseline in filename; Aeolus has baseline in URL path
- **Timestamps**: EarthCARE uses `_YYYYMMDDTHHMMSSZ_`; Aeolus uses `_YYYYMMDDTHHMMSSMMM_` (with ms)
- **Orbit**: EarthCARE has 5 digits + frame letter; Aeolus has 6 digits
- **Extension**: EarthCARE uses `.h5`; Aeolus uses `.DBL`

## Path Generation Functions

### generate_data_path()

Generate structured path for downloaded data files.

```python
def generate_data_path(
    data_dir: Path,
    mission: str,
    collection: str,
    product_type: str,
    baseline: str,
    dt: datetime,
    filename: str,
) -> Path:
```

**Structure**: `data_dir/mission/collection/product_type/baseline/YYYY/MM/DD/filename`

```python
from pathlib import Path
from datetime import datetime, timezone
from maap_client.paths import generate_data_path

path = generate_data_path(
    data_dir=Path("./data"),
    mission="EarthCARE",
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
    dt=datetime(2024, 12, 15, tzinfo=timezone.utc),
    filename="ECA_EXBC_CPR_CLD_2A_20241215T143000Z_20241215T160000Z_07282E.h5",
)
# Path: ./data/EarthCARE/EarthCAREL2Validated_MAAP/CPR_CLD_2A/BC/2024/12/15/ECA_EXBC_...h5
```

### generate_registry_path()

Generate path for registry tracking directory.

```python
def generate_registry_path(
    registry_dir: Path,
    prefix: str,
    mission: str,
    collection: str,
    product_type: str,
    baseline: str,
) -> Path:
```

**Structure**: `registry_dir/prefix/mission/collection/product_type/baseline/`

```python
from maap_client.paths import generate_registry_path

path = generate_registry_path(
    registry_dir=Path("./registry"),
    prefix="urls",
    mission="EarthCARE",
    collection="EarthCAREL2Validated_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BC",
)
# Path: ./registry/urls/EarthCARE/EarthCAREL2Validated_MAAP/CPR_CLD_2A/BC/
```

## Filename Parsing Functions

### Common Functions (EarthCARE + Aeolus)

| Function | Description | EarthCARE | Aeolus |
|----------|-------------|-----------|--------|
| `extract_sensing_time(filename)` | First timestamp | `datetime` | `datetime` |
| `extract_orbit_frame(filename)` | Orbit identifier | `"07282E"` | `"027018"` |
| `extract_agency(filename)` | Agency code | `"EX"` or `"JX"` | `"EX"` |
| `extract_baseline(uri)` | Baseline version | From filename | From URL path |
| `extract_product(filename)` | Product type | `"CPR_CLD_2A"` | `"ALD_U_N_1B"` |

### EarthCARE-Only Functions

| Function | Description | Example |
|----------|-------------|---------|
| `extract_creation_time(filename)` | Second timestamp | `datetime` |

### Aeolus-Only Functions

| Function | Description | Example |
|----------|-------------|---------|
| `extract_file_class(filename)` | File class | `"OPER"`, `"RPRO"` |
| `extract_duration_ms(filename)` | Duration in ms | `5543989` |
| `extract_file_version(filename)` | File version | `"0001"` |

### Examples

```python
from maap_client.paths import (
    extract_sensing_time,
    extract_baseline,
    extract_product,
    extract_orbit_frame,
)

# EarthCARE
earthcare_file = "ECA_EXBC_CPR_CLD_2A_20241215T143000Z_20241215T160000Z_07282E.h5"
print(extract_sensing_time(earthcare_file))  # 2024-12-15 14:30:00+00:00
print(extract_baseline(earthcare_file))       # "BC"
print(extract_product(earthcare_file))        # "CPR_CLD_2A"
print(extract_orbit_frame(earthcare_file))    # "07282E"

# Aeolus (note: baseline from URL, not filename)
aeolus_url = "https://.../ALD_U_N_1B/1B16/2023/04/22/AE_OPER_ALD_U_N_1B_20230422T165721033_005543989_027018_0001.DBL"
aeolus_file = "AE_OPER_ALD_U_N_1B_20230422T165721033_005543989_027018_0001.DBL"
print(extract_sensing_time(aeolus_file))  # 2023-04-22 16:57:21.033000+00:00
print(extract_baseline(aeolus_url))        # "1B16" (extracted from URL path)
print(extract_baseline(aeolus_file))       # None (not in filename)
print(extract_product(aeolus_file))        # "ALD_U_N_1B"
print(extract_orbit_frame(aeolus_file))    # "027018"
```

### Baseline Extraction Details

The `extract_baseline()` function handles both missions:

- **EarthCARE**: Baseline is embedded in filename after agency code (`ECA_EXBC_...` → `BC`)
- **Aeolus**: Baseline is in URL path, not filename (`.../ALD_U_N_1B/1B16/2023/...` → `1B16`)

```python
# EarthCARE: from filename
extract_baseline("ECA_EXBC_CPR_CLD_2A_...h5")  # "BC"

# Aeolus: from URL (full path required)
extract_baseline("https://.../ALD_U_N_1B/1B16/2023/04/22/AE_OPER_...DBL")  # "1B16"
extract_baseline("AE_OPER_ALD_U_N_1B_...DBL")  # None (filename only - no baseline info)
```

## URL to Path Conversion

### url_to_local_path()

Convert a product URL to its structured local path.

```python
def url_to_local_path(
    url: str,
    data_dir: Path,
    mission: str,
    collection: str,
) -> Path:
```

Extracts product type, baseline, and sensing time from the URL/filename to generate the structured path.

```python
from pathlib import Path
from maap_client.paths import url_to_local_path

url = "https://catalog.maap.eo.esa.int/data/.../ECA_EXBC_CPR_CLD_2A_20241215T143000Z_20241215T160000Z_07282E.h5"
path = url_to_local_path(
    url=url,
    data_dir=Path("./data"),
    mission="EarthCARE",
    collection="EarthCAREL2Validated_MAAP",
)
# Path: ./data/EarthCARE/EarthCAREL2Validated_MAAP/CPR_CLD_2A/BC/2024/12/15/ECA_EXBC_...h5
```

## Design Notes

### Why Structured Paths?

1. **Organization**: Easy navigation by product/baseline/date
2. **Deduplication**: Same file always goes to same location
3. **Cleanup**: Delete old data by date directories
4. **Parallelism**: Different products/baselines in different directories

### Why Year Subdirectories?

Date-organized directories (`/YYYY/MM/DD/`) instead of flat structure:
- Keeps directories small (~50-100 files per day max)
- Fast filesystem operations
- Natural cleanup boundaries (delete whole months)

### Why Extract from Both Filename and URL?

- **EarthCARE**: All metadata in filename (baseline, timestamps, orbit)
- **Aeolus**: Baseline only in URL path, not filename
- Functions handle both cases transparently

## File Location

| File | Purpose |
|------|---------|
| `maap_client/paths.py` | This module |
