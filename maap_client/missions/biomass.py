"""Biomass: product-name parsing and mission profile.

Product directory (BIO-BPS-L1PFD-ARE-010076 v1.6.1 sections 3.4/5.3 for L1,
Forest Height Products Format Specification v3.4.0 sections 3.2/5.2 for L2)::

    BIO_<TTTTTTTTTT>_<start>_<stop>_<P>_G<CC>_M<NN>_C<nn>_T<TTT>_F<FFF>_<BB>_<DDDDDD>

type, UTC start/stop, mission phase, global coverage, major cycle, repeat
cycle (``___`` in L2), track, frame, baseline, compact creation date. Blank
fields are written ``___``. Internal files are lower-cased and drop baseline
and creation date, so every field is read from the product directory of the
URL, never from the file name.

Meaning of sensing_time (first timestamp of the name; equals the item's
start_datetime within 1 s for every product type of every fixture item: names
hold whole seconds, the catalogue milliseconds):

    L1a, L1b ......... start of acquisition (Zero Doppler time), section 3.4
    L1c .............. start after coregistration, which differs from the
                       source L1a (section 5.3)
    L2a .............. start of the validity of the stack (FH spec 3.2)
    L2b .............. no timestamps in the name: sensing_time is None
    AUX_ORB___, AUX_ATT___, AUX_INS___, AUX_PP1___, AUX_PPS___, AUX_TEC___,
    AUX_CLM___ ....... UTC validity start (BIO-BPS-AUX-FMT-ARE-010163 v3.6.1
                       section 3.2)
    L0, CalVal, Simulated, other AUX, items of other missions' types
    (MPL_ORBPRE, ...) not publicly documented; validity/acquisition start

The compact creation date has no documented encoding, so creation_time is
always None. M, C, T and F are identifiers (integers), never times.

The T/F/C/M/G/phase fields are extracted only for the types the documents
define (L1a/b/c, L2a); the other types get type, baseline and sensing_time
only.
"""

import os
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Optional

from maap_client.missions.base import (
    FilterSpec,
    Mission,
    ProductName,
    declared_baseline,
    match_group,
    parse_filter_values,
    parse_timestamp,
    product_folder,
    split_product_url,
)

COLLECTIONS = (
    "BiomassLevel0",
    "BiomassLevel0IOC",
    "BiomassLevel1a",
    "BiomassLevel1aIOC",
    "BiomassLevel1b",
    "BiomassLevel1bIOC",
    "BiomassLevel1c",
    "BiomassLevel1cIOC",
    "BiomassLevel2a",
    "BiomassLevel2aIOC",
    "BiomassLevel2b",
    "BiomassLevel2bIOC",
    "BiomassAux",
    "BiomassAuxIOC",
    "BiomassAuxRest",
    "BiomassCalVal10",
    "BiomassSimulated",
)

# Verified rule: the 10 characters after BIO_ (after BIO_OPER_ for the
# MPL_ORBPRE orbit files) equal `product:type` on every fixture item. They are
# followed by the first timestamp, or by `_<P>_G` for L2b (no timestamps).
_PRODUCT_TYPE = re.compile(r"^BIO_(?:OPER_)?(.{10})_(?:\d{8}T|[A-Z]_G)", re.IGNORECASE)
_SENSING = re.compile(r"^BIO_(?:OPER_)?.{10}_(\d{8}T\d{6})_", re.IGNORECASE)
# Verified rule: the trailing `_<BB>_<DDDDDD>` of the product directory equals
# the item's `version` on every fixture item, for every type (same tail as the
# documented L1/L2/AUX grammars). Names without it (MPL_ORBPRE) have no baseline.
_BASELINE = re.compile(r"_(\d{2})_[A-Z0-9]{6}$", re.IGNORECASE)

# Documented types (sections 3.4/5.3 and FH spec 3.2): L1a/b, L1c, L2a
_DOCUMENTED = re.compile(
    r"^BIO_(?:S[123]_(?:SCS__1S|SCS[12XY]_1S|DGM__1S|SCS__1M|STA__1S)|FP_.{7})"
    r"_\d{8}T\d{6}_\d{8}T\d{6}"
    r"_(?P<phase>[A-Z])_G(?P<global_coverage>\d{2}|__)_M(?P<major_cycle>\d{2}|__)"
    r"_C(?P<repeat_cycle>\d{2}|__)_T(?P<track>\d{3}|___)_F(?P<frame>\d{3}|___)"
    r"_\d{2}_[A-Z0-9]{6}$",
    re.IGNORECASE,
)

# Verified rule: no MPL_ORBPRE item (BiomassAux, BiomassAuxIOC) has a baseline
# in its URL, its name or a catalogue `version`.
NO_BASELINE_PRODUCTS = frozenset({"MPL_ORBPRE"})

# Product types that hold one file by definition, so their files need no
# --product-dir: MPL_ORBPRE is a mission planning orbit file, one EO CFI .EOF
# file (EO CFI orbit file format). Types merely seen with one enclosure in a
# sample of items are not declared: a sample is not a property.
SINGLE_FILE_PRODUCTS = frozenset({"MPL_ORBPRE"})


