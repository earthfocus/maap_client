"""Shared types and helpers for mission modules (stdlib only)."""

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Literal, Optional

# Baseline of the products that have none (declared per mission in
# Mission.no_baseline_products); distinct from None, a baseline not read.
NO_BASELINE = "NO_BASELINE"


@dataclass(frozen=True)
class ProductName:
    """Metadata read from a product filename or URL: the fields every mission can have."""

    mission: str  # "ECA" | "AE" | "BIO" | "FLX"
    product: str  # product directory name (or file stem fallback)
    filename: str  # basename of the URL path
    product_type: Optional[str] = None
    baseline: Optional[str] = None
    sensing_time: Optional[datetime] = None
    creation_time: Optional[datetime] = None
    orbit: Optional[int] = None  # absolute orbit, where the name carries it

    @property
    def orbit_frame(self) -> Optional[str]:
        """Legacy orbit+frame string (e.g. ``07282E``), or None for missions without one."""
        return None


@dataclass(frozen=True)
class FilterSpec:
    """A mission filter: CLI/API option, help, value parser, STAC queryable and ProductName attribute."""

    option: str  # e.g. "frame", "repeat_cycle" (CLI flag --repeat-cycle)
    help: str  # this mission's values, e.g. "frame letter(s) A-H"
    parse: Callable[[str], list[str]]  # comma list -> canonical values; raises ValueError
    queryable: str  # e.g. "track", "eofeos:repeat_cycle_id"
    attribute: str  # attribute of the mission's ProductName, for offline (registry) filtering


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


def __getattr__(name: str):
    # parse_frames moved to the EarthCARE module (the only mission with frame
    # letters); still importable from here. Imported lazily: earthcare imports base.
    if name == "parse_frames":
        from maap_client.missions.earthcare import parse_frames

        return parse_frames
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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


# Verified rule: archive URLs (.../YYYY/MM/DD/<P>/<P>/...) and local paths
# downloaded with --product-dir (.../YYYY/MM/DD/<P>/...) hold the product
# folder right after the YYYY/MM/DD day folders.
_DAY_FOLDER = re.compile(r"/\d{4}/\d{2}/\d{2}/([^/]+)/")


def product_folder(path: str) -> Optional[str]:
    """Folder right after the YYYY/MM/DD day folders of a URL or local path, or None."""
    match = _DAY_FOLDER.search(path)
    return match.group(1) if match else None


def match_group(pattern: re.Pattern, text: str) -> Optional[str]:
    """First group of the first match of pattern in text, or None."""
    match = pattern.search(text)
    return match.group(1) if match else None


def declared_baseline(
    baseline: Optional[str], product_type: Optional[str], no_baseline: frozenset[str]
) -> Optional[str]:
    """The baseline read; if none, NO_BASELINE for a type declared without one, else None."""
    if baseline is None and product_type in no_baseline:
        return NO_BASELINE
    return baseline


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
    # orbits may end with a frame letter ('01525E'), merged into the "frame" filter
    orbit_frame_letter: bool = False
    # names that carry an absolute orbit, for offline (registry) orbit filtering:
    # "all" (names without one are dropped), "some" (such names are rejected),
    # "none" (--orbit only works with search)
    orbit_offline: Literal["all", "some", "none"] = "none"
    no_orbit_products: frozenset[str] = frozenset()
    no_baseline_products: frozenset[str] = frozenset()
    # individual files need --product-dir (their names repeat across and within
    # products), except the product types declared to hold a single file
    files_need_product_dir: bool = False
    single_file_products: frozenset[str] = frozenset()

    def available_filters(self) -> tuple[str, ...]:
        """Filter options of the mission: orbit, then its declared filters."""
        return ("orbit",) + tuple(spec.option for spec in self.filters)

    def parse(self, url: str) -> ProductName:
        """Parse a product filename or URL."""
        raise NotImplementedError

    def product_name(self, url: str) -> str:
        """
        Name to parse the product fields from: the first of the basename, the
        product directory of an archive URL and the product folder of a local
        path that is a product name of this mission (some enclosures are
        named differently, e.g. ``L1A_<start>__<stop>.nc``); else the product
        directory of the URL.
        """
        product = split_product_url(url)[0]
        for candidate in (os.path.basename(url), product, product_folder(url)):
            if candidate and candidate.upper().startswith(self.prefix.upper()):
                return candidate
        return product

    def data_url(self, filename: str) -> Optional[str]:
        """Rebuild the download URL from a filename, or None when not derivable."""
        return None

    def dedup_pattern(self, filename: str) -> Optional[str]:
        """Glob of the other versions of the same granule, or None when versions are not deduplicated."""
        return None
