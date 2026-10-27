"""Aeolus: product-name parsing and mission profile.

Name: ``AE_<CCCC>_<file type>_<start>[_<duration ms>_<orbit>|_<stop>]_<version>.<ext>``
where CCCC is the file class (OPER, RPRO, ...). The naming is not publicly
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
from typing import Optional

from maap_client.missions.base import Mission, ProductName, parse_timestamp, split_product_url

COLLECTIONS = (
    "AeolusBaseline16Products10",
    "AeolusEOLProducts10",
    "AeolusL2CProducts10",
    "AeolusL0ProductsB16",
    "AeolusAdditionalProducts",
)

# First timestamp: with milliseconds (9-digit time) or without (6-digit time)
_SENSING = re.compile(r"_(\d{8}T\d{6}(?:\d{3})?)_")
_FILE_CLASS = re.compile(r"^AE_([A-Z]{4})_")
# Verified rule: the 10 characters after AE_<CCCC>_ equal `product:type` on
# every fixture item (shorter types are padded with underscores).
_PRODUCT_TYPE = re.compile(r"^AE_[A-Z]{4}_([A-Z0-9_]{10})_\d{8}T\d{6}")
# Verified rule: the archive path holds .../<file type>/<baseline>/YYYY/MM/DD/;
# the baseline is the segment after the directory equal to the file type and
# equals the item's `version` where the catalogue has one (aux products
# without version use the literal `NNAA`).
_BASELINE_PATH = re.compile(r"/(?P<type>[A-Z0-9_]{10})/(?P<baseline>[A-Za-z0-9]{2,4})/\d{4}/\d{2}/\d{2}/", re.IGNORECASE)
_ORBIT = re.compile(r"_(\d{6})_\d{4}\.[A-Z]{3}$", re.IGNORECASE)
_DURATION = re.compile(r"_\d{8}T\d{9}_(\d{9})_\d{6}_\d{4}\.[A-Z]{3}$", re.IGNORECASE)
_VERSION = re.compile(r"_(\d{4})\.[A-Z]{3}$", re.IGNORECASE)


def _group(pattern: re.Pattern, text: str) -> Optional[str]:
    match = pattern.search(text)
    return match.group(1) if match else None


def _baseline(url: str, product_type: Optional[str]) -> Optional[str]:
    if product_type is None:
        return None
    for match in _BASELINE_PATH.finditer(url):
        if match.group("type").upper() == product_type:
            return match.group("baseline")
    return None


class _Aeolus(Mission):
    name = "Aeolus"
    code = "AE"
    prefix = "AE_"
    collections = COLLECTIONS
    start = "2018-08-22T00:00:00Z"
    end = "2023-07-28T23:59:59Z"
    default_formats = ("dbl", "nc", "bufr", "eef")
    orbit_offline = True
    orbit_frame_suffix = False

    def parse(self, url: str) -> ProductName:
        name = self.product_name(url)
        product_type = _group(_PRODUCT_TYPE, name)
        sensing = _group(_SENSING, name)
        # Aeolus is an ESA mission: the agency is always EX
        return ProductName(
            mission=self.code,
            product=split_product_url(url)[0],
            filename=os.path.basename(url),
            product_type=product_type,
            baseline=_baseline(url, product_type),
            agency="EX",
            sensing_time=parse_timestamp(sensing, "%Y%m%dT%H%M%S%f" if sensing and len(sensing) > 15 else "%Y%m%dT%H%M%S") if sensing else None,
            creation_time=None,
            orbit_frame=_group(_ORBIT, name),
            fields={
                "file_class": _group(_FILE_CLASS, name),
                "duration_ms": _group(_DURATION, name),
                "file_version": _group(_VERSION, name),
            },
        )

    def data_url(self, filename: str) -> Optional[str]:
        """Aeolus URLs hold the baseline only in the archive path: not derivable."""
        return None


AEOLUS = _Aeolus()
