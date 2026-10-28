"""CryoSat: product-name parsing and mission profile.

SIRAL L1b and L2, Ice and Ocean (C2-RS-ACS-ESL-5364 issue 2.0 section 4.1,
C2-RS-ACS-ESL-5265 issue 2.1 section 2.3, C2-RS-ACS-ESL-5266 issue 3.7
section 2.2, CryoSat-2 Product Handbook C2-LI-ACS-ESL-5319 Baseline E
section 4.4)::

    CS_<CCCC>_<TTTTTTTTTT>_<start>_<stop>_<B><vvv>

file class (OFFL, LTA_, NRT_, ...), file type, UTC validity start and stop,
processing baseline letter and file version. Baseline F has no published
format specification; its names follow the same grammar (verified against the
catalogue). CryoTEMPO thematic products (LU_ESA_Cryo-TEMPO_PH v5.1 section
4.1.1)::

    CS_OFFL_SIR_TDP_<TH>_<AREA6>_<start>_<stop>_<CC>_<OOOOO>_<B><vvv>

where the SD climatologies write ``CLIM<mmdd>T<hhmmss>`` as times and gridded
products ``GRID____`` for cycle and relative orbit. Those two fields are not
read: their live values contradict the handbook (relative orbits above the
5344 orbits of a cycle, absolute orbits for IW). CryoTEMPO-EOLIS
(CS_CTS_PHB_EWAVE_0401 issue 4.1 section 3.1)::

    CS_OFFL_THEM_POINT_<ZONE9>_<YYYY>_<MM>_<X>_<Y>_<VNNN>
    CS_OFFL_THEM_GRID__<ZONE9>_<YYYY>_<MM>_<VNNN>

zone, year, month, tile corner (POINT) and version; no acquisition time.

The trailing ``<B><vvv>`` / ``<VNNN>`` is the baseline: it equals the item's
``version`` and the archive folder for every fixture item.

Meaning of sensing_time:

    name start on the URL's day folder ... the name's first timestamp (validity
                                            start; equals the item's
                                            start_datetime within 1 s, up to
                                            16 min earlier for GDR and
                                            CryoTEMPO PO/SI, same day)
    otherwise, with a day folder ......... that day at midnight UTC, with
                                            sensing_day_only (EOLIS, SD
                                            climatologies, and IW names
                                            dated up to 12 days before the
                                            item's start_datetime)
    bare filename ........................ the name's first timestamp, or
                                            None (EOLIS, SD)

The archive day folder is the day of the item's start_datetime for every
fixture item. No creation time or absolute orbit is in the names.
"""

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from maap_client.missions.base import (
    ORBIT_DIRECTION,
    Mission,
    ProductName,
    day_folder,
    match_group,
    parse_timestamp,
    split_product_url,
)

COLLECTIONS = (
    "CryoSatIceL110",
    "CryoSatIceL210",
    "CryoSatOceanL110",
    "CryoSatOceanL210",
    "CryoTEMPO10",
    "CryoTEMPOEOLIS10",
)

DATA_URL = "https://catalog.maap.eo.esa.int/data/cryosat-pdgs-01/CRYOSAT"

# Verified rule: the 10 characters after CS_<CCCC>_ equal `product:type` on
# every fixture item, except EOLIS POINT, whose type is the 11 characters
# THEM_POINT_ (THEM_GRID_ is followed by a `_` separator like the others).
_PRODUCT_TYPE = re.compile(r"^CS_.{4}_(THEM_POINT_|.{10}(?=_))", re.IGNORECASE)
_FILE_CLASS = re.compile(r"^CS_(.{4})_", re.IGNORECASE)
_BASELINE = re.compile(r"_([A-Z]\d{3})(?:\.[A-Z]+)?$", re.IGNORECASE)
# Absent from SD climatology (CLIM...) and EOLIS names
_SENSING = re.compile(r"_(\d{8}T\d{6})_")
_REGION = re.compile(
    r"^CS_.{4}_(?:SIR_TDP_.{2}_([A-Z]{6})|THEM_(?:POINT_|GRID__)([A-Z_]{9}))_", re.IGNORECASE
)
# Names whose day is not always the archive day folder (IW) or that have no
# acquisition time (SD climatologies, EOLIS): their URL is not derivable
_NO_DATA_URL_PRODUCTS = frozenset({"SIR_TDP_IW", "SIR_TDP_SD", "THEM_GRID_", "THEM_POINT_"})


