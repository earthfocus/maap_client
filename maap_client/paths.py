"""Path generation utilities for MAAP data organization.

This module is standalone with no maap_client imports, so it can be
used independently in other contexts.
"""

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


logger = logging.getLogger(__name__)


def generate_data_path(
    data_dir: Path,
    mission: str,
    collection: str,
    product_type: str,
    baseline: str,
    dt: datetime,
    filename: str,
) -> Path:
    """
    Generate structured path for downloaded data files.

    Structure: data_dir/mission/collection/product_type/baseline/yyyy/mm/dd/filename

    Args:
        data_dir: Base data directory
        mission: Mission name (e.g., "EarthCARE")
        collection: Collection name
        product_type: Product type name
        baseline: Baseline version
        dt: Datetime for the file
        filename: Filename

    Returns:
        Full path for the file
    """
    base = data_dir / mission / collection / product_type / baseline / f"{dt.year:04d}" / f"{dt.month:02d}" / f"{dt.day:02d}"
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
    filename = os.path.basename(filename)

    # Aeolus: _YYYYMMDDTHHMMSSMMM_ (9-digit time with milliseconds)
    # Must check first as it's more specific than the 6-digit pattern
    # e.g., AE_OPER_ALD_U_N_1B_20230422T165721033_005543989_027018_0001.DBL
    match = re.search(r"_(\d{8}T\d{9})_", filename)
    if match:
        dt_str = match.group(1)
        try:
            dt = datetime.strptime(dt_str, "%Y%m%dT%H%M%S%f")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # EarthCARE/Aeolus: _YYYYMMDDTHHMMSS[Z]_ (6-digit time, optional Z suffix)
    # e.g., ECA_EXBC_BM__RAD_2B_20250908T232505Z_...
    # e.g., AE_OPER_ALD_U_N_2B_20190430T015241_20190430T041441_0003.DBL
    match = re.search(r"_(\d{8}T\d{6})Z?_", filename)
    if match:
        dt_str = match.group(1)
        try:
            dt = datetime.strptime(dt_str, "%Y%m%dT%H%M%S")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def extract_creation_time(filename: str) -> Optional[datetime]:
    """
    Extract creation time (second timestamp) from EarthCARE filename.

    Example: ECA_EXBA_BM__RAD_2B_20250908T232505Z_20250909T010458Z_07282E.h5
                                                  ^^^^^^^^^^^^^^^^ creation time

    Args:
        filename: Product filename (or full path - directory is stripped)

    Returns:
        Creation datetime or None if not found
    """
    filename = os.path.basename(filename)
    # Pattern: _YYYYMMDDTHHMMSSZ_YYYYMMDDTHHMMSSZ_
    pattern = r"_\d{8}T\d{6}Z_(\d{8}T\d{6}Z)_"
    match = re.search(pattern, filename)

    if match:
        dt_str = match.group(1)
        try:
            dt = datetime.strptime(dt_str, "%Y%m%dT%H%M%SZ")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    return None


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
    filename = os.path.basename(filename)

    # EarthCARE: 5 digits + 1 letter at the end before extension
    match = re.search(r"_(\d{5})([A-Z])\.[a-zA-Z0-9]+$", filename, re.IGNORECASE)
    if match:
        orbit_str, frame = match.groups()
        return f"{orbit_str}{frame.upper()}"

    # Aeolus: 6 digits orbit number (third field from end: _ORBIT_VERSION.EXT)
    # AE_OPER_ALD_U_N_1B_20230422T165721033_005543989_027018_0001.DBL
    match = re.search(r"_(\d{6})_\d{4}\.[A-Z]{3}$", filename, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


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
    filename = os.path.basename(filename)

    # EarthCARE: ECA_ + 2 uppercase letters (agency)
    match = re.match(r"^ECA_([A-Z]{2})[A-Z]{2}_", filename)
    if match:
        return match.group(1)

    # Aeolus: ESA mission, always "EX"
    if filename.startswith("AE_"):
        return "EX"

    return None


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
        - RPRO: reprocessing
        - OFFL: backlog
        - TEST: internal tests

    Args:
        filename: Product filename (or full path - directory is stripped)

    Returns:
        File class string (e.g., "OPER", "RPRO") or None if not Aeolus
    """
    filename = os.path.basename(filename)

    # Aeolus: AE_ + 4 uppercase letters (file class)
    match = re.match(r"^AE_([A-Z]{4})_", filename)
    if match:
        return match.group(1)

    return None


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
    filename = os.path.basename(filename)

    # Aeolus: timestamp_duration_orbit_version.ext
    match = re.search(r"_\d{8}T\d{9}_(\d{9})_\d{6}_\d{4}\.[A-Z]{3}$", filename, re.IGNORECASE)
    if match:
        return int(match.group(1))

    return None


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
    filename = os.path.basename(filename)

    # Aeolus: _VERSION.EXT at the end
    match = re.search(r"_(\d{4})\.[A-Z]{3}$", filename, re.IGNORECASE)
    if match and filename.startswith("AE_"):
        return match.group(1)

    return None


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
    filename = os.path.basename(uri)

    # EarthCARE: baseline in filename (ECA_XX + baseline)
    match = re.match(r"^ECA_[A-Z]{2}([A-Z]{2})_", filename)
    if match:
        return match.group(1)

    # Aeolus: baseline in URL path after product type
    # URL pattern: .../PRODUCT_TYPE/BASELINE/YYYY/MM/DD/...
    # e.g., .../ALD_U_N_1B/1B16/2023/04/22/... or .../ALD_U_N_2B/2b16/2023/04/22/...
    if filename.startswith("AE_"):
        # Look for baseline in path: /PRODUCT_TYPE/BASELINE/YYYY/
        # Case-insensitive to handle both uppercase (1B16) and lowercase (2b16) baselines
        match = re.search(r"/ALD_[UC]_N_\d[AB]/([A-Za-z0-9]{4})/\d{4}/", uri, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


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
    filename = os.path.basename(filename)

    # EarthCARE: ECA_XXXX_ followed by product, then _YYYYMMDDTHHMMSSZ
    match = re.match(r"^ECA_[A-Z]{4}_(.+?)_\d{8}T\d{6}Z_", filename)
    if match:
        return match.group(1)

    # Aeolus: AE_CCCC_ followed by product type (ALD_X_N_XX), then _timestamp
    # AE_OPER_ALD_U_N_1B_20230422T165721033_...
    match = re.match(r"^AE_[A-Z]{4}_(ALD_[UC]_N_\d[AB])_\d{8}T\d{9}_", filename)
    if match:
        return match.group(1)

    return None


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
    filename = os.path.basename(filename)

    if filename.startswith("ECA_"):
        return "ECA"
    if filename.startswith("AE_"):
        return "AE"

    return None


def extract_info(uri: str) -> dict[str, Any]:
    """
    Extract all metadata from a product filename.

    Wraps all extraction functions to provide complete metadata in a single call.

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
    filename = os.path.basename(uri)

    return {
        "filename": filename,
        "mission": extract_mission(filename),
        "agency": extract_agency(filename),
        "baseline": extract_baseline(filename),
        "product_type": extract_product(filename),
        "sensing_time": extract_sensing_time(filename),
        "creation_time": extract_creation_time(filename),
        "orbit_frame": extract_orbit_frame(filename),
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


def url_to_local_path(
    url: str,
    data_dir: Path,
    mission: str,
    collection: str,
) -> Optional[Path]:
    """
    Convert a product URL to the expected local file path.

    Args:
        url: Product URL
        data_dir: Base data directory
        mission: Mission name
        collection: Collection name

    Returns:
        Local path or None if URL cannot be parsed
    """
    info = extract_info(url)

    if not info["sensing_time"]:
        return None

    return generate_data_path(
        data_dir=data_dir,
        mission=mission,
        collection=collection,
        product_type=info["product_type"],
        baseline=info["baseline"],
        dt=info["sensing_time"],
        filename=info["filename"],
    )
