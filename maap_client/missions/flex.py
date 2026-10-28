"""FLEX: product-name parsing and mission profile.

Documented grammars (FLEXDISC-IPF-PFD-MAG-016 issue 3.3, sections 4.1.1 and
4.1.2; the folder is upper-case, the files lower-case)::

    L1C: FLX_<type>_<start>_<stop>_<creation>_<SSSS>_<CCC>_<LLL>_<AAAA>_<BB>
    L2:  FLX_<type>_<start>_<stop>_<creation>_<TTTTT>_<CCC>_<LLL>_<BB>

UTC sensing start/stop and creation, then for L1C the duration in seconds,
cycle, relative orbit and seconds from the ascending node (ANX); for L2 the
MGRS tile, cycle and relative orbit; finally the baseline. Cycle and relative
orbit are integers, never times. Only these two types are documented (the
document writes the L2 type as ``l2_``, MAAP as ``L2__``; both are read), so
the type-specific fields and creation_time are extracted for L1C and L2 only.
Every other type (L0, L1B, RAW, ANC, RAC, AUX; the L1B names look like L1C but
are not documented) gets type, baseline and sensing_time only. The ESA naming
note for those (ESA-EOPG-EOEP-TN-0015) is not published.

sensing_time is the first timestamp of the name, which equals the item's
start_datetime for every product type of every fixture item.

The FLEXL2AuxProductsInternal types listed in NO_BASELINE_PRODUCTS have no
baseline in their URL and no documented name grammar: their baseline is
NO_BASELINE (the trailing ``_01`` of their names is never read as one). FLEX
downloads are not validated (MAAP answers 403 without access).
"""

import os
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
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
    "FLEXL0AncProductsInternal",
    "FLEXL0CALProductsInternal",
    "FLEXL0EOProductsInternal",
    "FLEXL0NotNomProductsInternal",
    "FLEXL1BCalProductsInternal",
    "FLEXL1BEOProductsInternal",
    "FLEXL1BAncProductsInternal",
    "FLEXL1CEOProductsInternal",
    "FLEXL2EOProductsInternal",
    "FLEXRAWProductsInternal",
    "FLEXL1AuxProductsInternal",
    "FLEXL2AuxProductsInternal",
    "FLEXL1AuxCCDBInternal",
    "FLEXTestAuxProducts",
    "FLEXTestL1Products",
    "FLEXTestL2Products",
    "FLEXTestRAWL0Products",
)

# Verified rule: the 10 characters after FLX_ equal `product:type` on every
# fixture item. The documented L2 example writes `l2_` plus a 6-character
# type, which is normalised to MAAP's `L2__`.
_PRODUCT_TYPE = re.compile(r"^FLX_(.{10})_\d{8}T", re.IGNORECASE)
_L2_SHORT_TYPE = re.compile(r"^FLX_(L2)_([A-Z0-9]{6})_\d{8}T", re.IGNORECASE)
_SENSING = re.compile(r"_(\d{8}T\d{6})_")
# Verified rule: the archive layout `/FLEX/<type>/<baseline>/YYYY/MM/DD/`
# carries the baseline of every fixture item that has a `version`, including
# the CCDB `C0` baselines that the product name does not hold.
_URL_BASELINE = re.compile(r"/FLEX/[^/]+/([^/]+)/\d{4}/\d{2}/\d{2}/")

_TIME = r"\d{8}T\d{6}"
# Optional suffix and extension of the internal files (section 4.1.1)
_TAIL = r"(?:_[A-Z0-9]+)?(?:\.[A-Z0-9]+)?$"
_L1C = re.compile(
    rf"^FLX_L1C_[A-Z0-9_]{{6}}_(?P<start>{_TIME})_{_TIME}_(?P<creation>{_TIME})"
    r"_(?P<duration_s>\d{4})_(?P<cycle>\d{3})_(?P<relative_orbit>\d{3})_(?P<anx_seconds>\d{4})"
    rf"_(?P<baseline>\d{{2}}){_TAIL}",
    re.IGNORECASE,
)
_L2 = re.compile(
    rf"^FLX_L2_{{1,2}}[A-Z0-9_]{{6}}_(?P<start>{_TIME})_{_TIME}_(?P<creation>{_TIME})"
    r"_(?P<tile>[A-Z0-9]{5})_(?P<cycle>\d{3})_(?P<relative_orbit>\d{3})"
    rf"_(?P<baseline>\d{{2}}){_TAIL}",
    re.IGNORECASE,
)

# Verified rule: no item of these types (FLEXL2AuxProductsInternal, AUX_CCCRAD
# also FLEXTestAuxProducts) has a baseline in its URL or a catalogue `version`;
# their names end in `_01`, but no document says that is the baseline.
NO_BASELINE_PRODUCTS = frozenset({
    "AUX_CCCRAD", "AUX_DVAERR", "AUX_MACV2_", "AUX_OLISRF", "AUX_REFCEN",
    "AUX_SIFCOV", "AUX_SLISRF", "AUX_UTMTIL", "AUX_V_TEMP",
})

_DATA_ROOT = "https://catalog.maap.eo.esa.int/data/flex-pdgs-01/FLEX"


def _documented(name: str) -> Optional[re.Match]:
    """Match of the L1C or L2 grammar, or None for every other type."""
    return _L1C.match(name) or _L2.match(name)