def _product(url: str) -> str:
    # Verified rule: the product directory is the segment after the YYYY/MM/DD
    # folders. Some aux enclosures sit in an inner directory with another compact
    # creation date, so the repeated-name anchor alone would pick the wrong one.
    return product_folder(url) or split_product_url(url)[0]


# Cached: parse() reads six fields of the same match (bounded, for long registry runs)
@lru_cache(maxsize=1024)
def _documented_match(name_or_url: str) -> Optional[re.Match]:
    """Match of the documented grammar on the product directory, or None for other types."""
    return _DOCUMENTED.match(_product(name_or_url))


def _documented(name_or_url: str, key: str) -> Optional[str]:
    """A field of the documented grammar, or None for other types and blank (``__``) fields."""
    match = _documented_match(name_or_url)
    value = match.group(key) if match else None
    return None if value is None or value.startswith("_") else value


def _identifier(name_or_url: str, key: str) -> Optional[int]:
    value = _documented(name_or_url, key)
    return int(value) if value is not None else None


@dataclass(frozen=True)
class BiomassName(ProductName):
    """Biomass product name: ProductName plus the L1/L2a grammar fields (identifiers as int)."""

    phase: Optional[str] = None
    global_coverage: Optional[int] = None
    major_cycle: Optional[int] = None
    repeat_cycle: Optional[int] = None
    track: Optional[int] = None
    frame: Optional[int] = None


def extract_product_type(name_or_url: str) -> Optional[str]:
    """Product type, e.g. ``S3_DGM__1S``."""
    product_type = match_group(_PRODUCT_TYPE, _product(name_or_url))
    return product_type.upper() if product_type else None


def extract_baseline(name_or_url: str) -> Optional[str]:
    """Baseline, e.g. ``02``; NO_BASELINE for the types that have none."""
    baseline = match_group(_BASELINE, _product(name_or_url))
    return declared_baseline(baseline, extract_product_type(name_or_url), NO_BASELINE_PRODUCTS)


def extract_sensing_time(name_or_url: str) -> Optional[datetime]:
    """First timestamp of the name as UTC."""
    sensing = match_group(_SENSING, _product(name_or_url))
    return parse_timestamp(sensing.upper(), "%Y%m%dT%H%M%S") if sensing else None


def extract_creation_time(name_or_url: str) -> None:
    """Always None: the compact creation date has no documented encoding."""


def extract_orbit(name_or_url: str) -> None:
    """Always None: Biomass names carry no absolute orbit."""


def extract_phase(name_or_url: str) -> Optional[str]:
    """Mission phase letter, upper-case."""
    phase = _documented(name_or_url, "phase")
    return phase.upper() if phase else None


def extract_global_coverage(name_or_url: str) -> Optional[int]:
    """Global coverage identifier (``G``)."""
    return _identifier(name_or_url, "global_coverage")


def extract_major_cycle(name_or_url: str) -> Optional[int]:
    """Major cycle identifier (``M``)."""
    return _identifier(name_or_url, "major_cycle")


def extract_repeat_cycle(name_or_url: str) -> Optional[int]:
    """Repeat cycle identifier (``C``)."""
    return _identifier(name_or_url, "repeat_cycle")


def extract_track(name_or_url: str) -> Optional[int]:
    """Track number (``T``)."""
    return _identifier(name_or_url, "track")


def extract_frame(name_or_url: str) -> Optional[int]:
    """Frame number (``F``)."""
    return _identifier(name_or_url, "frame")


class _Biomass(Mission):
    # no data_url: the collection and date are only in the archive path, not in the filename
    name = "Biomass"
    code = "BIO"
    prefixes = ("BIO_",)
    collections = COLLECTIONS
    # earliest start_datetime among the catalogue items (an AUX_PP0 validity
    # start), rounded down to the day
    start = "2010-01-01T00:00:00Z"
    end = "2045-12-31T23:59:59Z"
    default_formats = ("zip",)
    # MAAP queryables; offline values come from the T/F/C/M fields of the name
    filters = (
        FilterSpec("track", "track number(s)", parse_filter_values, "track", "track"),
        FilterSpec("frame", "frame number(s)", parse_filter_values, "frame", "frame"),
        FilterSpec("repeat_cycle", "repeat cycle number(s)", parse_filter_values,
                   "eofeos:repeat_cycle_id", "repeat_cycle"),
        FilterSpec("major_cycle", "major cycle number(s)", parse_filter_values,
                   "eofeos:major_cycle_id", "major_cycle"),
    )
    orbit_offline = "none"
    no_baseline_products = NO_BASELINE_PRODUCTS
    files_need_product_dir = True
    single_file_products = SINGLE_FILE_PRODUCTS

    def parse(self, url: str) -> BiomassName:
        return BiomassName(
            mission=self.code,
            product=_product(url),
            filename=os.path.basename(url),
            product_type=extract_product_type(url),
            baseline=extract_baseline(url),
            sensing_time=extract_sensing_time(url),
            creation_time=extract_creation_time(url),
            orbit=extract_orbit(url),
            phase=extract_phase(url),
            global_coverage=extract_global_coverage(url),
            major_cycle=extract_major_cycle(url),
            repeat_cycle=extract_repeat_cycle(url),
            track=extract_track(url),
            frame=extract_frame(url),
        )


BIOMASS = _Biomass()
