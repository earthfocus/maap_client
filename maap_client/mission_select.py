"""Mission selection: the input (collection or URLs) decides first, then the selection order."""

import os
from pathlib import Path
from typing import Optional, Sequence

from maap_client.config import MaapConfig
from maap_client.constants import DEFAULT_MISSION
from maap_client.exceptions import InvalidRequestError
from maap_client.missions import Mission, get_mission, mission_for_filename

# Persisted by 'maap mission use'; expanded at call time so tests can redirect it.
ACTIVE_MISSION_FILE = Path("~/.maap/active_mission")


def read_active_mission() -> Optional[str]:
    """Mission name persisted by 'maap mission use', or None when unset."""
    path = ACTIVE_MISSION_FILE.expanduser()
    if not path.exists():
        return None
    return path.read_text().strip() or None


def write_active_mission(name: str) -> None:
    """Persist the active mission (canonical name); ValueError for an unknown name."""
    canonical = get_mission(name).name
    path = ACTIVE_MISSION_FILE.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical + "\n")


def _named_mission(name: str, origin: str) -> Mission:
    """Look up a mission given by the user; an unknown name is an invalid request."""
    try:
        return get_mission(name)
    except ValueError as e:
        raise InvalidRequestError(f"{e} (from {origin})") from e


def resolve_mission(
    collection: Optional[str],
    urls: Sequence[str],
    cli_mission: Optional[str],
    config: MaapConfig,
) -> tuple[Mission, str]:
    """
    Decide the mission of a command and where the choice came from.

    A collection known to a mission (profile or config) or URLs whose
    filenames name a mission decide it; ``--mission`` may confirm but not
    contradict them. Otherwise the selection order applies: ``--mission`` >
    MAAP_MISSION > active mission file > config default > EarthCARE.

    Returns (mission, source) with source one of "collection", "url",
    "--mission", "MAAP_MISSION", "active", "config", "default".
    """
    inferred: Optional[Mission] = None
    source = ""
    if collection:
        name = config.collection_mission(collection)
        if name:
            inferred, source = get_mission(name), "collection"

    # URLs that no mission recognises are left out of the inference
    url_missions = {m.name: m for m in map(mission_for_filename, urls) if m is not None}
    if len(url_missions) > 1:
        raise InvalidRequestError(f"URL list mixes missions: {', '.join(sorted(url_missions))}")
    if url_missions:
        url_mission = next(iter(url_missions.values()))
        if inferred is not None and inferred is not url_mission:
            raise InvalidRequestError(
                f"Collection '{collection}' belongs to {inferred.name} "
                f"but the URLs are {url_mission.name} products"
            )
        if inferred is None:
            inferred, source = url_mission, "url"

    if cli_mission:
        requested = _named_mission(cli_mission, "--mission")
        if inferred is not None and requested is not inferred:
            what = f"collection '{collection}'" if source == "collection" else "the URLs"
            raise InvalidRequestError(
                f"--mission {requested.name} contradicts the mission of {what} ({inferred.name})"
            )
    if inferred is not None:
        return inferred, source
    if cli_mission:
        return requested, "--mission"

    if env_mission := os.environ.get("MAAP_MISSION"):
        return _named_mission(env_mission, "MAAP_MISSION"), "MAAP_MISSION"
    if active := read_active_mission():
        return _named_mission(active, str(ACTIVE_MISSION_FILE.expanduser())), "active"
    if config.default_mission:
        return get_mission(config.default_mission), "config"
    return get_mission(DEFAULT_MISSION), "default"
