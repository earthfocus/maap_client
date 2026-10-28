"""Filtering of product URLs/paths by sensing time, orbit, frame and mission fields.

Also validates the filter arguments.
"""

import logging
from datetime import datetime
from typing import Optional, Union

from maap_client.exceptions import InvalidRequestError
from maap_client.missions import parse_product
from maap_client.missions.base import FilterSpec, Mission
from maap_client.utils import parse_orbit, timezone_is_aware

logger = logging.getLogger(__name__)


def _sensing_time(item: str) -> Optional[datetime]:
    parsed = parse_product(item)
    return parsed.sensing_time if parsed else None


def _orbit(item: str) -> Optional[int]:
    parsed = parse_product(item)
    return parsed.orbit if parsed else None


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


def filter_by_orbit(items: list[str], orbit: Optional[int]) -> list[str]:
    """
    Filter URLs/paths by the absolute orbit read from their names.

    Items whose orbit cannot be read are dropped, mirroring
    filter_by_sensing_time. None means no orbit constraint.
    """
    if orbit is None:
        return items
    return [item for item in items if _orbit(item) == orbit]


def _unknown_option_message(mission: Mission, option: str) -> str:
    return (
        f"{mission.name} has no {option_flag(option)}; "
        f"available filters: {', '.join(map(option_flag, mission.available_filters()))}"
    )


def _canonical_attribute(spec: FilterSpec, value: object) -> Optional[str]:
    """A ProductName attribute in the canonical form of spec.parse.

    None if the value is blank or not parseable.
    """
    if value is None:
        return None
    try:
        return spec.parse(str(value))[0]
    except ValueError:
        return None


def filter_by_fields(
    items: list[str], filters: dict[str, list[str]], mission: Mission
) -> list[str]:
    """
    Filter URLs/paths by the mission filters read from their product names.

    An item is kept when, for every filter, its ProductName attribute is one
    of the accepted values, both compared in the canonical form of the
    filter's FilterSpec parser (e.g. "002" and 2 match track 2, "e" matches
    frame E). A blank field in the name (e.g. Biomass L2 ``C___``) matches
    nothing.

    Args:
        items: List of URLs or paths to filter
        filters: Filter option (e.g. "track") -> accepted values
        mission: Mission whose filters and parser apply

    Raises:
        ValueError: If a filter is not one of the mission's, a value is invalid,
            or some items' product names carry none of the mission's filter fields
            (undocumented grammar); the message names those product types.
    """
    if not filters:
        return items
    specs = {spec.option: spec for spec in mission.filters}
    for option in filters:
        if option not in specs:
            raise ValueError(_unknown_option_message(mission, option))

    accepted = {
        option: set(specs[option].parse(",".join(str(value) for value in values)))
        for option, values in filters.items()
    }
    result = []
    undocumented: set[str] = set()
    for item in items:
        parsed = mission.parse(item)
        if all(getattr(parsed, spec.attribute) is None for spec in specs.values()):
            undocumented.add(parsed.product_type or parsed.product)
            continue
        if all(
            _canonical_attribute(specs[option], getattr(parsed, specs[option].attribute)) in values
            for option, values in accepted.items()
        ):
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


def option_flag(option: str) -> str:
    """CLI flag of a filter option: "repeat_cycle" -> "--repeat-cycle"."""
    return "--" + option.replace("_", "-")


FilterValues = Union[str, int, list]