def _type(name: str) -> Optional[str]:
    product_type = match_group(_PRODUCT_TYPE, name)
    if product_type:
        return product_type.upper()
    short = _L2_SHORT_TYPE.match(name)
    return f"{short.group(1)}__{short.group(2)}".upper() if short else None


def _time(value: Optional[str]) -> Optional[datetime]:
    return parse_timestamp(value.upper(), "%Y%m%dT%H%M%S") if value else None


def _name(name_or_url: str) -> str:
    return FLEX.product_name(name_or_url)


# Cached: parse() reads up to seven fields of the same match (bounded, for long registry runs)
@lru_cache(maxsize=1024)
def _documented_match(name_or_url: str) -> Optional[re.Match]:
    """Match of the L1C or L2 grammar on the product name, or None for every other type."""
    return _documented(_name(name_or_url))


def _documented_field(name_or_url: str, key: str) -> Optional[str]:
    """A field of the L1C or L2 grammar, or None for other types and fields of the other grammar."""
    match = _documented_match(name_or_url)
    return match.groupdict().get(key) if match else None


def _identifier(name_or_url: str, key: str) -> Optional[int]:
    value = _documented_field(name_or_url, key)
    return int(value) if value is not None else None


@dataclass(frozen=True)
class FlexName(ProductName):
    """FLEX product name: ProductName plus the L1C/L2 grammar fields."""

    duration_s: Optional[int] = None
    cycle: Optional[int] = None
    relative_orbit: Optional[int] = None
    anx_seconds: Optional[int] = None
    tile: Optional[str] = None  # MGRS tile (L2)


def extract_product_type(name_or_url: str) -> Optional[str]:
    """Product type, e.g. ``L1C_FLXSYN``; the documented ``l2_`` is read as ``L2__``."""
    return _type(_name(name_or_url))


def extract_baseline(name_or_url: str) -> Optional[str]:
    """Baseline from the URL path, else from an L1C/L2 name; NO_BASELINE for types without one."""
    baseline = match_group(_URL_BASELINE, name_or_url) or _documented_field(name_or_url, "baseline")
    return declared_baseline(baseline, extract_product_type(name_or_url), NO_BASELINE_PRODUCTS)


def extract_sensing_time(name_or_url: str) -> Optional[datetime]:
    """First timestamp of the name as UTC."""
    return _time(match_group(_SENSING, _name(name_or_url)))


def extract_creation_time(name_or_url: str) -> Optional[datetime]:
    """Creation timestamp of an L1C/L2 name as UTC."""
    return _time(_documented_field(name_or_url, "creation"))


def extract_orbit(name_or_url: str) -> None:
    """Always None: FLEX names carry no absolute orbit."""


def extract_duration_s(name_or_url: str) -> Optional[int]:
    """Duration in seconds (L1C)."""
    return _identifier(name_or_url, "duration_s")


def extract_cycle(name_or_url: str) -> Optional[int]:
    """Cycle number (L1C, L2)."""
    return _identifier(name_or_url, "cycle")


def extract_relative_orbit(name_or_url: str) -> Optional[int]:
    """Relative orbit number (L1C, L2)."""
    return _identifier(name_or_url, "relative_orbit")


def extract_anx_seconds(name_or_url: str) -> Optional[int]:
    """Seconds from the ascending node (L1C)."""
    return _identifier(name_or_url, "anx_seconds")


def extract_tile(name_or_url: str) -> Optional[str]:
    """MGRS tile, upper-case (L2)."""
    tile = _documented_field(name_or_url, "tile")
    return tile.upper() if tile else None


class _Flex(Mission):
    name = "FLEX"
    code = "FLX"
    prefix = "FLX_"
    collections = COLLECTIONS
    # earliest start_datetime among the catalogue items (AUX validity starts),
    # rounded down to the day
    start = "2016-08-01T00:00:00Z"
    end = "2045-12-31T23:59:59Z"
    default_formats = ("zip",)
    orbit_offline = "none"
    no_baseline_products = NO_BASELINE_PRODUCTS

    def parse(self, url: str) -> FlexName:
        return FlexName(
            mission=self.code,
            product=split_product_url(url)[0],
            filename=os.path.basename(url),
            product_type=extract_product_type(url),
            baseline=extract_baseline(url),
            sensing_time=extract_sensing_time(url),
            creation_time=extract_creation_time(url),
            orbit=extract_orbit(url),
            duration_s=extract_duration_s(url),
            cycle=extract_cycle(url),
            relative_orbit=extract_relative_orbit(url),
            anx_seconds=extract_anx_seconds(url),
            tile=extract_tile(url),
        )

    def data_url(self, filename: str) -> Optional[str]:
        """
        Rebuild the download URL of an L1C or L2 file, whose name holds the
        baseline (sections 4.1.1/4.1.2); other types carry it only in the URL.
        """
        basename = os.path.basename(filename)
        match = _documented(basename)
        sensing = _time(match.group("start")) if match else None
        if not match or sensing is None:
            return None
        product_type = _type(basename)
        # the product folder is the name up to the baseline, upper-case
        product = f"FLX_{product_type}_{basename[match.end('start') - 15:match.end('baseline')]}".upper()
        return (
            f"{_DATA_ROOT}/{product_type}/{match.group('baseline')}/{sensing:%Y/%m/%d}"
            f"/{product}/{product}/{basename}"
        )


FLEX = _Flex()
