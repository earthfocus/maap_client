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
from typing import Optional

from maap_client.missions.base import Mission, ProductName, parse_timestamp, split_product_url

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
_ORBIT_FRAME = re.compile(r"_(\d{5})([A-Z])\.[a-zA-Z0-9]+$", re.IGNORECASE)
_AGENCY = re.compile(r"^ECA_([A-Z]{2})[A-Z]{2}_")
_BASELINE = re.compile(r"^ECA_[A-Z]{2}([A-Z]{2})_")
_PRODUCT_TYPE = re.compile(r"^ECA_[A-Z]{4}_(.+?)_\d{8}T\d{6}Z_")


def _group(pattern: re.Pattern, filename: str) -> Optional[str]:
    match = pattern.search(filename)
    return match.group(1) if match else None


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

    def parse(self, url: str) -> ProductName:
        name = self.product_name(url)
        sensing = _group(_SENSING, name)
        creation = _group(_CREATION, name)
        orbit_frame = _ORBIT_FRAME.search(name)
        return ProductName(
            mission=self.code,
            product=split_product_url(url)[0],
            filename=os.path.basename(url),
            product_type=_group(_PRODUCT_TYPE, name),
            baseline=_group(_BASELINE, name),
            agency=_group(_AGENCY, name),
            sensing_time=parse_timestamp(sensing, "%Y%m%dT%H%M%S") if sensing else None,
            creation_time=parse_timestamp(creation, "%Y%m%dT%H%M%SZ") if creation else None,
            orbit_frame=f"{orbit_frame.group(1)}{orbit_frame.group(2).upper()}" if orbit_frame else None,
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
