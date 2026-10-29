"""Utility functions for MAAP client."""

from datetime import date, datetime, timezone
from typing import Optional

from maap_client.exceptions import InvalidRequestError
from maap_client.missions import NO_BASELINE


def normalize_format(value: str) -> str:
    """Canonical format token, as --format and default_format take it: " .H5 " -> "h5"."""
    return value.strip().lower().lstrip(".")


def normalize_baseline(baseline: Optional[str]) -> Optional[str]:
    """The baseline as given, except NO_BASELINE in any case -> NO_BASELINE."""
    if baseline and baseline.upper() == NO_BASELINE:
        return NO_BASELINE
    return baseline


def to_zulu(dt: datetime) -> str:
    """Convert datetime to ISO 8601 Zulu format (UTC with Z suffix)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_date(dt: Optional[datetime]) -> Optional[date]:
    """UTC calendar day of a datetime (naive means UTC), or None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def to_stac_datetime(start: datetime, end: datetime) -> list[str]:
    """
    Convert start/end datetimes to STAC datetime list format.

    Args:
        start: Start datetime
        end: End datetime

    Returns:
        ['ISO_START', 'ISO_END'] list for STAC API
    """
    return [to_zulu(start), to_zulu(end)]


def timezone_is_aware(dt: datetime) -> bool:
    """Check if a datetime object is timezone-aware."""
    return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None


def format_time_range(start: datetime | None, end: datetime | None) -> str:
    """Format optional datetime range for verbose output."""
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    if start and end:
        return f" [{start.strftime(fmt)} - {end.strftime(fmt)}]"
    elif start:
        return f" [from {start.strftime(fmt)}]"
    elif end:
        return f" [to {end.strftime(fmt)}]"
    return ""


def parse_datetime(dt_str: str) -> datetime:
    """Parse datetime string in ISO or date-only format.

    Supports:
    - ISO 8601 with T: "2024-05-28T00:00:00Z" or "2024-05-28T00:00:00+00:00"
    - ISO 8601 without timezone: "2024-05-28T00:00:00" (assumes UTC)
    - Date only: "2024-05-28" (assumes UTC)

    Raises:
        ValueError: If the datetime string cannot be parsed
    """
    if "T" in dt_str:
        # ISO format with time
        dt_str = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(dt_str)
        # If no timezone was specified, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    else:
        # Date only - assume UTC
        return datetime.strptime(dt_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def normalize_time_range(
    start: Optional[datetime],
    end: Optional[datetime],
    mission_start: datetime,
    mission_end: datetime,
) -> tuple[datetime, datetime]:
    """
    Normalize and clamp a time range to mission bounds and current time.

    - Defaults start to mission_start if None
    - Defaults end to min(now, mission_end) if None
    - Clamps start to be >= mission_start
    - Clamps end to be <= min(now, mission_end)

    Args:
        start: Optional start datetime
        end: Optional end datetime
        mission_start: Mission start datetime
        mission_end: Mission end datetime

    Returns:
        Tuple of (start, end) datetimes clamped to valid bounds

    Raises:
        InvalidRequestError: If the range does not overlap the mission period
            (up to now), e.g. a recent --days-back window of an ended mission
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)

    # Cap at current time (no point searching future dates)
    end_cap = min(now, mission_end)

    # Default and clamp start
    t0 = max(start if start else mission_start, mission_start)

    # Default and clamp end
    t1 = min(end if end else end_cap, end_cap)

    if t0 > t1:
        raise InvalidRequestError(
            f"{to_zulu(start or t0)} to {to_zulu(end or t1)} is outside the mission period "
            f"{to_zulu(mission_start)} to {to_zulu(end_cap)}"
        )
    return t0, t1


def parse_orbit(value: str) -> tuple[int, Optional[str]]:
    """
    Parse an orbit spec in dual form.

    '1525' or '01525' -> (1525, None); '01525E' -> (1525, 'E'). Whether a
    mission takes a frame letter, and which, is checked by
    filters.resolve_filters against the mission's frame filter.

    Raises:
        ValueError: If the value is not digits optionally followed by one letter.
    """
    orbit_str = value.strip().upper()
    frame: Optional[str] = None
    if orbit_str and orbit_str[-1].isalpha():
        frame = orbit_str[-1]
        orbit_str = orbit_str[:-1]
    if not orbit_str.isdigit():
        raise ValueError(
            f"invalid orbit '{value.strip()}': expected digits with optional frame letter "
            f"(e.g. '1525' or '01525E')"
        )
    return int(orbit_str), frame