@dataclass(frozen=True)
class CryoSatName(ProductName):
    """CryoSat product name: ProductName plus file class and region."""

    file_class: Optional[str] = None  # OFFL, LTA_, ...
    region: Optional[str] = None  # CryoTEMPO area or EOLIS zone, e.g. ANTARC, ANTICESHF


def _name(name_or_url: str) -> str:
    return CRYOSAT.product_name(name_or_url)


def _named_sensing_time(name_or_url: str) -> Optional[datetime]:
    """First timestamp of the name as UTC."""
    sensing = match_group(_SENSING, _name(name_or_url))
    return parse_timestamp(sensing, "%Y%m%dT%H%M%S") if sensing else None


def _sensing(name_or_url: str) -> tuple[Optional[datetime], bool]:
    """(sensing_time, sensing_day_only): the name's time, else the day folder's day."""
    named = _named_sensing_time(name_or_url)
    day = day_folder(name_or_url)
    if day is not None and (named is None or named.date() != day):
        return datetime(day.year, day.month, day.day, tzinfo=timezone.utc), True
    return named, False


def extract_product_type(name_or_url: str) -> Optional[str]:
    """File type, e.g. ``SIR_SAR_1B``, ``THEM_POINT_``."""
    product_type = match_group(_PRODUCT_TYPE, _name(name_or_url))
    return product_type.upper() if product_type else None


def extract_baseline(name_or_url: str) -> Optional[str]:
    """Baseline letter and file version, e.g. ``E001``, ``V201``."""
    baseline = match_group(_BASELINE, _name(name_or_url))
    return baseline.upper() if baseline else None


def extract_sensing_time(name_or_url: str) -> Optional[datetime]:
    """Sensing time as UTC: the name's start, else the day of the archive day folder."""
    return _sensing(name_or_url)[0]


def extract_creation_time(name_or_url: str) -> None:
    """Always None: CryoSat names carry no creation time."""


def extract_orbit(name_or_url: str) -> None:
    """Always None: CryoSat names carry no absolute orbit."""


def extract_file_class(name_or_url: str) -> Optional[str]:
    """File class, e.g. ``OFFL``, ``LTA_``."""
    file_class = match_group(_FILE_CLASS, _name(name_or_url))
    return file_class.upper() if file_class else None


def extract_region(name_or_url: str) -> Optional[str]:
    """CryoTEMPO area or EOLIS zone without padding, e.g. ``ANTARC``, ``ALASKA``."""
    match = _REGION.search(_name(name_or_url))
    if not match:
        return None
    return (match.group(1) or match.group(2)).rstrip("_").upper()


class _CryoSat(Mission):
    name = "CryoSat"
    code = "CS"
    prefixes = ("CS_",)
    collections = COLLECTIONS
    # temporal extent of the catalogue collections
    start = "2010-07-16T00:00:00Z"
    end = "2045-12-31T23:59:59Z"
    default_formats = ("nc",)
    filters = (ORBIT_DIRECTION,)
    orbit_offline = "none"

    def parse(self, url: str) -> CryoSatName:
        sensing_time, sensing_day_only = _sensing(url)
        return CryoSatName(
            mission=self.code,
            product=split_product_url(url)[0],
            filename=os.path.basename(url),
            product_type=extract_product_type(url),
            baseline=extract_baseline(url),
            sensing_time=sensing_time,
            creation_time=extract_creation_time(url),
            orbit=extract_orbit(url),
            sensing_day_only=sensing_day_only,
            file_class=extract_file_class(url),
            region=extract_region(url),
        )

    def data_url(self, filename: str) -> Optional[str]:
        """
        Rebuild the download URL from a filename, laid out as
        ``.../{type}/{baseline}/{yyyy}/{mm}/{dd}/{stem}/{stem}/{filename}``
        by the day of the name's start; None for the types whose name does
        not give that day.
        """
        info = self.parse(os.path.basename(filename))
        dt = info.sensing_time
        if not (info.product_type and info.baseline and dt):
            return None
        if info.product_type in _NO_DATA_URL_PRODUCTS:
            return None
        stem = os.path.splitext(info.filename)[0]
        return (
            f"{DATA_URL}/{info.product_type}/{info.baseline}"
            f"/{dt.year:04d}/{dt.month:02d}/{dt.day:02d}/{stem}/{stem}/{info.filename}"
        )


CRYOSAT = _CryoSat()
