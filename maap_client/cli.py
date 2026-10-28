"""Command-line interface for MAAP client."""

import argparse
import logging
import sys
from pathlib import Path

from maap_client.constants import DEFAULT_MISSION, TOKEN_RENEW_URL, __version__
from maap_client.cli_helpers import filter_options
from maap_client.exceptions import classify_exit_code
from maap_client.filters import option_flag
from maap_client.missions import MISSIONS
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
    cmd_mission_list,
    cmd_mission_show,
    cmd_mission_use,
    cmd_token,
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


def add_mission_option(parser: argparse.ArgumentParser) -> None:
    """
    Accept --mission after a sub-command too. SUPPRESS leaves the top-level
    value in place when the sub-command copy is not given; when given, it wins.
    """
    parser.add_argument(
        "--mission",
        default=argparse.SUPPRESS,
        help="Mission when the collection or URLs do not decide it (same as the top-level --mission)",
    )


def add_filter_options(group) -> None:
    """
    One option per filter declared by any mission (e.g. --frame, --track),
    with the help of each mission that has it. Values stay plain strings,
    parsed once the command's mission is known.
    """
    for option, help_text in filter_options().items():
        metavar = option.upper()
        group.add_argument(option_flag(option), metavar=f"{metavar}[,{metavar}...]", help=help_text)


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
        "--mission",
        help=f"Mission ({', '.join(MISSIONS)}) when the collection or URLs "
             f"do not decide it (default: MAAP_MISSION, 'maap mission use', config, {DEFAULT_MISSION})",
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
    add_mission_option(list_parser)
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
    add_mission_option(catalog_update)
    catalog_update.set_defaults(func=cmd_catalog_update)

    catalog_build = catalog_sub.add_parser(
        "build",
        help="Build metadata catalog for a collection",
        description="Build a metadata catalog with time ranges and product counts for a collection.",
        usage="%(prog)s [collection [product [baseline]]] [options]",
        epilog="""Notes:
  Products and baselines are retrieved from the queryables catalog. If new
  products or baselines are available, run 'maap catalog update' first.""",
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

    # Output options group
    build_output_group = catalog_build.add_argument_group("output options")
    build_output_group.add_argument(
        "--out-dir", "-o", type=Path, help="Output directory"
    )

    add_mission_option(catalog_build)
    catalog_build.set_defaults(func=cmd_catalog_build)

    # --- search subcommand (unified: time-based or orbit-based) ---
    search_parser = subparsers.add_parser(
        "search",
        help="Search for products (by date, time range or orbit)",
        description="Search for product URLs using time-based or orbit-based queries.",
        epilog="Note: --date, --start/--end, --days-back and --orbit are mutually exclusive.\n"
               "--frame combines with any time option or with a frame-less --orbit.",
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
        "--date", help="Single date (YYYY-MM-DD) or exact datetime (YYYY-MM-DDTHH:MM:SSZ)"
    )
    filter_exclusive.add_argument(
        "--days-back", "-d", type=int, help="Days to look back from now"
    )
    filter_exclusive.add_argument(
        "--orbit",
        help="Orbit-based search: orbit number with optional frame letter "
             "(e.g., '1525' for all frames, '01525F' for one)"
    )
    filter_exclusive.add_argument(
        "--start", "-s", help="Start datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)"
    )
    filter_group.add_argument(
        "--end", "-e", help="End datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)"
    )
    add_filter_options(filter_group)

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
    other_group.add_argument(
        "--format",
        default=None,
        help="zip, all, or a file extension; default per mission",
    )
    other_group.add_argument(
        "--newest-first", action="store_true",
        help="Return URLs sorted newest-first by sensing time",
    )
    add_mission_option(search_parser)
    search_parser.set_defaults(func=cmd_search)

    # --- download subcommand ---
    no_offline_orbit = [m.name for m in MISSIONS.values() if m.orbit_offline == "none"]
    no_offline_orbit_note = (
        f" (not for {' or '.join(no_offline_orbit)}, whose names carry no absolute orbit)"
        if no_offline_orbit else ""
    )
    download_parser = subparsers.add_parser(
        "download",
        help="Download products",
        description="Download products from MAAP, a URL, URL file, or saved registry files.",
        epilog="""
Notes:
  --url, --url-file, and --registry are mutually exclusive download source modes;
  one of them is required.
  --date, --start/--end, --orbit and the mission filters (--frame, --track, ...)
  filter registry entries and only apply with --registry. They match against
  filenames (no MAAP query).
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Positional arguments
    download_parser.add_argument("collection", type=non_empty_string, help="Collection name")
    download_parser.add_argument("product", type=non_empty_string, help="Product type")
    download_parser.add_argument("baseline", nargs="?", default=None, help="Baseline version (optional)")

    # Download source group (mutually exclusive, optional)
    source_group = download_parser.add_argument_group(
        "download source (required: --url, --url-file, or --registry)"
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
        "--date", help="Single date (YYYY-MM-DD) or exact datetime (YYYY-MM-DDTHH:MM:SSZ)"
    )
    filter_exclusive.add_argument(
        "--days-back", "-d", type=int, help="Days to look back from now"
    )
    filter_exclusive.add_argument(
        "--start", "-s", help="Start datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)"
    )
    filter_group.add_argument(
        "--end", "-e", help="End datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)"
    )
    add_filter_options(filter_group)
    filter_group.add_argument(
        "--orbit",
        help="Filter registry entries by orbit (e.g., '1525' or '01525E'), matched "
             "against filenames; works even for products MAAP does not index by orbit"
             + no_offline_orbit_note
    )

    # Output options group
    output_group = download_parser.add_argument_group("output options")
    output_group.add_argument(
        "--out-dir", "-o", type=Path, help="Output directory"
    )
    output_group.add_argument(
        "--dry-run", action="store_true", help="Show what would be downloaded"
    )
    output_group.add_argument(
        "--product-dir", action="store_true",
        help="Put each product's files in a folder named after the product, keeping its internal sub-folders"
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
    other_group.add_argument(
        "--newest-first", action="store_true",
        help="Download newest sensing times first",
    )
    add_mission_option(download_parser)
    download_parser.set_defaults(func=cmd_download)

    # --- get subcommand ---
    get_parser = subparsers.add_parser(
        "get",
        help="Search and download products in one step",
        description="Search for products from MAAP API and download them immediately.",
        epilog="""
Notes:
  --date, --start/--end, --days-back and --orbit are mutually exclusive.
  --frame combines with any time option or with a frame-less --orbit.
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
        "--date", help="Single date (YYYY-MM-DD) or exact datetime (YYYY-MM-DDTHH:MM:SSZ)"
    )
    filter_exclusive.add_argument(
        "--days-back", "-d", type=int, help="Days to look back from now"
    )
    filter_exclusive.add_argument(
        "--orbit",
        help="Orbit-based search: orbit number with optional frame letter "
             "(e.g., '1525' for all frames, '01525F' for one)"
    )
    filter_exclusive.add_argument(
        "--start", "-s", help="Start datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)"
    )
    filter_group.add_argument(
        "--end", "-e", help="End datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)"
    )
    add_filter_options(filter_group)

    # Output options group
    output_group = get_parser.add_argument_group("output options")
    output_group.add_argument(
        "--out-dir", "-o", type=Path, help="Output directory"
    )
    output_group.add_argument(
        "--dry-run", action="store_true", help="Show what would be downloaded"
    )
    output_group.add_argument(
        "--product-dir", action="store_true",
        help="Put each product's files in a folder named after the product, keeping its internal sub-folders"
    )

    # Other options group
    other_group = get_parser.add_argument_group("other options")
    other_group.add_argument(
        "--max-items", "-n", type=int, default=50000,
        help="Maximum items to get"
    )
    other_group.add_argument(
        "--format",
        default=None,
        help="zip, all, or a file extension; default per mission",
    )
    other_group.add_argument(
        "--newest-first", action="store_true",
        help="Search and download newest sensing times first",
    )
    add_mission_option(get_parser)
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
    add_filter_options(sync_parser)
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
    sync_parser.add_argument(
        "--format",
        default=None,
        help="zip, all, or a file extension; default per mission",
    )
    sync_parser.add_argument(
        "--product-dir", action="store_true",
        help="Put each product's files in a folder named after the product, keeping its internal sub-folders"
    )
    sync_parser.add_argument(
        "--newest-first", action="store_true",
        help="Search and download newest sensing times first",
    )
    add_mission_option(sync_parser)
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
    add_mission_option(state_show)
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
    add_mission_option(state_pending)
    state_pending.set_defaults(func=cmd_state_pending)

    state_mark = state_sub.add_parser(
        "mark",
        help="Mark files as processed",
        description="Mark files as processed for cleanup tracking.",
    )
    state_mark.add_argument("paths", nargs="*", help="Local file paths to mark")
    state_mark.add_argument("--file", "-f", type=Path, help="File with paths to mark")
    add_mission_option(state_mark)
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
    add_mission_option(state_cleanup)
    state_cleanup.set_defaults(func=cmd_state_cleanup)

    # --- config subcommand ---
    config_parser = subparsers.add_parser(
        "config",
        help="Show loaded configuration",
        description="Show the currently loaded configuration including all paths and settings.",
    )
    add_mission_option(config_parser)
    config_parser.set_defaults(func=cmd_config)

    # --- mission subcommand ---
    mission_parser = subparsers.add_parser(
        "mission",
        help="List, select or show missions",
        description="List the known missions, persist the active one, or show a mission profile.",
    )
    mission_sub = mission_parser.add_subparsers(dest="mission_cmd", required=True)

    mission_list = mission_sub.add_parser(
        "list",
        help="List missions, marking the active one",
        description="List the known missions; the active one is marked with where the choice came from.",
    )
    add_mission_option(mission_list)
    mission_list.set_defaults(func=cmd_mission_list)

    mission_use = mission_sub.add_parser(
        "use",
        help="Persist the active mission",
        description="Persist the mission used by commands whose collection or URLs do not decide it.",
    )
    mission_use.add_argument("name", type=non_empty_string, help="Mission name")
    mission_use.set_defaults(func=cmd_mission_use)

    mission_show = mission_sub.add_parser(
        "show",
        help="Show a mission profile",
        description="Show the effective profile of a mission: dates, default formats, filters, collections.",
    )
    mission_show.add_argument("name", nargs="?", default=None, help="Mission name (default: active mission)")
    add_mission_option(mission_show)
    mission_show.set_defaults(func=cmd_mission_show)

    # --- token subcommand ---
    token_parser = subparsers.add_parser(
        "token",
        help="Show when the offline token expires",
        description="Show when the offline token in the credentials file expires (read from "
                    "the token itself, no request). Renew it at " + TOKEN_RENEW_URL,
    )
    token_parser.add_argument("--days-left", action="store_true",
                              help="Print only the whole days left (negative once expired)")
    token_parser.set_defaults(func=cmd_token)

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
        return classify_exit_code(e)


if __name__ == "__main__":
    sys.exit(main())
