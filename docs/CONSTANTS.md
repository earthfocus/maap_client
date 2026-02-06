# Constants Module Documentation

This document describes the constants defined in `maap_client/constants.py`.

## Overview

The `constants.py` module defines all hard-coded values used throughout the MAAP client:

- Package version
- API endpoints
- Mission information
- Collection list
- Default paths
- Download settings

## Constants Reference

### Package Version

```python
__version__ = "0.1.0"
```

Used for package identification and `--version` CLI flag.

### API Endpoints

| Constant | Value | Purpose |
|----------|-------|---------|
| `DEFAULT_CATALOG_URL` | `https://catalog.maap.eo.esa.int/catalogue` | STAC catalog API for search |
| `DEFAULT_TOKEN_URL` | `https://iam.maap.eo.esa.int/realms/esa-maap/protocol/openid-connect/token` | OAuth2 token endpoint |

### Mission Information

| Constant | Value | Purpose |
|----------|-------|---------|
| `DEFAULT_MISSION` | `"EarthCARE"` | Mission name for path generation |
| `DEFAULT_MISSION_START` | `"2024-05-28T00:00:00Z"` | Mission start date (launch) |
| `DEFAULT_MISSION_END` | `"2045-12-31T23:59:59Z"` | Mission end date (projected) |

### Collections

```python
DEFAULT_COLLECTIONS = [
    "EarthCAREL0L1Products_MAAP",
    "EarthCAREL1InstChecked_MAAP",
    "EarthCAREL1Validated_MAAP",
    "EarthCAREL2InstChecked_MAAP",
    "EarthCAREL2Products_MAAP",
    "EarthCAREL2Validated_MAAP",
    "EarthCAREAuxiliary_MAAP",
    "EarthCAREOrbitData_MAAP",
    "EarthCAREXMETL1DProducts10_MAAP",
    "JAXAL2InstChecked_MAAP",
    "JAXAL2Products_MAAP",
    "JAXAL2Validated_MAAP",
]
```

#### Collection Categories

| Category | Collections | Description |
|----------|-------------|-------------|
| **L0/L1 Raw** | `EarthCAREL0L1Products_MAAP` | Raw instrument data |
| **L1 Checked** | `EarthCAREL1InstChecked_MAAP` | Instrument-checked L1 |
| **L1 Validated** | `EarthCAREL1Validated_MAAP` | Validated L1 products |
| **L2 Checked** | `EarthCAREL2InstChecked_MAAP` | Instrument-checked L2 |
| **L2 Products** | `EarthCAREL2Products_MAAP` | Standard L2 products |
| **L2 Validated** | `EarthCAREL2Validated_MAAP` | Validated L2 products |
| **Auxiliary** | `EarthCAREAuxiliary_MAAP` | Auxiliary data |
| **Orbit** | `EarthCAREOrbitData_MAAP` | Orbit/ephemeris data |
| **XMET** | `EarthCAREXMETL1DProducts10_MAAP` | XMET L1D products |
| **JAXA L2** | `JAXAL2*_MAAP` | JAXA-processed L2 products |

### Default Paths

| Constant | Default Value | Purpose |
|----------|---------------|---------|
| `DEFAULT_DATA_DIR` | `./data` | Downloaded HDF5 files |
| `DEFAULT_CATALOG_DIR` | `./catalogs` | Downloaded queryables |
| `DEFAULT_BUILT_CATALOG_DIR` | `./built_catalogs` | Processed catalogs |
| `DEFAULT_REGISTRY_DIR` | `./registry` | Registry/state tracking files |
| `DEFAULT_CREDENTIALS_FILE` | `~/.maap/credentials.txt` | OAuth2 credentials |

### Download Settings

| Constant | Value | Purpose |
|----------|-------|---------|
| `DEFAULT_CHUNK_SIZE` | `8192` | Bytes per read during download |
| `DEFAULT_TIMEOUT` | `30` | HTTP request timeout (seconds) |

## Usage

### Direct Import

```python
from maap_client.constants import (
    __version__,
    DEFAULT_CATALOG_URL,
    DEFAULT_TOKEN_URL,
    DEFAULT_MISSION,
    DEFAULT_MISSION_START,
    DEFAULT_MISSION_END,
    DEFAULT_COLLECTIONS,
)

print(f"MAAP Client v{__version__}")
print(f"Mission: {DEFAULT_MISSION}")
print(f"Collections: {len(DEFAULT_COLLECTIONS)}")
```

### Via MaapClient

```python
from maap_client import MaapClient

client = MaapClient()
print(f"Mission: {client.config.mission}")
for c in client.config.collections:
    print(f"  - {c}")
```

### In Configuration

```python
from maap_client.config import MaapConfig
from maap_client.constants import DEFAULT_MISSION_START

config = MaapConfig.load()
print(config.mission_start)  # Uses DEFAULT_MISSION_START as default
```

## Dependencies

This module has no internal dependencies - it only uses Python builtins.

## Design Decisions

### Why Separate Constants File?

1. **Single source of truth**: All magic values in one place
2. **Easy updates**: Change URLs or dates without searching codebase
3. **Import flexibility**: Other modules can import just what they need
4. **Testing**: Can mock constants for testing

### Why Hardcoded Collections?

1. **Offline availability**: Works without network access
2. **Fast startup**: No API call needed to list collections
3. **Stability**: Collection list rarely changes
4. **Validation**: Can validate user input against known list

### Why ISO 8601 Dates?

1. **Unambiguous**: Clear timezone (Z = UTC)
2. **Sortable**: String comparison works correctly
3. **Standard**: Widely supported by APIs and libraries
4. **Parseable**: `datetime.fromisoformat()` works directly

## File Location

| File | Purpose |
|------|---------|
| `maap_client/constants.py` | This module |
