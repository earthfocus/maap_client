"""Shared types and helpers for mission modules (stdlib only)."""

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping, Optional


@dataclass(frozen=True)
class ProductName:
    """Metadata read from a product filename or URL."""

    mission: str  # "ECA" | "AE" | "BIO" | "FLX"
    product: str  # product directory name (or file stem fallback)
    filename: str  # basename of the URL path
    product_type: Optional[str] = None
    baseline: Optional[str] = None
    agency: Optional[str] = None
    sensing_time: Optional[datetime] = None
    creation_time: Optional[datetime] = None
    orbit_frame: Optional[str] = None
    fields: Mapping[str, Optional[str]] = field(default_factory=dict)  # mission extras


@dataclass(frozen=True)
class FilterSpec:
    """A mission filter: CLI/API option, STAC queryable and ProductName.fields key."""

    option: str  # "track" | "frame" | "repeat_cycle" | "major_cycle"
    queryable: str  # e.g. "track", "eofeos:repeat_cycle_id"
    field: str  # key in ProductName.fields, for offline (registry) filtering


def parse_filter_values(value: str) -> list[str]:
    """
    Parse a comma list of non-negative integers into unpadded decimal strings.

    Example: "002, 12" -> ["2", "12"]. MAAP matches these queryables only
    unpadded ('2' matches, '002' finds nothing). Duplicates are removed,
    first-seen order is kept.

    Raises:
        ValueError: If any entry is not a non-negative integer.
    """
    values: list[str] = []
    for part in value.split(","):
        token = part.strip()
        if not token.isdecimal():
            raise ValueError(f"invalid value '{token}': must be non-negative integers")
        unpadded = str(int(token))
        if unpadded not in values:
            values.append(unpadded)
    return values


def split_product_url(url: str) -> tuple[str, str]:
    """
    Split a product URL into (product, relative path inside the product).

    Archive URLs repeat the product directory name twice in a row
    (``.../<P>/<P>/<relpath>``); the relative path is everything after the
    second occurrence. Without a repeated segment (e.g. a bare filename) the
    product is the stem of the basename and the relative path is the basename.
    """
    parts = url.split("/")
    for i in range(len(parts) - 1):
        # all-digit segments are skipped: the .../MM/DD/ date folders repeat
        # (e.g. 2026/01/01) without being a product directory
        if parts[i] and not parts[i].isdigit() and parts[i] == parts[i + 1]:
            return parts[i], "/".join(parts[i + 2:])
    basename = os.path.basename(url)
    return os.path.splitext(basename)[0], basename


def parse_timestamp(value: str, fmt: str) -> Optional[datetime]:
    """
    Parse a timestamp of a product name as UTC.

    The ESA special validity values ``00000000T000000`` (beginning of
    mission) and ``99999999T999999`` (end of mission) are not valid dates
    and yield None, as does any other malformed value.
    """
    try:
        return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class Mission:
    """Base class of a mission module; one instance per mission."""

    name: str
    code: str  # mission code in filenames: "ECA", "AE", ...
    prefix: str  # product-name prefix, matched case-insensitively
    collections: tuple[str, ...]
    start: str
    end: str
    default_formats: tuple[str, ...]
    filters: tuple[FilterSpec, ...] = ()
    orbit_offline: bool
    orbit_frame_suffix: bool
    dedup_products: frozenset[str] = frozenset()
    no_orbit_products: frozenset[str] = frozenset()

    def available_filters(self) -> tuple[str, ...]:
        """Filter options of the mission: orbit, frame letters where orbits carry them, then its filters."""
        letters = ("frame",) if self.orbit_frame_suffix else ()
        return ("orbit",) + letters + tuple(spec.option for spec in self.filters)

    def parse(self, url: str) -> ProductName:
        """Parse a product filename or URL."""
        raise NotImplementedError

    def product_name(self, url: str) -> str:
        """
        Name to parse the product fields from: the basename when it is a
        product name of this mission, else the product directory of the URL
        (some enclosures are named differently, e.g. ``L1A_<start>__<stop>.nc``).
        """
        basename = os.path.basename(url)
        if basename.upper().startswith(self.prefix.upper()):
            return basename
        return split_product_url(url)[0]

    def data_url(self, filename: str) -> Optional[str]:
        """Rebuild the download URL from a filename, or None when not derivable."""
        return None
