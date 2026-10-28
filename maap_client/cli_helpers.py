"""CLI helper functions for MAAP client.

This module contains CLI-specific utilities for argument parsing and validation.
Business logic has been moved to MaapClient facade methods.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from maap_client import MaapClient, MaapConfig
from maap_client.exceptions import InvalidRequestError
from maap_client.filters import option_flag
from maap_client.mission_select import resolve_mission
from maap_client.missions import MISSIONS
from maap_client.registry import read_pairs_file
from maap_client.utils import parse_datetime, parse_orbit


def input_urls(args: argparse.Namespace) -> list[str]:
    """
    URLs a 'download' command was given (--url or the --url-file contents).

    Other commands' --url-file is an output file. A missing or unreadable
    file yields no URLs; cmd_download reports it.
    """
    if getattr(args, "command", None) != "download":
        return []
    if getattr(args, "url", None):
        return [args.url]
    url_file = getattr(args, "url_file", None)
    if url_file:
        try:
            return [url for url, _ in read_pairs_file(url_file)]
        except OSError:
            return []
    return []


def load_config(args: argparse.Namespace) -> tuple[MaapConfig, str]:
    """
    Load the configuration of the mission a command works on.

    Returns (config, source) where source says how the mission was chosen
    (see mission_select.resolve_mission).
    """
    config_path = getattr(args, "config", None)
    base = MaapConfig.load(config_path)
    mission, source = resolve_mission(
        getattr(args, "collection", None), input_urls(args), getattr(args, "mission", None), base
    )
    return MaapConfig.load(config_path, mission=mission.name), source


def apply_cli_overrides(args: argparse.Namespace, config: MaapConfig) -> MaapConfig:
    """The config with the global CLI overrides (-d/--data-dir) applied."""
    if getattr(args, "data_dir", None):
        config.data_dir = args.data_dir
    return config


def _client(args: argparse.Namespace, config: MaapConfig) -> MaapClient:
    """Create MaapClient from a config, with the CLI overrides applied."""
    return MaapClient(apply_cli_overrides(args, config))


def get_client(args: argparse.Namespace) -> MaapClient:
    """Create MaapClient from parsed arguments."""
    config, _ = load_config(args)
    return _client(args, config)


def mission_client(args: argparse.Namespace, mission: str) -> MaapClient:
    """Create MaapClient for a mission the command already determined."""
    return _client(args, MaapConfig.load(getattr(args, "config", None), mission=mission))


def resolve_date_args(args: argparse.Namespace) -> tuple[Optional[datetime], Optional[datetime]]:
    """
    Resolve --date, --days-back, or --start/--end to (start, end) datetimes.

    Priority: --date > --days-back > --start/--end

    Args:
        args: Parsed argparse namespace

    Returns:
        Tuple of (start, end) datetimes or (None, None)

    Raises:
        InvalidRequestError: If a date or time cannot be parsed
    """
    try:
        return _resolve_date_args(args)
    except ValueError as e:
        raise InvalidRequestError(f"invalid date or time: {e}") from e


def _resolve_date_args(args: argparse.Namespace) -> tuple[Optional[datetime], Optional[datetime]]:
    """resolve_date_args; ValueError on a date or time that cannot be parsed."""
    # --date mode
    if hasattr(args, 'date') and args.date:
        if 'T' in args.date:
            start = parse_datetime(args.date)
            end = start + timedelta(minutes=1)
            return start, end
        else:
            return parse_datetime(f"{args.date}T00:00:00Z"), parse_datetime(f"{args.date}T23:59:59Z")

    # --days-back mode
    if getattr(args, 'days_back', None) is not None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        start = now - timedelta(days=args.days_back)
        return start, now

    # --start/--end mode
    start_str = getattr(args, 'start', None)
    end_str = getattr(args, 'end', None)
    start = parse_datetime(start_str) if start_str else None
    if end_str:
        if 'T' in end_str:
            end = parse_datetime(end_str)
        else:
            # Date-only: set to end of day (23:59:59)
            end = parse_datetime(f"{end_str}T23:59:59Z")
    else:
        end = None
    return start, end


def validate_time_args(args: argparse.Namespace, orbit_is_filter: bool = False) -> Optional[str]:
    """
    Validate time-based arguments and return error message if invalid.

    Validates mutual exclusivity and logical constraints for:
    --date, --start, --end, --days-back, --orbit

    Args:
        args: Parsed argparse namespace
        orbit_is_filter: If True, --orbit is a client-side filename filter
            (as in `download --registry`) rather than a query mode, so it may
            be combined with time-based options. Orbit format validation and
            the orbit-with-letter + --frame conflict check still apply.

    Returns:
        Error message string if validation fails, None if valid
    """
    has_date = bool(getattr(args, 'date', None))
    has_start = bool(getattr(args, 'start', None))
    has_end = bool(getattr(args, 'end', None))
    has_days_back = getattr(args, 'days_back', None) is not None
    has_orbit = bool(getattr(args, 'orbit', None))

    # --date cannot be used with --start or --end
    if has_date and has_start:
        return "--date cannot be used with --start"
    if has_date and has_end:
        return "--date cannot be used with --end (date already specifies full day)"

    # --days-back cannot be used with --date, --start, or --end
    if has_days_back and has_date:
        return "--days-back cannot be used with --date"
    if has_days_back and has_start:
        return "--days-back cannot be used with --start"
    if has_days_back and has_end:
        return "--days-back cannot be used with --end"

    # --orbit cannot be used with any time-based options (unless orbit is a
    # client-side filter, e.g. download --registry, where it's combinable)
    if not orbit_is_filter:
        if has_orbit and has_date:
            return "--orbit cannot be used with --date"
        if has_orbit and has_start:
            return "--orbit cannot be used with --start"
        if has_orbit and has_end:
            return "--orbit cannot be used with --end"
        if has_orbit and has_days_back:
            return "--orbit cannot be used with --days-back"

    # Validate start <= end if both provided
    if has_start and has_end:
        start = parse_datetime(args.start)
        end = parse_datetime(args.end)
        if start > end:
            return f"--start ({args.start}) must be before --end ({args.end})"

    # Validate --orbit format (its frame letter is checked against the
    # mission by filters.resolve_filters)
    if has_orbit:
        try:
            parse_orbit(args.orbit)
        except ValueError as e:
            return str(e)

    return None


def filter_options() -> dict[str, str]:
    """
    Filter options of all missions (argparse dests, first-seen order) -> help,
    e.g. "frame" -> "EarthCARE: frame letter(s) A-H; Biomass: frame number(s)".
    """
    helps: dict[str, list[str]] = {}
    for mission in MISSIONS.values():
        for spec in mission.filters:
            helps.setdefault(spec.option, []).append(f"{mission.name}: {spec.help}")
    return {option: "; ".join(parts) for option, parts in helps.items()}


def collect_filter_args(args: argparse.Namespace) -> Optional[dict[str, str]]:
    """
    The filter options given (option -> raw value), or None.

    Values are validated by the client (filters.resolve_filters) once the
    mission is known; InvalidRequestError there means exit code 4.
    """
    given = {option: getattr(args, option) for option in filter_options() if getattr(args, option, None)}
    return given or None


def validate_download_filter_args(args: argparse.Namespace) -> Optional[str]:
    """Registry-only filters and time options (--frame/--orbit/--date/...) must not be used with --url/--url-file."""
    if not getattr(args, 'registry', False):
        for option in (*filter_options(), "orbit", "date", "start", "end", "days_back"):
            if getattr(args, option, None) is not None:
                return f"{option_flag(option)} requires --registry"
    return None


def report_failed_days(failed_days: list) -> None:
    """Print skipped days in a stable, parseable format.

    Entries are (day, error) tuples, or (baseline, day, error) from sync.
    """
    for entry in failed_days:
        if len(entry) == 3:
            baseline, day, err = entry
            print(f"FAILED DAY: {baseline.upper()} {day.isoformat()} ({err})", file=sys.stderr)
        else:
            day, err = entry
            print(f"FAILED DAY: {day.isoformat()} ({err})", file=sys.stderr)
    if failed_days:
        print(
            f"WARNING: {len(failed_days)} day(s) failed; "
            "re-run the same command to fill the gaps",
            file=sys.stderr,
        )
