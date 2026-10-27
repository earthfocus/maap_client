"""Path generation utilities for MAAP data organization.

This module holds the on-disk layout and the filename/URL dispatchers over
the mission parsers. The filtering helpers live in maap_client.filters and
are re-exported here.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from maap_client.filters import (  # noqa: F401  (re-exported)
    filter_by_fields,
    filter_by_orbit_frame,
    filter_by_sensing_time,
    sort_by_sensing_time,
)
from maap_client.missions import mission_for_filename, parse_product, split_product_url
from maap_client.missions.base import product_folder


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
        product_dir: Legacy and unused by the package (downloads pass a
                     ``local_relpath`` as filename): if True, wrap ``filename``
                     in a subdirectory named after its stem.

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


def extract_sensing_time(filename: str) -> Optional[datetime]:
    """Sensing time (first timestamp of the name), or None."""
    parsed = parse_product(filename)
    return parsed.sensing_time if parsed else None


def extract_creation_time(filename: str) -> Optional[datetime]:
    """Creation time of the name, or None where the mission's names carry none."""
    parsed = parse_product(filename)
    return parsed.creation_time if parsed else None


def extract_orbit_frame(filename: str) -> Optional[str]:
    """Legacy orbit+frame string (e.g. "07282E", "027018"), or None."""
    parsed = parse_product(filename)
    return parsed.orbit_frame if parsed else None


def extract_agency(filename: str) -> Optional[str]:
    """Agency code (e.g. "EX", "JX"), or None where the mission's names carry none."""
    return getattr(parse_product(filename), "agency", None)


def extract_file_class(filename: str) -> Optional[str]:
    """Aeolus file class (e.g. "OPER", "RPRO"), or None."""
    return getattr(parse_product(filename), "file_class", None)


def extract_duration_ms(filename: str) -> Optional[int]:
    """Aeolus sensing duration in milliseconds, or None."""
    return getattr(parse_product(filename), "duration_ms", None)


def extract_file_version(filename: str) -> Optional[str]:
    """Aeolus file version as four digits (e.g. "0001"), or None."""
    version = getattr(parse_product(filename), "file_version", None)
    return f"{version:04d}" if version is not None else None


def extract_baseline(uri: str) -> Optional[str]:
    """Baseline from the name or URL path (e.g. "BC", "1B16", "NO_BASELINE"), or None."""
    parsed = parse_product(uri)
    return parsed.baseline if parsed else None


def extract_product(filename: str) -> Optional[str]:
    """Product type (e.g. "CPR_NOM_1B", "ALD_U_N_1B"), or None."""
    parsed = parse_product(filename)
    return parsed.product_type if parsed else None


def extract_mission(filename: str) -> Optional[str]:
    """Mission code of the name (e.g. "ECA", "AE"), or None."""
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
    parsed = parse_product(uri)
    return {
        "filename": os.path.basename(uri),
        "mission": parsed.mission if parsed else None,
        "agency": getattr(parsed, "agency", None),
        "baseline": parsed.baseline if parsed else None,
        "product_type": parsed.product_type if parsed else None,
        "sensing_time": parsed.sensing_time if parsed else None,
        "creation_time": parsed.creation_time if parsed else None,
        "orbit_frame": parsed.orbit_frame if parsed else None,
    }


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
    parsed = parse_product(url)
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
    product directory and its sub-folders), all checked against the filename.

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

    tail = (product_type, baseline, f"{dt.year:04d}", f"{dt.month:02d}", f"{dt.day:02d}")
    parts = path.parent.parts
    if product_folder(path.as_posix()):
        # product directory (and any sub-folders) below the day folder
        day_end = next((i for i in range(len(tail), len(parts)) if parts[i - len(tail):i] == tail), None)
        if day_end is not None:
            parts = parts[:day_end]
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
