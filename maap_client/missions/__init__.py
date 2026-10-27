"""Mission modules: everything specific to one ESA mission (stdlib only)."""

import os
from typing import Mapping, Optional, Sequence

from maap_client.missions.aeolus import AEOLUS
from maap_client.missions.base import Mission, ProductName, product_folder, split_product_url
from maap_client.missions.biomass import BIOMASS
from maap_client.missions.earthcare import EARTHCARE
from maap_client.missions.flex import FLEX

MISSIONS: dict[str, Mission] = {m.name: m for m in (EARTHCARE, AEOLUS, BIOMASS, FLEX)}

__all__ = [
    "MISSIONS",
    "Mission",
    "ProductName",
    "get_mission",
    "mission_for_collection",
    "mission_for_filename",
    "split_product_url",
]


def get_mission(name: str) -> Mission:
    """Look up a mission by name, case-insensitively; ValueError lists the known names."""
    for mission in MISSIONS.values():
        if mission.name.lower() == name.lower():
            return mission
    raise ValueError(f"Unknown mission '{name}'. Known missions: {', '.join(MISSIONS)}")


def mission_for_filename(name_or_url: str) -> Optional[Mission]:
    """
    Mission whose product-name prefix starts the basename, case-insensitively.

    Falls back to the product directory of an archive URL, then to the
    product folder after YYYY/MM/DD of a local ``--product-dir`` path, for
    files that are not named after the product (e.g. ``schema/*.xsd``).
    """
    candidates = (
        os.path.basename(name_or_url),
        split_product_url(name_or_url)[0],
        product_folder(name_or_url),
    )
    for candidate in filter(None, candidates):
        for mission in MISSIONS.values():
            if candidate.upper().startswith(mission.prefix.upper()):
                return mission
    return None


def mission_for_collection(
    collection: str, extra: Mapping[str, Sequence[str]] = {}
) -> Optional[Mission]:
    """
    Mission owning a collection: its profile collections plus ``extra``
    (mission name -> additional collections, e.g. from the config).
    """
    for mission in MISSIONS.values():
        if collection in mission.collections or collection in extra.get(mission.name, ()):
            return mission
    return None
