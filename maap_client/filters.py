"""Filtering of product URLs/paths by sensing time, orbit, frame and mission fields, and validation of the filter arguments."""

from datetime import datetime
from typing import Optional

from maap_client.exceptions import InvalidRequestError
from maap_client.missions import parse_product
from maap_client.missions.base import Mission
from maap_client.utils import parse_frames, parse_orbit, timezone_is_aware


def _sensing_time(item: str) -> Optional[datetime]:
    parsed = parse_product(item)
    return parsed.sensing_time if parsed else None


def _orbit_frame(item: str) -> Optional[str]:
    parsed = parse_product(item)
    return parsed.orbit_frame if parsed else None


def sort_by_sensing_time(items: list[str], reverse: bool = False) -> list[str]:
    """
    Sort URLs/paths by their sensing time. Items with no extractable
    sensing time are appended at the end regardless of order.
    """
    with_dt: list[tuple[datetime, str]] = []
    without_dt: list[str] = []
    for item in items:
        dt = _sensing_time(item)
        if dt is None:
            without_dt.append(item)
        else:
            with_dt.append((dt, item))
    with_dt.sort(key=lambda x: x[0], reverse=reverse)
    return [item for _, item in with_dt] + without_dt


def filter_by_sensing_time(
    items: list[str],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> list[str]:
    """
    Filter URLs/paths by sensing time within [start, end].

    Items where sensing_time cannot be extracted are dropped.

    Args:
        items: List of URLs or paths to filter
        start: Optional start datetime (inclusive). None means no lower bound.
        end: Optional end datetime (inclusive). None means no upper bound.

    Returns:
        Filtered list of items with valid sensing times within range
    """
    if start is None and end is None:
        return items
    result = []
    for item in items:
        sensing_time = _sensing_time(item)
        if sensing_time is None:
            continue
        if (start is None or start <= sensing_time) and (end is None or sensing_time <= end):
            result.append(item)
    return result


def filter_by_orbit_frame(
    items: list[str],
    orbit: Optional[int] = None,
    frames: Optional[list[str]] = None,
) -> list[str]:
    """
    Filter URLs/paths by orbit number and/or frame letters (from filename).

    Items where orbit/frame cannot be extracted are dropped, mirroring
    filter_by_sensing_time. Frame letters must be uppercase (canonical
    form from parse_frames).

    Args:
        items: List of URLs or paths to filter
        orbit: Optional orbit number to match. None means no orbit constraint.
        frames: Optional list of frame letters to match. None/empty means
                no frame constraint.

    Returns:
        Filtered list of items
    """
    if orbit is None and not frames:
        return items
    result = []
    for item in items:
        orbit_frame = _orbit_frame(item)
        if orbit_frame is None:
            continue
        if orbit_frame[-1].isalpha():
            item_orbit, item_frame = int(orbit_frame[:-1]), orbit_frame[-1]
        else:
            item_orbit, item_frame = int(orbit_frame), None
        if orbit is not None and item_orbit != orbit:
            continue
        if frames and item_frame not in frames:
            continue
        result.append(item)
    return result


def filter_by_fields(items: list[str], filters: dict[str, list[str]], mission: Mission) -> list[str]:
    """
    Filter URLs/paths by the mission filters read from their product names.

    An item is kept when, for every filter, its ProductName attribute is one
    of the accepted values (decimal strings, as parse_filter_values gives
    them, compared as integers). A blank field in the name (e.g. Biomass L2
    ``C___``) matches nothing.

    Args:
        items: List of URLs or paths to filter
        filters: Filter option (e.g. "track") -> accepted values
        mission: Mission whose filters and parser apply

    Raises:
        ValueError: If a filter is not one of the mission's, or some items'
            product names carry none of the mission's filter fields
            (undocumented grammar); the message names those product types.
    """
    if not filters:
        return items
    specs = {spec.option: spec for spec in mission.filters}
    unknown = [option for option in filters if option not in specs]
    if unknown:
        raise ValueError(f"{mission.name} has no {', '.join(unknown)} filter")

    accepted = {option: {int(value) for value in values} for option, values in filters.items()}
    result = []
    undocumented: set[str] = set()
    for item in items:
        parsed = mission.parse(item)
        if all(getattr(parsed, spec.attribute) is None for spec in specs.values()):
            undocumented.add(parsed.product_type or parsed.product)
            continue
        if all(getattr(parsed, specs[option].attribute) in ints for option, ints in accepted.items()):
            result.append(item)
    if undocumented:
        raise ValueError(
            f"Cannot filter by {', '.join(filters)} offline: the product names of "
            f"{', '.join(sorted(undocumented))} do not carry these fields; use search instead"
        )
    return result


def validate_time_range(
    start: Optional[datetime],
    end: Optional[datetime],
    orbit: Optional[str] = None,
) -> None:
    """
    Validate time parameters. Called by methods with time/orbit args.

    Args:
        start: Start datetime
        end: End datetime
        orbit: Orbit+frame string

    Raises:
        InvalidRequestError: If validation fails
    """
    # Timezone awareness (prevents subtle bugs from naive datetimes)
    if start is not None and not timezone_is_aware(start):
        raise InvalidRequestError(
            "'start' must be timezone-aware (e.g., datetime(..., tzinfo=timezone.utc))."
        )
    if end is not None and not timezone_is_aware(end):
        raise InvalidRequestError(
            "'end' must be timezone-aware (e.g., datetime(..., tzinfo=timezone.utc))."
        )

    # Mutual exclusivity
    if orbit and (start or end):
        raise InvalidRequestError(
            "Cannot combine 'orbit' with 'start'/'end'. "
            "Use orbit for orbit-based search, or start/end for time-based."
        )

    # Logical order
    if start and end and start > end:
        raise InvalidRequestError(
            f"'start' must be before 'end' (got {start} > {end})."
        )

def normalize_frames(frames: Optional[list[str]]) -> Optional[list[str]]:
    """
    Validate and canonicalize a frames list (Python API entry point).

    CLI callers already get canonical uppercase letters from `frames_arg`;
    this normalizes frames passed directly via the Python API.

    Returns:
        None if frames is None/empty, otherwise the uppercased, validated list.

    Raises:
        InvalidRequestError: If any entry is not a single letter A-H.
    """
    if not frames:
        return None
    try:
        return parse_frames(",".join(frames))
    except ValueError as e:
        raise InvalidRequestError(str(e)) from e

def resolve_orbit_frames(
    orbit: Optional[str],
    frames: Optional[list[str]],
) -> tuple[Optional[int], Optional[list[str]]]:
    """
    Parse a dual-form orbit spec and merge with a frames list.

    '01525E' -> (1525, ['E']); '1525' -> (1525, frames).

    Raises:
        InvalidRequestError: If the orbit is malformed, or it includes a
                             frame letter while frames is also given.
    """
    frames = normalize_frames(frames)
    if not orbit:
        return None, frames
    try:
        orbit_num, orbit_letter = parse_orbit(orbit)
    except ValueError as e:
        raise InvalidRequestError(str(e)) from e
    if orbit_letter and frames:
        raise InvalidRequestError(
            f"orbit '{orbit.strip()}' already includes a frame letter; "
            f"use orbit '{orbit_num}' together with the frames list instead"
        )
    return orbit_num, [orbit_letter] if orbit_letter else frames
