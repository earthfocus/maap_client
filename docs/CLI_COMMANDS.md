# CLI Commands Module

Internal documentation for `maap_client/cli_commands.py` and `maap_client/cli_helpers.py`.

## Overview

The CLI command layer is split across two modules:
- `cli_commands.py` contains all CLI command handlers (`cmd_*` functions)
- `cli_helpers.py` contains helper functions and shared logic used by the commands

These are separated from `cli.py` (which contains only the argument parser and entry point) for better maintainability.

## Helper Functions (cli_helpers.py)

### `get_client(args) -> MaapClient`
Create a MaapClient instance from parsed CLI arguments.

Applies overrides from CLI args (e.g., `--data-dir`) to the loaded configuration.

### `resolve_date_args(args) -> tuple[Optional[datetime], Optional[datetime]]`
Resolve time arguments to (start, end) datetimes.

**Priority:** `--date` > `--days-back` > `--start/--end`

- `--date 2024-12-01` → `(2024-12-01T00:00:00Z, 2024-12-01T23:59:59Z)`
- `--date 2024-12-01T12:00:00Z` → `(2024-12-01T12:00:00Z, 2024-12-01T12:01:00Z)`
- `--days-back 7` → `(now - 7 days, now)`
- `--start 2024-12-01 --end 2024-12-31` → `(2024-12-01T00:00:00Z, 2024-12-31T23:59:59Z)`
- `(no time args)` → `(None, None)`

### `validate_time_args(args) -> Optional[str]`
Validate time-based arguments and return an error message if invalid.

**Validates:**
- `--date` cannot be used with `--start` or `--end`
- `--days-back` cannot be used with `--date`, `--start`, or `--end`
- `--orbit` cannot be used with any time-based options
- `--start` must be before `--end` if both provided

Returns error message string if validation fails, `None` if valid.

## Command Handlers

All command handlers follow the pattern `cmd_*(args) -> int` where the return value is the exit code (0 for success, non-zero for errors).

| Handler | Command | Description |
|---------|---------|-------------|
| `cmd_catalog_update` | `maap catalog update` | Download/update catalog queryables |
| `cmd_catalog_build` | `maap catalog build` | Build metadata catalog for collections |
| `cmd_list` | `maap list` | List collections, products, baselines, or info |
| `cmd_search` | `maap search` | Search for products |
| `cmd_download` | `maap download` | Download products |
| `cmd_get` | `maap get` | Search + download in one step |
| `cmd_sync` | `maap sync` | Incremental sync for crontab |
| `cmd_state_show` | `maap state show` | Show state summary |
| `cmd_state_pending` | `maap state pending` | List pending items |
| `cmd_state_mark` | `maap state mark` | Mark files as processed |
| `cmd_state_cleanup` | `maap state cleanup` | Delete marked files |
| `cmd_config` | `maap config` | Show configuration |

### Command Handler Pattern

Each command handler:
1. Gets a `MaapClient` via `get_client(args)`
2. Validates arguments (if needed) via `validate_time_args(args)`
3. Resolves time range via `resolve_date_args(args)`
4. Calls appropriate `MaapClient` methods
5. Logs/prints output
6. Returns exit code

Example:
```python
def cmd_search(args: argparse.Namespace) -> int:
    # Validate
    if error := validate_time_args(args):
        logger.error(error)
        return 1

    # Get client and resolve args
    client = get_client(args)
    start, end = resolve_date_args(args)

    # Call facade method
    result = client.search(
        collection=args.collection,
        product_type=args.product,
        baseline=args.baseline,
        start=start,
        end=end,
        orbit=getattr(args, 'orbit', None),
        verbose=args.verbose > 0,
    )

    # Output results
    logger.info(f"Found {result.total_count} URLs")
    for url in result.urls:
        print(url)

    return 0
```

## Module Dependencies

```
cli_commands.py
├── cli_helpers (get_client, resolve_date_args, validate_time_args)
├── maap_client (MaapClient)
├── maap_client.utils (parse_datetime)
└── logging

cli_helpers.py
├── maap_client (MaapClient, MaapConfig)
└── maap_client.utils (parse_datetime)
```

## Design Notes

### Why Thin Wrappers?

The CLI commands are intentionally thin wrappers around `MaapClient` methods:

1. **Single source of truth**: Business logic lives in `MaapClient`, not scattered across CLI handlers
2. **Testability**: `MaapClient` methods can be unit tested without CLI parsing
3. **Reusability**: Same logic available in Python API and CLI
4. **Maintainability**: Changes only need to happen in one place

### Why Separate cli_helpers.py?

1. **Reusability**: Multiple commands use `get_client()` and `resolve_date_args()`
2. **Testability**: Helper functions can be tested independently
3. **Clarity**: CLI-specific utilities vs business logic clearly separated
