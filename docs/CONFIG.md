# Configuration Module Documentation

This document describes the `MaapConfig` dataclass used to configure the MAAP client.

## Overview

`MaapConfig` is a Python dataclass that centralizes all configuration for the MAAP client. It supports multiple configuration sources with a defined priority order:

1. **Environment variables** (highest priority)
2. **TOML config file** (`~/.maap/config.toml`)
3. **Built-in defaults** (lowest priority)

## Configuration Priority

```
┌─────────────────────────────────────────────────────────────────┐
│                    Environment Variables                        │
│                                                                 │
│  MAAP_DATA_DIR, MAAP_CATALOG_DIR, MAAP_REGISTRY_DIR, etc.      │
│  (Highest priority - always wins if set)                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ overrides
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     TOML Config File                            │
│                                                                 │
│  ~/.maap/config.toml                                            │
│  (Used if exists, overridden by env vars)                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ overrides
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Built-in Defaults                          │
│                                                                 │
│  From constants.py: ./data, ./catalogs, ./registry, etc.        │
│  (Lowest priority - used if nothing else specified)             │
└─────────────────────────────────────────────────────────────────┘
```

## MaapConfig Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `data_dir` | `Path` | `./data` | Root directory for downloaded files |
| `catalog_dir` | `Path` | `./catalogs` | Directory for downloaded queryables |
| `built_catalog_dir` | `Path` | `./built_catalogs` | Directory for built catalog JSONs |
| `registry_dir` | `Path` | `./registry` | Directory for state/registry tracking files |
| `credentials_file` | `Path` | `~/.maap/credentials.txt` | Path to credentials file |
| `catalog_url` | `str` | `https://catalog.maap.eo.esa.int/catalogue` | STAC catalog API URL |
| `token_url` | `str` | `https://iam.maap.eo.esa.int/.../token` | OAuth2 token endpoint |
| `mission` | `str` | `EarthCARE` | Mission name |
| `mission_start` | `str` | `2024-05-28T00:00:00Z` | Mission start date (ISO 8601) |
| `mission_end` | `str` | `2045-12-31T23:59:59Z` | Mission end date (ISO 8601) |
| `collections` | `list[str]` | (EarthCARE collections) | List of known collection names |

## Environment Variables

| Variable | Maps To | Example |
|----------|---------|---------|
| `MAAP_DATA_DIR` | `data_dir` | `/data/earthcare` |
| `MAAP_CATALOG_DIR` | `catalog_dir` | `/data/catalogs` |
| `MAAP_BUILT_CATALOG_DIR` | `built_catalog_dir` | `/data/built_catalogs` |
| `MAAP_REGISTRY_DIR` | `registry_dir` | `/data/registry` |
| `MAAP_CREDENTIALS_FILE` | `credentials_file` | `/secrets/creds.txt` |
| `MAAP_CATALOG_URL` | `catalog_url` | `https://...` |
| `MAAP_MISSION_START` | `mission_start` | `2024-06-01T00:00:00Z` |
| `MAAP_MISSION_END` | `mission_end` | `2025-12-31T23:59:59Z` |

## TOML Config File

Default location: `~/.maap/config.toml`

### Full Example

```toml
[paths]
data_dir = "./data"
catalog_dir = "./catalogs"
built_catalog_dir = "./built_catalogs"
registry_dir = "./registry"
credentials_file = "~/.maap/credentials.txt"

[api]
catalog_url = "https://catalog.maap.eo.esa.int/catalogue"
token_url = "https://iam.maap.eo.esa.int/realms/esa-maap/protocol/openid-connect/token"

[mission]
name = "EarthCARE"
start = "2024-05-28T00:00:00Z"
end = "2045-12-31T23:59:59Z"
# collections = [...]        # Replace default collections
# collections_extend = [...] # Add to default collections
```

### Minimal Example

Only specify what you want to change:

```toml
[paths]
data_dir = "/mnt/storage/earthcare"
credentials_file = "/etc/maap/credentials.txt"
```

### Collection Configuration

You can either replace or extend the default collections:

```toml
[mission]
# Replace entire collection list (removes EarthCARE defaults)
collections = [
    "AeolusL1BProducts",
    "AeolusL2AProducts",
]

# OR extend existing collections (keeps EarthCARE defaults)
collections_extend = [
    "AeolusL1BProducts",
    "AeolusL2AProducts",
]
```

## Class Methods

### `MaapConfig.load()`

**Recommended method** - Loads configuration with full priority handling.

```python
from maap_client.config import MaapConfig

# Load with default priority (env -> ~/.maap/config.toml -> defaults)
config = MaapConfig.load()

# Load from specific TOML file
config = MaapConfig.load(config_path=Path("/etc/maap/config.toml"))
```

### `MaapConfig.from_env()`

Load from environment variables only.

