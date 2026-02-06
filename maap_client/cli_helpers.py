"""CLI helper functions for MAAP client.

This module contains CLI-specific utilities for argument parsing and validation.
Business logic has been moved to MaapClient facade methods.
"""

import argparse
from datetime import datetime, timedelta, timezone
from typing import Optional

from maap_client import MaapClient, MaapConfig
from maap_client.utils import parse_datetime


def get_client(args: argparse.Namespace) -> MaapClient:
    """Create MaapClient from parsed arguments."""
    config = MaapConfig.load(args.config) if args.config else MaapConfig.load()

    # Override with CLI args
    if args.data_dir:
        config.data_dir = args.data_dir

    return MaapClient(config)


def resolve_date_args(args: argparse.Namespace) -> tuple[Optional[datetime], Optional[datetime]]:
    """
    Resolve --date, --days-back, or --start/--end to (start, end) datetimes.

    Priority: --date > --days-back > --start/--end

    Args:
        args: Parsed argparse namespace

    Returns:
        Tuple of (start, end) datetimes or (None, None)
    """
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


def validate_time_args(args: argparse.Namespace) -> Optional[str]:
    """
    Validate time-based arguments and return error message if invalid.

    Validates mutual exclusivity and logical constraints for:
    --date, --start, --end, --days-back, --orbit

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

    # --orbit cannot be used with any time-based options
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

    return None
