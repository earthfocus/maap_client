"""Aeolus: product-name parsing and mission profile.

Name: ``AE_<CCCC>_<file type>_<start>[_<duration ms>_<orbit>|_<stop>]_<version>.<ext>``
where CCCC is the file class (OPER, RPRO, ...); a few AUX products (e.g.
AUX_CHAR__) start with ``AE1_`` instead. The naming is not publicly
documented; every rule below is verified against the catalogue fixtures.

Meaning of sensing_time (first timestamp of the name; equals the item's
start_datetime to the second for every product type of every fixture item):

    names with duration ....... sensing start (with milliseconds), followed
                                by duration in ms and orbit (L0, L1A and
                                the matching AUX types)
    names with stop ........... sensing/validity start, followed by stop
                                (L1B/L2 and the matching AUX types)
    AUX validity files ........ validity start (the stop may be the
                                99991231T235959 end-of-validity marker)

No creation timestamp is documented, so creation_time is always None.
"""

import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from maap_client.missions.base import (
    Mission,
    ProductName,
    declared_baseline,
    match_group,
    parse_timestamp,
    split_product_url,
)

COLLECTIONS = (
    "AeolusBaseline16Products10",
    "AeolusEOLProducts10",
    "AeolusL2CProducts10",
    "AeolusL0ProductsB16",
    "AeolusAdditionalProducts",
)

# First timestamp: with milliseconds (9-digit time) or without (6-digit time)
_SENSING = re.compile(r"_(\d{8}T\d{6}(?:\d{3})?)_")
_FILE_CLASS = re.compile(r"^AE1?_([A-Z]{4})_")
# Verified rule: the 10 characters after AE_<CCCC>_ equal `product:type` on
# every fixture item (shorter types are padded with underscores).
_PRODUCT_TYPE = re.compile(r"^AE1?_[A-Z]{4}_([A-Z0-9_]{10})_\d{8}T\d{6}")
# Verified rule: the archive path holds .../<file type>/<baseline>/YYYY/MM/DD/;
# the baseline is the segment after the directory equal to the file type and
# equals the item's `version` where the catalogue has one. Items without
# version use the literal `NNAA` ("no baseline"), which is never a baseline.
_BASELINE_PATH = re.compile(r"/(?P<type>[A-Z0-9_]{10})/(?P<baseline>[A-Za-z0-9]{2,4})/\d{4}/\d{2}/\d{2}/", re.IGNORECASE)
# The extension is optional: zip (product) URLs end in the bare product name
_ORBIT = re.compile(r"_(\d{6})_\d{4}(?:\.[A-Z]{3})?$", re.IGNORECASE)
_NO_VERSION = "NNAA"
_DURATION = re.compile(r"_\d{8}T\d{9}_(\d{9})_\d{6}_\d{4}\.[A-Z]{3}$", re.IGNORECASE)
_VERSION = re.compile(r"_(\d{4})\.[A-Z]{3}$", re.IGNORECASE)


@dataclass(frozen=True)
class AeolusName(ProductName):
    """Aeolus product name: ProductName plus file class, duration and file version."""

    file_class: Optional[str] = None  # OPER, RPRO, ...
    duration_ms: Optional[int] = None
    file_version: Optional[int] = None

    @property
    def orbit_frame(self) -> Optional[str]:
        """Orbit as 6 digits, e.g. ``027018`` (Aeolus has no frames)."""
        return f"{self.orbit:06d}" if self.orbit is not None else None


def _name(name_or_url: str) -> str:
    return AEOLUS.product_name(name_or_url)


# Verified rule: every item of these AeolusAdditionalProducts types, and no
# item of any other type, has no catalogue `version` (path folder `NNAA`),
# checked against the whole catalogue on 2026-10-28.
NO_BASELINE_PRODUCTS = frozenset({
    "AUX_CHAR__", "AUX_CLM_L2", "AUX_LUT_BL", "AUX_MET_12", "AUX_PAR_0_",
    "AUX_PAR_1A", "AUX_PAR_1B", "AUX_PAR_2A", "AUX_PAR_2B", "AUX_PAR_CL",
    "AUX_PAR_CS", "AUX_PAR_HB", "AUX_PAR_QC", "AUX_PAR_RB", "AUX_TEL_12",
    "GRND_TRACK", "MPL_ORBPRE", "MPL_ORBRES", "MPL_ORBSCT", "TLMX__VC1_",
})


def extract_product_type(name_or_url: str) -> Optional[str]:
    """File type, e.g. ``ALD_U_N_1B``."""
    return match_group(_PRODUCT_TYPE, _name(name_or_url))


def extract_baseline(name_or_url: str) -> Optional[str]:
    """
    Baseline from the archive path, e.g. ``1B16``; NO_BASELINE for the types
    that have none; else None (e.g. a bare filename).
    """
    product_type = extract_product_type(name_or_url)
    if product_type is None:
        return None
    baseline = None
    for match in _BASELINE_PATH.finditer(name_or_url):
        if match.group("type").upper() == product_type:
            if match.group("baseline").upper() != _NO_VERSION:
                baseline = match.group("baseline")
            break
    return declared_baseline(baseline, product_type, NO_BASELINE_PRODUCTS)


def extract_sensing_time(name_or_url: str) -> Optional[datetime]:
    """First timestamp of the name as UTC, with milliseconds where the name has them."""
    sensing = match_group(_SENSING, _name(name_or_url))
    if not sensing:
        return None
    return parse_timestamp(sensing, "%Y%m%dT%H%M%S%f" if len(sensing) > 15 else "%Y%m%dT%H%M%S")


def extract_creation_time(name_or_url: str) -> None:
    """Always None: Aeolus names carry no documented creation time."""


def extract_orbit(name_or_url: str) -> Optional[int]:
    """Absolute orbit number, for names with duration and orbit."""
    orbit = match_group(_ORBIT, _name(name_or_url))
    return int(orbit) if orbit else None


def extract_file_class(name_or_url: str) -> Optional[str]:
    """File class, e.g. ``OPER``."""
    return match_group(_FILE_CLASS, _name(name_or_url))


def extract_duration_ms(name_or_url: str) -> Optional[int]:
    """Sensing duration in milliseconds."""
    duration = match_group(_DURATION, _name(name_or_url))
    return int(duration) if duration else None


def extract_file_version(name_or_url: str) -> Optional[int]:
    """File version, e.g. 1 for ``_0001``."""
    version = match_group(_VERSION, _name(name_or_url))
    return int(version) if version else None


class _Aeolus(Mission):
    # no data_url: the baseline is only in the archive path, not in the filename
    name = "Aeolus"
    code = "AE"
    prefixes = ("AE_", "AE1_")
    collections = COLLECTIONS
    start = "2018-08-22T00:00:00Z"
    end = "2023-07-28T23:59:59Z"
    default_formats = ("dbl", "nc", "bufr", "eef")
    orbit_offline = "some"
    no_baseline_products = NO_BASELINE_PRODUCTS

    def parse(self, url: str) -> AeolusName:
        return AeolusName(
            mission=self.code,
            product=split_product_url(url)[0],
            filename=os.path.basename(url),
            product_type=extract_product_type(url),
            baseline=extract_baseline(url),
            sensing_time=extract_sensing_time(url),
            creation_time=extract_creation_time(url),
            orbit=extract_orbit(url),
            file_class=extract_file_class(url),
            duration_ms=extract_duration_ms(url),
            file_version=extract_file_version(url),
        )


AEOLUS = _Aeolus()