```python
import os
from maap_client.config import MaapConfig

os.environ["MAAP_DATA_DIR"] = "/data/earthcare"
config = MaapConfig.from_env()
print(config.data_dir)  # Path('/data/earthcare')
```

### `MaapConfig.from_file()`

Load from TOML file only.

```python
from pathlib import Path
from maap_client.config import MaapConfig

config = MaapConfig.from_file(Path("~/.maap/config.toml").expanduser())
```

### `MaapConfig()` (Direct Instantiation)

Create with explicit values.

```python
from pathlib import Path
from maap_client.config import MaapConfig

config = MaapConfig(
    data_dir=Path("/data/earthcare"),
    credentials_file=Path("/secrets/creds.txt"),
)
```

### `config.ensure_directories()`

Creates all configured directories if they don't exist.

```python
config = MaapConfig.load()
config.ensure_directories()
# Creates: data_dir, catalog_dir, built_catalog_dir, registry_dir
# Also creates parent directory for credentials_file
```

## Usage Examples

### With MaapClient

```python
from maap_client import MaapClient, MaapConfig

# Default config (recommended)
client = MaapClient()

# Custom config
config = MaapConfig(
    data_dir=Path("/data/earthcare"),
    credentials_file=Path("./my_credentials.txt"),
)
client = MaapClient(config=config)

# Access config from client
print(client.config.data_dir)
```

### Environment Variable Override

```bash
# Shell
export MAAP_DATA_DIR=/mnt/data
export MAAP_CREDENTIALS_FILE=/etc/maap/credentials.txt
python my_script.py
```

```python
# Python
from maap_client import MaapClient

client = MaapClient()
print(client.config.data_dir)  # Path('/mnt/data')
print(client.config.credentials_file)  # Path('/etc/maap/credentials.txt')
```

### Docker/Container Usage

```dockerfile
ENV MAAP_DATA_DIR=/data
ENV MAAP_REGISTRY_DIR=/data/registry
ENV MAAP_CREDENTIALS_FILE=/secrets/credentials.txt
```

### CI/CD Pipeline

```yaml
# GitHub Actions
env:
  MAAP_DATA_DIR: /tmp/maap_data
  MAAP_CREDENTIALS_FILE: ${{ secrets.MAAP_CREDENTIALS_PATH }}
```

## Directory Structure

When `ensure_directories()` is called, this structure is created:

```
./                          # Working directory
├── data/                   # data_dir: Downloaded HDF5 files
│   └── EarthCARE/
│       └── {collection}/
│           └── {product}/
│               └── {baseline}/
│                   └── yyyy/mm/dd/
├── catalogs/               # catalog_dir: Downloaded queryables
│   └── {collection}_queryables.json
├── built_catalogs/         # built_catalog_dir: Processed catalogs
│   └── {collection}_collection.json
└── registry/               # registry_dir: Workflow tracking
    ├── urls/
    ├── downloads/
    └── marked/

~/.maap/                    # User config directory
├── config.toml             # Configuration file
└── credentials.txt         # OAuth2 credentials
```

## Dependencies

The module imports from:

| Import | From Module | Purpose |
|--------|-------------|---------|
| `DEFAULT_CATALOG_URL`, `DEFAULT_TOKEN_URL` | constants.py | Default API endpoints |
| `DEFAULT_MISSION`, `DEFAULT_MISSION_START`, `DEFAULT_MISSION_END` | constants.py | Mission defaults |
| `DEFAULT_DATA_DIR`, etc. | constants.py | Default paths |
| `DEFAULT_COLLECTIONS` | constants.py | Default collection list |

## Design Decisions

### Why a Dataclass?

1. **Immutable by convention**: Clear what configuration is set
2. **Default values**: Built-in defaults without boilerplate
3. **Type hints**: IDE support and validation
4. **Easy serialization**: Can convert to dict if needed

### Why Three Loading Methods?

- `from_env()`: Container/CI environments where env vars are standard
- `from_file()`: User machines with persistent config
- `load()`: Combines both with clear precedence

### Why Environment Variables Override Files?

1. **12-Factor App**: Env vars are the standard for runtime config
2. **Security**: Credentials can be injected without files
3. **Flexibility**: Override specific values without editing files
4. **Container-friendly**: Works with Docker, K8s secrets, etc.

### Why TOML?

1. **Standard library** (Python 3.11+): `tomllib` is built-in
2. **Human readable**: Easy to edit by hand
3. **Sections**: Natural grouping (`[paths]`, `[api]`, `[mission]`)
4. **No ambiguity**: Unlike YAML, TOML has clear semantics

## File Locations

| File | Purpose |
|------|---------|
| `maap_client/config.py` | MaapConfig dataclass (this module) |
| `maap_client/constants.py` | Default values for config |
| `~/.maap/config.toml` | User configuration file |
| `~/.maap/credentials.txt` | Default credentials location |
