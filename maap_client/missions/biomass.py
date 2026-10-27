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
define (L1a/b/c, L2a, L2b); the other types get type, baseline and
sensing_time only.
"""

import os
import re
from typing import Optional

from maap_client.missions.base import FilterSpec, Mission, ProductName, parse_timestamp, split_product_url

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
_NO_FIELDS = {k: None for k in ("phase", "global_coverage", "major_cycle", "repeat_cycle", "track", "frame")}


# Verified rule: the product directory is the segment after the YYYY/MM/DD
# folders. Some aux enclosures sit in an inner directory with another compact
# creation date, so the repeated-name anchor alone would pick the wrong one.
_PRODUCT_DIR = re.compile(r"/\d{4}/\d{2}/\d{2}/([^/]+)/")


def _product(url: str) -> str:
    match = _PRODUCT_DIR.search(url)
    return match.group(1) if match else split_product_url(url)[0]


def _group(pattern: re.Pattern, text: str) -> Optional[str]:
    match = pattern.search(text)
    return match.group(1) if match else None


def _fields(name: str) -> dict:
    """Documented grammar fields; identifiers as unpadded decimal strings (`002` -> `2`)."""
    match = _DOCUMENTED.match(name)
    if not match:
        return dict(_NO_FIELDS)
    values = match.groupdict()
    return {
        key: None if value.startswith("_") else (value.upper() if key == "phase" else str(int(value)))
        for key, value in values.items()
    }


class _Biomass(Mission):
    name = "Biomass"
    code = "BIO"
    prefix = "BIO_"
    collections = COLLECTIONS
    # earliest start_datetime among the catalogue items (an AUX_PP0 validity
    # start), rounded down to the day
    start = "2010-01-01T00:00:00Z"
    end = "2045-12-31T23:59:59Z"
    default_formats = ("zip",)
    # MAAP queryables; offline values come from the T/F/C/M fields of the name
    filters = (
        FilterSpec("track", "track", "track"),
        FilterSpec("frame", "frame", "frame"),
        FilterSpec("repeat_cycle", "eofeos:repeat_cycle_id", "repeat_cycle"),
        FilterSpec("major_cycle", "eofeos:major_cycle_id", "major_cycle"),
    )
    orbit_offline = False
    orbit_frame_suffix = False

    def parse(self, url: str) -> ProductName:
        name = _product(url)
        product_type = _group(_PRODUCT_TYPE, name)
        sensing = _group(_SENSING, name)
        return ProductName(
            mission=self.code,
            product=name,
            filename=os.path.basename(url),
            product_type=product_type.upper() if product_type else None,
            baseline=_group(_BASELINE, name),
            agency=None,
            sensing_time=parse_timestamp(sensing.upper(), "%Y%m%dT%H%M%S") if sensing else None,
            creation_time=None,
            orbit_frame=None,
            fields=_fields(name),
        )

    def data_url(self, filename: str) -> Optional[str]:
        """Biomass URLs hold the collection and date in the archive path: not derivable."""
        return None


BIOMASS = _Biomass()
