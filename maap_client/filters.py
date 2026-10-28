"""Filtering of product URLs/paths by sensing time, orbit, frame and mission fields, and validation of the filter arguments."""

from datetime import datetime
from typing import Optional, Union

from maap_client.exceptions import InvalidRequestError
from maap_client.missions import parse_product
from maap_client.missions.base import Mission
from maap_client.utils import has_orbit_letter, parse_frames, parse_orbit, timezone_is_aware


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
    Validate and canonicalize a list of frame letters.

    Used for the frame letters of orbits (resolve_orbit_frames).

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
            f"--frame cannot be used when --orbit already includes a frame letter; "
            f"use --orbit {orbit_num} --frame {','.join(frames)}"
        )
    return orbit_num, [orbit_letter] if orbit_letter else frames


def option_flag(option: str) -> str:
    """CLI flag of a filter option: "repeat_cycle" -> "--repeat-cycle"."""
    return "--" + option.replace("_", "-")


FilterValues = Union[str, int, list]


def _value_list(values: Optional[FilterValues]) -> list:
    """Filter values as a list: one str/int (a str may be a comma list) or a list of them."""
    if values is None:
        return []
    return [values] if isinstance(values, (str, int)) else list(values)


def merge_frames(
    frames: Optional[list[str]], filters: Optional[dict[str, FilterValues]]
) -> Optional[dict[str, FilterValues]]:
    """filters with the API alias ``frames=[...]`` merged into ``filters["frame"]``."""
    if not frames:
        return filters
    merged = dict(filters or {})
    merged["frame"] = list(frames) + _value_list(merged.get("frame"))
    return merged


def resolve_filters(
    mission: Mission,
    orbit: Optional[str],
    filters: Optional[dict[str, FilterValues]],
    registry: bool = False,
) -> tuple[Optional[int], dict[str, list[str]]]:
    """
    Validate an orbit spec and filters against the mission's declarations.

    The only validation of the filter options of the CLI and the API. Values
    may be str (a comma list) or int, alone or in a list, and are parsed by
    the mission's FilterSpec. The frame letter of an orbit ('01525E') is
    merged into the "frame" filter on missions with orbit_frame_letter.

    Args:
        mission: Mission the request is for
        orbit: Orbit spec ('1525' or '01525E'), or None
        filters: Filter option (e.g. "track") -> values
        registry: True for offline (registry) filtering, where the orbit
            must be readable from the product names

    Returns:
        (orbit number or None, filter option -> canonical values) without
        empty filters.

    Raises:
        InvalidRequestError: On an option the mission does not have, a
            malformed value or orbit, an orbit frame letter on a mission
            without them or together with frames, or a registry orbit on a
            mission whose names carry no absolute orbit.
    """
    given = {option: _value_list(values) for option, values in (filters or {}).items()}
    given = {option: values for option, values in given.items() if values}
    specs = {spec.option: spec for spec in mission.filters}
    for option in given:
        if option not in specs:
            raise InvalidRequestError(
                f"{mission.name} has no {option_flag(option)}; "
                f"available filters: {', '.join(map(option_flag, mission.available_filters()))}"
            )
    if orbit and not mission.orbit_frame_letter and has_orbit_letter(orbit):
        raise InvalidRequestError(f"{mission.name} orbits take no frame letter: --orbit {orbit.strip()}")
    if orbit and registry and mission.orbit_offline == "none":
        raise InvalidRequestError(
            f"{mission.name} product names carry no absolute orbit: --orbit only works with search"
        )

    resolved: dict[str, list[str]] = {}
    for option, values in given.items():
        try:
            resolved[option] = specs[option].parse(",".join(str(value) for value in values))
        except ValueError as e:
            # prefixed with the flag unless the parser's message already names
            # the option (e.g. "invalid frame 'X': must be letters A-H")
            message = str(e)
            if not message.startswith(f"invalid {option} "):
                message = f"{option_flag(option)}: {message}"
            raise InvalidRequestError(message) from e
    letters = resolved.get("frame") if mission.orbit_frame_letter else None
    orbit_num, letters = resolve_orbit_frames(orbit, letters)
    if letters:
        resolved["frame"] = letters
    return orbit_num, resolved