def _value_list(values: Optional[FilterValues]) -> list:
    """Filter values as a list: one str/int (a str may be a comma list) or a list of them."""
    if values is None:
        return []
    return [values] if isinstance(values, (str, int)) else list(values)


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
    parsed by the "frame" FilterSpec and becomes the "frame" filter, on
    missions with orbit_frame_letter.

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
            without them or together with a "frame" filter, or a registry orbit on a
            mission whose names carry no absolute orbit.
    """
    given = {option: _value_list(values) for option, values in (filters or {}).items()}
    given = {option: values for option, values in given.items() if values}
    specs = {spec.option: spec for spec in mission.filters}
    for option in given:
        if option not in specs:
            raise InvalidRequestError(_unknown_option_message(mission, option))
    orbit_num, orbit_letter = _parse_orbit(orbit)
    if orbit_letter and not mission.orbit_frame_letter:
        raise InvalidRequestError(
            f"{mission.name} orbits take no frame letter: --orbit {orbit.strip()}"
        )
    if orbit_num is not None and registry and mission.orbit_offline == "none":
        raise InvalidRequestError(
            f"{mission.name} product names carry no absolute orbit: --orbit only works with search"
        )

    resolved: dict[str, list[str]] = {}
    for option, values in given.items():
        resolved[option] = _parse_values(specs[option], values, option_flag(option))
    if orbit_letter:
        if "frame" in resolved:
            raise InvalidRequestError(
                f"--frame cannot be used when --orbit already includes a frame letter; "
                f"use --orbit {orbit_num} --frame {','.join(resolved['frame'])}"
            )
        flag = f"--orbit {orbit.strip()}"
        resolved["frame"] = _parse_values(specs["frame"], [orbit_letter], flag)
    return orbit_num, resolved


def _parse_orbit(orbit: Optional[str]) -> tuple[Optional[int], Optional[str]]:
    """parse_orbit of an orbit spec, or (None, None) without one."""
    if not orbit:
        return None, None
    try:
        return parse_orbit(orbit)
    except ValueError as e:
        raise InvalidRequestError(str(e)) from e


def _parse_values(spec: FilterSpec, values: list, flag: str) -> list[str]:
    """spec.parse of the values; a malformed one is an InvalidRequestError naming flag."""
    try:
        return spec.parse(",".join(str(value) for value in values))
    except ValueError as e:
        raise InvalidRequestError(f"{flag}: {e}") from e


def resolve_filter_args(
    mission: Mission,
    orbit: Optional[str],
    filters: Optional[dict[str, FilterValues]],
    registry: bool = False,
) -> tuple[Optional[int], Optional[dict[str, list[str]]]]:
    """
    resolve_filters for the client API: no filters is None rather than {}.

    Returns:
        (orbit number or None, filter option -> canonical values or None)
    """
    if not (orbit or filters):
        return None, None
    orbit_num, resolved = resolve_filters(mission, orbit, filters, registry)
    return orbit_num, resolved or None


def filter_queryables(
    mission: Mission, filters: Optional[dict[str, list[str]]]
) -> Optional[dict[str, list[str]]]:
    """Resolved filters (option -> values) as the mission's STAC queryables -> values."""
    if not filters:
        return None
    return {
        spec.queryable: filters[spec.option] for spec in mission.filters if spec.option in filters
    }


def filter_registry_urls(
    urls: list[str],
    mission: Mission,
    orbit: Optional[int],
    filters: Optional[dict[str, list[str]]],
) -> list[str]:
    """
    Filter registry URLs offline by orbit and mission filters read from
    their product names (arguments as resolve_filter_args returns them).

    Raises:
        InvalidRequestError: If orbit is given and some names of a mission
            whose names carry the orbit only sometimes have none, or a filter
            cannot be read from the names (see filter_by_fields)
    """
    if orbit is not None and mission.orbit_offline == "some":
        # Names that carry the orbit only sometimes (Aeolus L0/L1 ms
        # timestamps): reject the others instead of silently dropping them.
        # With "all" orbit-less names (EarthCARE AUX_CC*, AUX_ORBPRE,
        # MPL_ORBSCT) are dropped by filter_by_orbit.
        orbitless = sorted({
            parsed.product_type or parsed.product
            for parsed in map(mission.parse, urls)
            if parsed.orbit_frame is None
        })
        if orbitless:
            raise InvalidRequestError(
                f"Cannot filter by orbit offline: the product names of {', '.join(orbitless)} "
                f"do not carry the orbit; use search instead"
            )
    if orbit is not None:
        total = len(urls)
        urls = filter_by_orbit(urls, orbit)
        logger.info(f"{len(urls)} of {total} registry URLs match the orbit filter")
    if filters:
        total = len(urls)
        try:
            urls = filter_by_fields(urls, filters, mission)
        except ValueError as e:
            raise InvalidRequestError(str(e)) from e
        logger.info(f"{len(urls)} of {total} registry URLs match the {', '.join(filters)} filter")
    return urls
