"""EarthCARE: product-name parsing and mission profile.

Name: ``ECA_<AB><CD>_<product type>_<start>Z_<second>Z_<orbit><frame>.<ext>``
where AB is the agency (EX = ESA, JX = JAXA) and CD the baseline.

Meaning of sensing_time (first timestamp, verified against ``start_datetime``
of the catalogue items for every product type):

    L1b, L2 ................ start of the frame (EarthCARE Data Handbook,
                             "Product Definition and Format")
    X-MET, AUX, orbit, L0 ... not publicly documented; validity start, equal
                             to the item's start_datetime

The second timestamp is the processing date/time for L1b and L2 (Handbook).
For the other types it is kept as creation_time as well, since existing code
and tests rely on it (legacy). Special values 00000000T000000 and
99999999T999999 (EO GS File Format Standard PE-TN-ESA-GS-0001) yield None.
"""

import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from maap_client.missions.base import (
    Mission,
    ProductName,
    match_group,
    parse_timestamp,
    split_product_url,
)

# Root of the MAAP archive serving EarthCARE products over HTTPS. The layout
# below it is keyed entirely by the filename (see EarthCARE.data_url).
DATA_URL = "https://catalog.maap.eo.esa.int/data/earthcare-pdgs-01/EarthCARE"

COLLECTIONS = (
    "EarthCAREL0L1Products_MAAP",
    "EarthCAREL1InstChecked_MAAP",
    "EarthCAREL1Validated_MAAP",
    "EarthCAREL2InstChecked_MAAP",
    "EarthCAREL2Products_MAAP",
    "EarthCAREL2Validated_MAAP",
    "EarthCAREAuxiliary_MAAP",
    "EarthCAREOrbitData_MAAP",
    "EarthCAREXMETL1DProducts10_MAAP",
    "JAXAL2InstChecked_MAAP",
    "JAXAL2Products_MAAP",
    "JAXAL2Validated_MAAP",
)

# Products that are deduplicated by (sensing_time, orbit_frame) at download time.
# AUX_MET_1D has multiple versions per granule (different creation_time) in the STAC API.
DEDUP_PRODUCTS = frozenset({"AUX_MET_1D"})

# Products that don't have orbit/frame indexed in STAC metadata
NO_ORBIT_PRODUCTS = frozenset({"AUX_MET_1D"})

_SENSING = re.compile(r"_(\d{8}T\d{6})Z?_")
_CREATION = re.compile(r"_\d{8}T\d{6}Z_(\d{8}T\d{6}Z)_")
# The extension is optional: zip (product) URLs end in the bare product name
_ORBIT_FRAME = re.compile(r"_(\d{5})([A-Z])(?:\.[a-zA-Z0-9]+)?$", re.IGNORECASE)
_AGENCY = re.compile(r"^ECA_([A-Z]{2})[A-Z]{2}_")
_BASELINE = re.compile(r"^ECA_[A-Z]{2}([A-Z]{2})_")
_PRODUCT_TYPE = re.compile(r"^ECA_[A-Z]{4}_(.+?)_\d{8}T\d{6}Z_")


@dataclass(frozen=True)
class EarthCAREName(ProductName):
    """EarthCARE product name: ProductName plus agency and frame letter."""

    agency: Optional[str] = None  # EX = ESA, JX = JAXA
    frame: Optional[str] = None  # frame letter A-H

    @property
    def orbit_frame(self) -> Optional[str]:
        """Orbit (5 digits) and frame letter, e.g. ``07282E``."""
        if self.orbit is None or self.frame is None:
            return None
        return f"{self.orbit:05d}{self.frame}"


def _name(name_or_url: str) -> str:
    return EARTHCARE.product_name(name_or_url)


def extract_product_type(name_or_url: str) -> Optional[str]:
    """Product type, e.g. ``BM__RAD_2B``."""
    return match_group(_PRODUCT_TYPE, _name(name_or_url))


def extract_baseline(name_or_url: str) -> Optional[str]:
    """Baseline (the two letters after the agency), e.g. ``BC``."""
    return match_group(_BASELINE, _name(name_or_url))


def extract_agency(name_or_url: str) -> Optional[str]:
    """Agency code: EX (ESA) or JX (JAXA)."""
    return match_group(_AGENCY, _name(name_or_url))


def extract_sensing_time(name_or_url: str) -> Optional[datetime]:
    """First timestamp of the name as UTC."""
    sensing = match_group(_SENSING, _name(name_or_url))
    return parse_timestamp(sensing, "%Y%m%dT%H%M%S") if sensing else None


def extract_creation_time(name_or_url: str) -> Optional[datetime]:
    """Second timestamp of the name as UTC."""
    creation = match_group(_CREATION, _name(name_or_url))
    return parse_timestamp(creation, "%Y%m%dT%H%M%SZ") if creation else None


def extract_orbit(name_or_url: str) -> Optional[int]:
    """Absolute orbit number."""
    orbit = match_group(_ORBIT_FRAME, _name(name_or_url))
    return int(orbit) if orbit else None


def extract_frame(name_or_url: str) -> Optional[str]:
    """Frame letter (A-H), upper-case."""
    match = _ORBIT_FRAME.search(_name(name_or_url))
    return match.group(2).upper() if match else None


class _EarthCARE(Mission):
    name = "EarthCARE"
    code = "ECA"
    prefix = "ECA_"
    collections = COLLECTIONS
    start = "2024-05-28T00:00:00Z"
    end = "2045-12-31T23:59:59Z"
    default_formats = ("h5", "eof", "dbl")
    orbit_offline = True
    orbit_frame_suffix = True
    dedup_products = DEDUP_PRODUCTS
    no_orbit_products = NO_ORBIT_PRODUCTS

    def parse(self, url: str) -> EarthCAREName:
        return EarthCAREName(
            mission=self.code,
            product=split_product_url(url)[0],
            filename=os.path.basename(url),
            product_type=extract_product_type(url),
            baseline=extract_baseline(url),
            sensing_time=extract_sensing_time(url),
            creation_time=extract_creation_time(url),
            orbit=extract_orbit(url),
            agency=extract_agency(url),
            frame=extract_frame(url),
        )

    def data_url(self, filename: str) -> Optional[str]:
        """
        Rebuild the MAAP download URL of a product from its filename.

        The archive lays products out as
        ``.../{product_type}/{baseline}/{yyyy}/{mm}/{dd}/{stem}/{stem}/{filename}``
        (the stem repeats), dated by sensing time, so every field comes from
        the filename and no catalogue query is needed.
        """
        info = self.parse(filename)
        dt = info.sensing_time
        if not (info.product_type and info.baseline and dt):
            return None
        name = info.filename
        stem = os.path.splitext(name)[0]
        return (
            f"{DATA_URL}/{info.product_type}/{info.baseline}"
            f"/{dt.year:04d}/{dt.month:02d}/{dt.day:02d}/{stem}/{stem}/{name}"
        )


EARTHCARE = _EarthCARE()
