"""Path generation utilities for MAAP data organization.

This module depends only on the stdlib and the stdlib-only
maap_client.missions package, so it can be used independently in other
contexts.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from maap_client.missions import mission_for_filename, split_product_url
from maap_client.missions.base import ProductName


logger = logging.getLogger(__name__)


def generate_data_path(
    data_dir: Path,
    mission: str,
    collection: str,
    product_type: str,
    baseline: str,
    dt: datetime,
    filename: str,
    product_dir: bool = False,
) -> Path:
    """
    Generate structured path for downloaded data files.

    Structure: data_dir/mission/collection/product_type/baseline/yyyy/mm/dd/filename
    With product_dir: .../yyyy/mm/dd/{stem}/filename (legacy; downloads pass
    a ``local_relpath`` as filename instead)

    Args:
        data_dir: Base data directory
        mission: Mission name (e.g., "EarthCARE")
        collection: Collection name
        product_type: Product type name
        baseline: Baseline version
        dt: Datetime for the file
        filename: Filename, or a relative path below the day folder (e.g.
                  ``local_relpath(url, product_dir)``)
        product_dir: Kept for compatibility: if True, wrap ``filename`` in a
                     subdirectory named after its stem. Leave False when
                     ``filename`` is already a ``local_relpath``.

    Returns:
        Full path for the file
    """
    base = data_dir / mission / collection / product_type / baseline / f"{dt.year:04d}" / f"{dt.month:02d}" / f"{dt.day:02d}"
    if product_dir:
        stem = Path(filename).stem
        return base / stem / filename
    return base / filename


def generate_registry_path(
    registry_dir: Path,
    prefix: str,
    mission: str,
    collection: str,
    product_type: str,
    baseline: str,
) -> Path:
    """
    Generate path for registry tracking directory.

    Structure: registry_dir/prefix/mission/collection/product_type/baseline/

    Args:
        registry_dir: Base registry directory
        prefix: Registry prefix (e.g., "downloads", "urls")
        mission: Mission name (e.g., "EarthCARE")
        collection: Collection name
        product_type: Product type name
        baseline: Baseline version

    Returns:
        Path for registry files directory
    """
    return registry_dir / prefix / mission / collection / product_type / baseline


def _parse(uri: str) -> Optional[ProductName]:
    """Parse a product filename or URL with its mission, or None for an unknown prefix."""
    mission = mission_for_filename(uri)
    return mission.parse(uri) if mission else None


def extract_sensing_time(filename: str) -> Optional[datetime]:
    """
    Extract sensing time (first timestamp) from product filename.

    Supported formats:
    - Aeolus with ms: _YYYYMMDDTHHMMSSMMM_ (e.g., _20230422T165721033_)
    - EarthCARE: _YYYYMMDDTHHMMSSZ_ (e.g., _20250908T232505Z_)
    - Aeolus without ms: _YYYYMMDDTHHMMSS_ (e.g., _20190430T015241_)

    Args:
        filename: Product filename (or full path - directory is stripped)

    Returns:
        Sensing datetime or None if not found
    """
    parsed = _parse(filename)
    return parsed.sensing_time if parsed else None


def sort_by_sensing_time(items: list[str], reverse: bool = False) -> list[str]:
    """
    Sort URLs/paths by their sensing time. Items with no extractable
    sensing time are appended at the end regardless of order.
    """
    with_dt: list[tuple[datetime, str]] = []
    without_dt: list[str] = []
    for item in items:
        dt = extract_sensing_time(item)
        if dt is None:
            without_dt.append(item)
        else:
            with_dt.append((dt, item))
    with_dt.sort(key=lambda x: x[0], reverse=reverse)
    return [item for _, item in with_dt] + without_dt


def extract_creation_time(filename: str) -> Optional[datetime]:
    """
    Extract creation time (second timestamp) from EarthCARE filename.

    Example: ECA_EXBA_BM__RAD_2B_20250908T232505Z_20250909T010458Z_07282E.h5
                                                  ^^^^^^^^^^^^^^^^ creation time

    Aeolus products do not have a creation time encoded in their filename.

    Args:
        filename: Product filename (or full path - directory is stripped)

    Returns:
        Creation datetime or None if not found
    """
    parsed = _parse(filename)
    return parsed.creation_time if parsed else None


def extract_orbit_frame(filename: str) -> Optional[str]:
    """
    Extract orbit+frame as a string from product filename.

    EarthCARE: ECA_EXBA_BM__RAD_2B_20250908T232505Z_20250909T010458Z_07282E.h5
               Returns: "07282E" (5 digits + frame letter)

    Aeolus: AE_OPER_ALD_U_N_1B_20230422T165721033_005543989_027018_0001.DBL
            Returns: "027018" (6 digits, no frame letter)

    Args:
        filename: Product filename (or full path - directory is stripped)

    Returns:
        Orbit+frame string (e.g., "07282E" or "027018") or None if not found
    """
    parsed = _parse(filename)
    return parsed.orbit_frame if parsed else None


def extract_agency(filename: str) -> Optional[str]:
    """
    Extract agency code from product filename.

    EarthCARE:
        ECA_EXBC_BM__RAD_2B_20250908T232505Z_20250909T010458Z_07282E.h5
             ^^
           agency = EX (ESA products), JX (JAXA products)

    Aeolus:
        AE_OPER_ALD_U_N_1B_20230422T165721033_005543989_027018_0001.DBL
           Returns: "EX" (Aeolus is an ESA mission)

    Args:
        filename: Product filename (or full path - directory is stripped)

    Returns:
        Agency string (e.g., "EX", "JX") or None if not found
    """
    parsed = _parse(filename)
    return parsed.agency if parsed else None


def extract_file_class(filename: str) -> Optional[str]:
    """
    Extract file class from Aeolus filename.

    Aeolus only:
        AE_OPER_ALD_U_N_1B_20230422T165721033_005543989_027018_0001.DBL
           ^^^^
           file_class = OPER

    File classes:
        - OPER: routine operations
        - OSVA: operational data acquired at Svalbard
        - OTRO: operational data acquired at Antarctiva Troll station (used for Aeolus)
        - RPRO: reprocessing
        - OFFL: backlog
        - TEST: internal tests

    Args:
        filename: Product filename (or full path - directory is stripped)

    Returns:
        File class string (e.g., "OPER", "RPRO") or None if not Aeolus
    """
    parsed = _parse(filename)
    return parsed.fields.get("file_class") if parsed else None


def extract_duration_ms(filename: str) -> Optional[int]:
    """
    Extract sensing duration in milliseconds from Aeolus filename.

    Aeolus only:
        AE_OPER_ALD_U_N_1B_20230422T165721033_005543989_027018_0001.DBL
                                              ^^^^^^^^^
                                              duration = 5543989 ms

    Args:
        filename: Product filename (or full path - directory is stripped)

    Returns:
        Duration in milliseconds or None if not Aeolus
    """
    parsed = _parse(filename)
    duration = parsed.fields.get("duration_ms") if parsed else None
    return int(duration) if duration is not None else None


def extract_file_version(filename: str) -> Optional[str]:
    """
    Extract file version from Aeolus filename.

    Aeolus only:
        AE_OPER_ALD_U_N_1B_20230422T165721033_005543989_027018_0001.DBL
                                                               ^^^^
                                                               version = 0001

    Args:
        filename: Product filename (or full path - directory is stripped)

    Returns:
        File version string (e.g., "0001") or None if not Aeolus
    """
    parsed = _parse(filename)
    return parsed.fields.get("file_version") if parsed else None


def extract_baseline(uri: str) -> Optional[str]:
    """
    Extract baseline version from product filename or URL path.

    EarthCARE (from filename):
        ECA_EXBC_BM__RAD_2B_20250908T232505Z_20250909T010458Z_07282E.h5
              ^^
            baseline = BC (ECA_EX + baseline)

    Aeolus (from URL path - baseline not in filename):
        .../ALD_U_N_1B/1B16/2023/04/22/...
                       ^^^^
            baseline = 1B16

    Args:
        uri: Product URL or filename

    Returns:
        Baseline string (e.g., "BC", "1B16") or None if not found
    """
    parsed = _parse(uri)
    return parsed.baseline if parsed else None


def extract_product(filename: str) -> Optional[str]:
    """
    Extract product type from product filename.

    EarthCARE:
        ECA_EXBC_BM__RAD_2B_20250908T232505Z_20250909T010458Z_07282E.h5
                 ^^^^^^^^^^
               product = BM__RAD_2B

    Aeolus:
        AE_OPER_ALD_U_N_1B_20230422T165721033_005543989_027018_0001.DBL
                ^^^^^^^^^^
               product = ALD_U_N_1B

    Args:
        filename: Product filename (or full path - directory is stripped)

    Returns:
        Product type string (e.g., "CPR_NOM_1B", "ALD_U_N_1B") or None if not found
    """
    parsed = _parse(filename)
    return parsed.product_type if parsed else None


def extract_mission(filename: str) -> Optional[str]:
    """
    Extract mission identifier from filename.

    EarthCARE: ECA_EXBC_BM__RAD_2B_... → "ECA"
    Aeolus: AE_OPER_ALD_U_N_1B_... → "AE"

    Args:
        filename: Product filename (or full path - directory is stripped)

    Returns:
        Mission identifier ("ECA" or "AE") or None if not recognized
    """
    mission = mission_for_filename(filename)
    return mission.code if mission else None


def extract_info(uri: str) -> dict[str, Any]:
    """
    Extract all metadata from a product filename.

    Wraps the mission parser to provide complete metadata in a single call.

    Example:
        ECA_EXBC_BM__RAD_2B_20250908T232505Z_20250909T010458Z_07282E.h5
        Returns: {
            "filename": "ECA_EXBC_BM__RAD_2B_20250908T232505Z_20250909T010458Z_07282E.h5",
            "mission": "ECA",
            "agency": "EX",
            "baseline": "BC",
            "product_type": "BM__RAD_2B",
            "sensing_time": datetime(2025, 9, 8, 23, 25, 5, tzinfo=timezone.utc),
            "creation_time": datetime(2025, 9, 9, 1, 4, 58, tzinfo=timezone.utc),
            "orbit_frame": "07282E"
        }

    Args:
        uri: Product URL or filename (directory is stripped)

    Returns:
        Dict with extracted metadata (values may be None if parsing fails)
    """
    parsed = _parse(uri)
    return {
        "filename": os.path.basename(uri),
        "mission": parsed.mission if parsed else None,
        "agency": parsed.agency if parsed else None,
        "baseline": parsed.baseline if parsed else None,
        "product_type": parsed.product_type if parsed else None,
        "sensing_time": parsed.sensing_time if parsed else None,
        "creation_time": parsed.creation_time if parsed else None,
        "orbit_frame": parsed.orbit_frame if parsed else None,
    }

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
        sensing_time = extract_sensing_time(item)
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
        orbit_frame = extract_orbit_frame(item)
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


def is_zip_url(url: str) -> bool:
    """True for a whole-product archive URL (the `product` asset, served by /data/zipper/)."""
    return "/data/zipper/" in urlparse(url).path


def local_relpath(url: str, product_dir: bool) -> Path:
    """
    Path of a downloaded file relative to its day folder.

    - individual file: ``<filename>``, or with product_dir
      ``<PRODUCT>/<internal relative path>``
    - zip: ``<PRODUCT>.zip``, or with product_dir ``<PRODUCT>/<PRODUCT>.zip``

    Archive URLs are ``.../<PRODUCT>/<root>/<internal relative path>`` where
    ``<root>`` is the product's own top directory (the product name again, or
    for some Biomass aux products a name with another creation date). The
    product comes from the mission parser; without a recognisable layout (e.g.
    a bare filename) the internal relative path is the filename.

    Args:
        url: Product file URL (or bare filename)
        product_dir: If True, place the file inside a folder named after the product

    Returns:
        Relative local path (never absolute, never containing ``..``)

    Raises:
        ValueError: If the URL yields an empty, ``.`` or ``..`` path segment
    """
    path = urlparse(url).path
    parsed = _parse(url)
    product = parsed.product if parsed else split_product_url(path)[0]

    filename = os.path.basename(path)
    if is_zip_url(url):
        name = f"{product}.zip"
        segments = [product, name] if product_dir else [name]
    elif not product_dir:
        segments = [filename]
    else:
        parts = path.split("/")
        inner = [filename]
        if product in parts:
            i = parts.index(product)
            # empty segments (doubled slashes) are dropped, so the path can
            # never turn absolute
            inner = [part for part in parts[i + 2:] if part] or inner
        segments = [product, *inner]

    # ".." or "." would escape (or collapse) the folder the file belongs in
    if any(part in ("", ".", "..") for part in segments):
        raise ValueError(f"unsafe local path from URL: {url}")
    return Path(*segments)


def url_to_local_path(
    url: str,
    data_dir: Path,
    mission: str,
    collection: str,
    product_dir: bool = False,
) -> Optional[Path]:
    """
    Convert a product URL to the expected local file path:
    ``data_dir/mission/collection/product_type/baseline/yyyy/mm/dd/`` plus
    ``local_relpath(url, product_dir)``.

    Args:
        url: Product URL
        data_dir: Base data directory
        mission: Mission name
        collection: Collection name
        product_dir: If True, place the file inside a folder named after the product

    Returns:
        Local path or None if the product type, baseline or sensing time
        cannot be parsed, or the URL holds unsafe path segments
    """
    info = extract_info(url)

    if not (info["sensing_time"] and info["product_type"] and info["baseline"]):
        return None
    try:
        relpath = local_relpath(url, product_dir)
    except ValueError:
        return None

    return generate_data_path(
        data_dir=data_dir,
        mission=mission,
        collection=collection,
        product_type=info["product_type"],
        baseline=info["baseline"],
        dt=info["sensing_time"],
        filename=str(relpath),
    )


def extract_collection(path: str | Path) -> Optional[str]:
    """
    Read the collection back from a local data path.

    Inverse of ``generate_data_path``: the directory above
    ``{product_type}/{baseline}/{yyyy}/{mm}/{dd}`` (optionally followed by the
    ``{stem}`` product directory), all checked against the filename.

    Args:
        path: Local path of a product file laid out by ``generate_data_path``

    Returns:
        Collection name, or None for unparsable names or paths outside the layout
    """
    path = Path(path)
    info = extract_info(str(path))
    product_type = info["product_type"]
    baseline = info["baseline"]
    dt = info["sensing_time"]
    if not (product_type and baseline and dt):
        return None

    parts = path.parent.parts
    if parts and parts[-1] == path.stem:
        parts = parts[:-1]
    tail = (product_type, baseline, f"{dt.year:04d}", f"{dt.month:02d}", f"{dt.day:02d}")
    if len(parts) <= len(tail) or parts[-len(tail):] != tail:
        return None
    collection = parts[-len(tail) - 1]
    return None if collection == path.anchor else collection



def filename_to_url(filename: str) -> Optional[str]:
    """
    Rebuild the MAAP download URL of a product from its filename.

    The archive lays products out as
    ``.../{product_type}/{baseline}/{yyyy}/{mm}/{dd}/{stem}/{stem}/{filename}``
    (the stem repeats), dated by sensing time, so every field comes from the
    filename and no catalogue query is needed. The URL is the enclosure asset
    and needs a MAAP token to download; it is not the public STAC item page.

    Counterpart of ``url_to_local_path``, which maps the same product onto the
    local convention instead (that one keys on collection, the URL does not).

    Args:
        filename: Product filename or path (directory is stripped)

    Returns:
        Download URL, or None for names of missions whose URL cannot be
        derived from the filename (e.g. Aeolus) or unparsable names
    """
    mission = mission_for_filename(filename)
    return mission.data_url(filename) if mission else None
