"""Command-line interface for MAAP client."""

import argparse
import logging
import sys
from pathlib import Path

from maap_client.constants import __version__
from maap_client.cli_commands import (
    cmd_catalog_update,
    cmd_catalog_build,
    cmd_list,
    cmd_search,
    cmd_download,
    cmd_get,
    cmd_sync,
    cmd_state_show,
    cmd_state_pending,
    cmd_state_mark,
    cmd_state_cleanup,
    cmd_config,
)


def setup_logging(verbosity: int = 0, quiet: bool = False) -> None:
    """Configure logging based on CLI flags.

    Log levels:
        --quiet: WARNING (suppress progress output)
        default: INFO (show progress messages)
        -v:      INFO (same as default)
        -vv:     DEBUG (show debug output)
    """
    if quiet:
        level = logging.WARNING
    elif verbosity >= 2:
        level = logging.DEBUG
    else:
        # Default to INFO for progress messages (logger.info)
        level = logging.INFO

    # Clean format for CLI output (just the message, like print())
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stderr,
    )


def non_empty_string(value: str) -> str:
    """Argparse type that rejects empty strings."""
    if not value or not value.strip():
        raise argparse.ArgumentTypeError("cannot be empty")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="maap",
        description="Python client for ESA MAAP satellite data access",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"maap-client {__version__}",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help="Configuration file path",
    )
    parser.add_argument(
        "-d",
        "--data-dir",
        type=Path,
        help="Data directory (overrides config)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v, -vv); use --quiet to suppress",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-error output",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- list subcommand (browse collections/products/baselines) ---
    list_parser = subparsers.add_parser(
        "list",
        help="Browse catalog collections, products, or baselines",
        description="List catalog information from local files.",
        usage="%(prog)s [collection [product [baseline]]]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    list_parser.add_argument("collection", nargs="?", default=None, help="Collection name")
    list_parser.add_argument("product", nargs="?", default=None, help="Product type")
    list_parser.add_argument("baseline", nargs="?", default=None, help="Baseline version")
    list_parser.add_argument(
        "--latest-baseline",
        action="store_true",
        help="Latest baseline",
    )
    list_parser.add_argument(
        "--verify",
        action="store_true",
        help="Refresh from API to get latest products/baselines",
    )
    list_parser.set_defaults(func=cmd_list)

    # --- catalog subcommand (manage catalogs) ---
    catalog_parser = subparsers.add_parser(
        "catalog",
        help="Manage catalog queryables and build catalogs",
        description="Manage local catalog metadata for faster browsing and searching.",
    )
    catalog_sub = catalog_parser.add_subparsers(dest="catalog_cmd", required=True)

    catalog_update = catalog_sub.add_parser(
        "update",
        help="Download/update catalog queryables",
        description="Download or refresh catalog queryables from the MAAP server.",
    )
    catalog_update.add_argument(
        "collection", nargs="?", default=None, help="Collection name (if omitted, updates all)"
    )
    catalog_update.add_argument(
        "--out-dir", "-o", type=Path, help="Output directory"
    )
    catalog_update.set_defaults(func=cmd_catalog_update)

    catalog_build = catalog_sub.add_parser(
        "build",
        help="Build metadata catalog for a collection",
        description="Build a metadata catalog with time ranges and product counts for a collection.",
        usage="%(prog)s [collection [product [baseline]]] [options]",
        epilog="""Notes:
  --date, --days-back and --start/--end are mutually exclusive.

  Products and baselines are retrieved from the queryables catalog. If new
  products or baselines are available, run 'maap catalog update' first.

  When extending an existing catalog with time increases (--start/--end),
  the total count may be inaccurate because new files may have appeared
  in time periods covered by previous searches. Use --force for accurate
  counts (rebuilds from scratch).""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    catalog_build.add_argument("collection", nargs="?", default=None, help="Collection name (if omitted, builds all)")
    catalog_build.add_argument("product", nargs="?", default=None, help="Product type (if omitted, builds all products)")
    catalog_build.add_argument("baseline", nargs="?", default=None, help="Baseline version (if omitted, builds all baselines)")
    catalog_build.add_argument(
        "--force",
        action="store_true",
        help="Delete existing catalog and rebuild from scratch",
    )

    # Filtering options group
    build_filter_group = catalog_build.add_argument_group("filtering options")
    build_filter_group.add_argument(
        "--latest-baseline",
        action="store_true",
        help="Latest baseline",
    )
    build_filter_exclusive = build_filter_group.add_mutually_exclusive_group()
    build_filter_exclusive.add_argument(
        "--start", "-s",
        help="Start datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)",
    )
    build_filter_exclusive.add_argument(
        "--date",
        help="Single date (YYYY-MM-DD) or exact datetime (YYYY-MM-DDTHH:MM:SSZ)",
    )
    build_filter_exclusive.add_argument(
        "--days-back",
        type=int,
        help="Days to look back from now",
    )
    build_filter_group.add_argument(
        "--end", "-e",
        help="End datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)",
    )

    # Output options group
    build_output_group = catalog_build.add_argument_group("output options")
    build_output_group.add_argument(
        "--out-dir", "-o", type=Path, help="Output directory"
    )

    catalog_build.set_defaults(func=cmd_catalog_build)

    # --- search subcommand (unified: time-based or orbit-based) ---
    search_parser = subparsers.add_parser(
        "search",
        help="Search for products (by date, time range or orbit)",
        description="Search for product URLs using time-based or orbit-based queries.",
        epilog="Note: --date, --start/--end, and --orbit are mutually exclusive filtering options.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    search_parser.add_argument("collection", type=non_empty_string, help="Collection name")
    search_parser.add_argument("product", type=non_empty_string, help="Product type")
    search_parser.add_argument(
        "baseline",
        nargs="?",
        default=None,
        help="Baseline version (if omitted, searches all baselines)"
    )

    # Filtering options group
    filter_group = search_parser.add_argument_group("filtering options")
    filter_exclusive = filter_group.add_mutually_exclusive_group()
    filter_exclusive.add_argument(
        "--start", "-s", help="Start datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)"
    )
    filter_exclusive.add_argument(
        "--date", help="Single date (YYYY-MM-DD) or exact datetime (YYYY-MM-DDTHH:MM:SSZ)"
    )
    filter_exclusive.add_argument(
        "--days-back", "-d", type=int, help="Days to look back from now"
    )
    filter_exclusive.add_argument(
        "--orbit", help="Orbit+frame for orbit-based search (e.g., '01525F')"
    )
    filter_group.add_argument(
        "--end", "-e", help="End datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)"
    )

    # Output options group
    output_group = search_parser.add_argument_group("output options")
    output_group.add_argument("--url-file", "-o", type=Path, help="Output file for URLs (flat file)")
    output_group.add_argument(
        "--registry-save",
        action="store_true",
        help="Save URLs to partitioned registry files (by sensing date)"
    )

    # Other options group
    other_group = search_parser.add_argument_group("other options")
    other_group.add_argument(
        "--max-items", "-n", type=int, default=50000,
        help="Maximum items to search"
    )
    other_group.add_argument(
        "--use-catalog",
        action="store_true",
        help="Use built catalog for time bounds (faster, may be stale)"
    )
    search_parser.set_defaults(func=cmd_search)

    # --- download subcommand ---
    download_parser = subparsers.add_parser(
        "download",
        help="Download products",
        description="Download products from MAAP, a URL, URL file, or saved registry files.",
        epilog="""
Notes:
  --date and --start/--end are mutually exclusive filtering options (only with --registry).
  --url, --url-file, and --registry are mutually exclusive download source modes.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Positional arguments
    download_parser.add_argument("collection", type=non_empty_string, help="Collection name")
    download_parser.add_argument("product", type=non_empty_string, help="Product type")
    download_parser.add_argument("baseline", nargs="?", default=None, help="Baseline version (optional)")

    # Download source group (mutually exclusive, optional)
    source_group = download_parser.add_argument_group(
        "download source (if not specified, searches MAAP)"
    )
    source_exclusive = source_group.add_mutually_exclusive_group()
    source_exclusive.add_argument("--url", "-u", help="Download a single URL")
    source_exclusive.add_argument("--url-file", "-f", type=Path, help="Download URLs from file")
    source_exclusive.add_argument("--registry", action="store_true",
        help="Search from registry files")

    # Filtering options group (only with --registry)
    filter_group = download_parser.add_argument_group(
        "filtering options (only with --registry)"
    )
    filter_exclusive = filter_group.add_mutually_exclusive_group()
    filter_exclusive.add_argument(
        "--start", "-s", help="Start datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)"
    )
    filter_exclusive.add_argument(
        "--date", help="Single date (YYYY-MM-DD) or exact datetime (YYYY-MM-DDTHH:MM:SSZ)"
    )
    filter_exclusive.add_argument(
        "--days-back", "-d", type=int, help="Days to look back from now"
    )
    filter_group.add_argument(
        "--end", "-e", help="End datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)"
    )

    # Output options group
    output_group = download_parser.add_argument_group("output options")
    output_group.add_argument(
        "--out-dir", "-o", type=Path, help="Output directory"
    )
    output_group.add_argument(
        "--dry-run", action="store_true", help="Show what would be downloaded"
    )

    # Other options group
    other_group = download_parser.add_argument_group("other options")
    other_group.add_argument(
        "--max-items", "-n", type=int,
        help="Maximum items to download"
    )
    other_group.add_argument(
        "--use-catalog", action="store_true",
        help="Use built catalog for time bounds (faster, may be stale)"
    )
    download_parser.set_defaults(func=cmd_download)

    # --- get subcommand ---
    get_parser = subparsers.add_parser(
        "get",
        help="Search and download products in one step",
        description="Search for products from MAAP API and download them immediately.",
        epilog="""
Notes:
  --date, --start/--end, and --orbit are mutually exclusive filtering options.
  For advanced options (--use-catalog, --registry), use 'search' and 'download' separately.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    get_parser.add_argument("collection", type=non_empty_string, help="Collection name")
    get_parser.add_argument("product", type=non_empty_string, help="Product type")
    get_parser.add_argument(
        "baseline",
        nargs="?",
        default=None,
        help="Baseline version (if omitted, searches all baselines)"
    )

    # Filtering options group
    filter_group = get_parser.add_argument_group("filtering options")
    filter_exclusive = filter_group.add_mutually_exclusive_group()
    filter_exclusive.add_argument(
        "--start", "-s", help="Start datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)"
    )
    filter_exclusive.add_argument(
        "--date", help="Single date (YYYY-MM-DD) or exact datetime (YYYY-MM-DDTHH:MM:SSZ)"
    )
    filter_exclusive.add_argument(
        "--days-back", "-d", type=int, help="Days to look back from now"
    )
    filter_exclusive.add_argument(
        "--orbit", help="Orbit+frame for orbit-based search (e.g., '01525F')"
    )
    filter_group.add_argument(
        "--end", "-e", help="End datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)"
    )

    # Output options group
    output_group = get_parser.add_argument_group("output options")
    output_group.add_argument(
        "--out-dir", "-o", type=Path, help="Output directory"
    )
    output_group.add_argument(
        "--dry-run", action="store_true", help="Show what would be downloaded"
    )

    # Other options group
    other_group = get_parser.add_argument_group("other options")
    other_group.add_argument(
        "--max-items", "-n", type=int, default=50000,
        help="Maximum items to get"
    )
    get_parser.set_defaults(func=cmd_get)

    # --- sync subcommand ---
    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync products (for crontab)",
        description="Incrementally sync products with automatic state tracking. Designed for crontab/scheduled workflows.",
    )
    sync_parser.add_argument("collection", type=non_empty_string, help="Collection name")
    sync_parser.add_argument("product", type=non_empty_string, help="Product type")
    sync_parser.add_argument("baseline", nargs="?", default=None, help="Baseline version (if omitted, syncs all baselines)")
    # Time range options (mutually exclusive modes)
    sync_time_group = sync_parser.add_mutually_exclusive_group()
    sync_time_group.add_argument(
        "--date", help="Single date (YYYY-MM-DD) or exact datetime (YYYY-MM-DDTHH:MM:SSZ)"
    )
    sync_time_group.add_argument(
        "--days-back", "-d", type=int, help="Days to look back from now"
    )
    sync_time_group.add_argument(
        "--start", "-s", help="Start datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)"
    )
    sync_parser.add_argument(
        "--end", "-e", help="End datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)"
    )
    sync_parser.add_argument(
        "--max-items",
        "-n",
        type=int,
        default=50000,
        help="Maximum items to synchronize",
    )
    sync_parser.add_argument(
        "--out-dir", "-o", type=Path, help="Output directory"
    )
    sync_parser.set_defaults(func=cmd_sync)

    # --- state subcommand ---
    state_parser = subparsers.add_parser(
        "state",
        help="Manage state tracking",
        description="Manage download state tracking for pipeline workflows.",
    )
    state_sub = state_parser.add_subparsers(dest="state_cmd", required=True)

    state_show = state_sub.add_parser(
        "show",
        help="Show state for product+baseline",
        description="Show state summary including URLs discovered, downloaded, marked, and pending.",
    )
    state_show.add_argument("collection", type=non_empty_string, help="Collection name")
    state_show.add_argument("product", type=non_empty_string, help="Product type")
    state_show.add_argument("baseline", type=non_empty_string, help="Baseline version")
    state_show_time = state_show.add_mutually_exclusive_group()
    state_show_time.add_argument("--date", help="Single date (YYYY-MM-DD) or exact datetime (YYYY-MM-DDTHH:MM:SSZ)")
    state_show_time.add_argument("--start", "-s", help="Start datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)")
    state_show.add_argument("--end", "-e", help="End datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)")
    state_show.set_defaults(func=cmd_state_show)

    state_pending = state_sub.add_parser(
        "pending",
        help="Show pending downloads/marks",
        description="List URLs or paths that are pending download or marking.",
    )
    state_pending.add_argument("collection", type=non_empty_string, help="Collection name")
    state_pending.add_argument("product", type=non_empty_string, help="Product type")
    state_pending.add_argument("baseline", type=non_empty_string, help="Baseline version")
    state_pending.add_argument(
        "--type",
        choices=["downloads", "marks"],
        default="downloads",
        help="Type of pending items (default: %(default)s)",
    )
    state_pending_time = state_pending.add_mutually_exclusive_group()
    state_pending_time.add_argument("--date", help="Single date (YYYY-MM-DD) or exact datetime (YYYY-MM-DDTHH:MM:SSZ)")
    state_pending_time.add_argument("--start", "-s", help="Start datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)")
    state_pending.add_argument("--end", "-e", help="End datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)")
    state_pending.set_defaults(func=cmd_state_pending)

    state_mark = state_sub.add_parser(
        "mark",
        help="Mark files as processed",
        description="Mark files as processed for cleanup tracking.",
    )
    state_mark.add_argument("paths", nargs="*", help="Local file paths to mark")
    state_mark.add_argument("--file", "-f", type=Path, help="File with paths to mark")
    state_mark.set_defaults(func=cmd_state_mark)

    state_cleanup = state_sub.add_parser(
        "cleanup",
        help="Delete marked originals",
        description="Delete original files that have been marked.",
    )
    state_cleanup.add_argument("collection", type=non_empty_string, help="Collection name")
    state_cleanup.add_argument("product", type=non_empty_string, help="Product type")
    state_cleanup.add_argument("baseline", type=non_empty_string, help="Baseline version")
    state_cleanup.add_argument("--dry-run", action="store_true", help="Show what would be deleted")
    state_cleanup.set_defaults(func=cmd_state_cleanup)

    # --- config subcommand ---
    config_parser = subparsers.add_parser(
        "config",
        help="Show loaded configuration",
        description="Show the currently loaded configuration including all paths and settings.",
    )
    config_parser.set_defaults(func=cmd_config)

    return parser


def main() -> int:
    """Main CLI entry point."""
    parser = build_parser()

    # Parse and execute
    args = parser.parse_args()
    setup_logging(args.verbose, args.quiet)

    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130
    except Exception as e:
        if args.verbose >= 2:
            raise
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
