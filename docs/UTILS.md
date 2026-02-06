# Utilities Module Documentation

This document describes the utility functions in `maap_client/utils.py`.

## Overview

The `utils.py` module provides datetime conversion utilities used throughout the MAAP client for handling ISO 8601 timestamps.

## Functions

### to_zulu()

Convert a datetime to ISO 8601 Zulu format (UTC with Z suffix).

```python
def to_zulu(dt: datetime) -> str:
    """Convert datetime to ISO 8601 Zulu format (UTC with Z suffix)."""
```

**Behavior**:
1. If datetime is naive (no timezone), assumes UTC
2. Converts to UTC timezone
3. Removes microseconds
4. Returns string in format: `YYYY-MM-DDTHH:MM:SSZ`

**Examples**:

```python
from datetime import datetime, timezone
from maap_client.utils import to_zulu

# Naive datetime (no timezone) - assumes UTC
dt = datetime(2024, 12, 15, 14, 30, 0)
print(to_zulu(dt))  # "2024-12-15T14:30:00Z"

# Aware datetime in UTC
dt = datetime(2024, 12, 15, 14, 30, 0, tzinfo=timezone.utc)
print(to_zulu(dt))  # "2024-12-15T14:30:00Z"

# Datetime with microseconds (stripped)
dt = datetime(2024, 12, 15, 14, 30, 0, 123456, tzinfo=timezone.utc)
print(to_zulu(dt))  # "2024-12-15T14:30:00Z"

# Datetime in different timezone (converted to UTC)
from zoneinfo import ZoneInfo
dt = datetime(2024, 12, 15, 9, 30, 0, tzinfo=ZoneInfo("America/New_York"))
print(to_zulu(dt))  # "2024-12-15T14:30:00Z" (EST → UTC)
```

**Used by**:
- `MaapSearcher` for STAC API datetime parameters
- CLI for converting user-provided dates

### parse_datetime()

Parse datetime string in ISO or date-only format.

```python
def parse_datetime(dt_str: str) -> datetime:
    """Parse datetime string in ISO or date-only format."""
```

**Supported formats**:
- ISO 8601 with T: `"2024-05-28T00:00:00Z"` or `"2024-05-28T00:00:00+00:00"`
- Date only: `"2024-05-28"` (assumes UTC midnight)

**Raises**:
- `ValueError`: If the datetime string cannot be parsed

**Examples**:

```python
from maap_client.utils import parse_datetime

# ISO format with Z suffix
dt = parse_datetime("2024-12-15T14:30:00Z")
print(dt)  # 2024-12-15 14:30:00+00:00

# ISO format with offset
dt = parse_datetime("2024-12-15T14:30:00+00:00")
print(dt)  # 2024-12-15 14:30:00+00:00

# Date only (assumes UTC midnight)
dt = parse_datetime("2024-12-15")
print(dt)  # 2024-12-15 00:00:00+00:00

# Invalid format raises ValueError
try:
    parse_datetime("15/12/2024")
except ValueError as e:
    print(f"Error: {e}")
```

**Used by**:
- CLI for parsing `--start` and `--end` arguments
- `MaapConfig` for parsing mission start/end dates

## Usage Examples

### In Search Operations

```python
from datetime import datetime, timezone
from maap_client.utils import to_zulu

# Build STAC datetime parameter
start = datetime(2024, 12, 1, tzinfo=timezone.utc)
end = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

datetime_param = f"{to_zulu(start)}/{to_zulu(end)}"
# "2024-12-01T00:00:00Z/2024-12-31T23:59:59Z"
```

### In CLI Arguments

```python
import argparse
from maap_client.utils import parse_datetime

parser = argparse.ArgumentParser()
parser.add_argument("--start", type=parse_datetime)
parser.add_argument("--end", type=parse_datetime)

# Works with: --start 2024-12-01 --end 2024-12-31T23:59:59Z
args = parser.parse_args()
```

### Combining Both

```python
from maap_client.utils import parse_datetime, to_zulu

# Parse user input
user_input = "2024-12-15"
dt = parse_datetime(user_input)

# Convert for API
api_format = to_zulu(dt)
print(api_format)  # "2024-12-15T00:00:00Z"
```

## Dependencies

| Import | From | Purpose |
|--------|------|---------|
| `datetime`, `timezone` | datetime (stdlib) | Datetime handling |

## Design Decisions

### Why Zulu Format?

1. **STAC API requirement**: ESA MAAP API expects Z-suffix format
2. **Unambiguous**: Z clearly indicates UTC
3. **Compact**: Shorter than `+00:00` offset notation
4. **Standard**: Widely recognized in scientific data systems

### Why Strip Microseconds?

1. **API compatibility**: STAC API doesn't need microsecond precision
2. **Readability**: Cleaner output in logs and URLs
3. **Consistency**: All timestamps have same format

### Why Assume UTC for Naive Datetimes?

1. **Safety**: Better to assume UTC than local timezone
2. **Consistency**: All MAAP data is in UTC
3. **Simplicity**: Users don't need to specify timezone

### Why Support Date-Only Format?

1. **User convenience**: `--start 2024-12-01` is easier than full ISO
2. **Common use case**: Most searches are by date, not time
3. **Sensible default**: Midnight UTC is logical start of day

## File Location

| File | Purpose |
|------|---------|
| `maap_client/utils.py` | This module |
