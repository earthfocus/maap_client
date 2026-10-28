"""Mission modules: everything specific to one ESA mission (stdlib only)."""

import os
from typing import Mapping, Optional, Sequence

from maap_client.missions.aeolus import AEOLUS, AeolusName
from maap_client.missions.base import Mission, ProductName, product_folder, split_product_url
from maap_client.missions.biomass import BIOMASS, BiomassName
from maap_client.missions.earthcare import EARTHCARE, EarthCAREName
from maap_client.missions.flex import FLEX, FlexName

MISSIONS: dict[str, Mission] = {m.name: m for m in (EARTHCARE, AEOLUS, BIOMASS, FLEX)}

__all__ = [
    "MISSIONS",
    "AeolusName",
    "BiomassName",
    "EarthCAREName",
    "FlexName",
    "Mission",
    "ProductName",
    "get_mission",
    "mission_for_code",
    "mission_for_collection",
    "mission_for_filename",
    "parse_product",
    "split_product_url",
]


def get_mission(name: str) -> Mission:
    """Look up a mission by name, case-insensitively; ValueError lists the known names."""
    for mission in MISSIONS.values():
        if mission.name.lower() == name.lower():
            return mission
    raise ValueError(f"Unknown mission '{name}'. Known missions: {', '.join(MISSIONS)}")


def mission_for_code(code: str) -> Optional[Mission]:
    """Mission whose filename code (ProductName.mission, e.g. "BIO") is code, or None."""
    for mission in MISSIONS.values():
        if mission.code == code:
            return mission
    return None


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
    collection: str, extra: Optional[Mapping[str, Sequence[str]]] = None
) -> Optional[Mission]:
    """
    Mission owning a collection: its profile collections plus ``extra``
    (mission name -> additional collections, e.g. from the config).
    """
    extra = extra or {}
    for mission in MISSIONS.values():
        if collection in mission.collections or collection in extra.get(mission.name, ()):
            return mission
    return None


def parse_product(name_or_url: str) -> Optional[ProductName]:
    """Parse a product filename or URL with its mission, or None for an unknown prefix."""
    mission = mission_for_filename(name_or_url)
    return mission.parse(name_or_url) if mission else None
