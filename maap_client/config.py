"""Configuration management for MAAP client."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import os

from maap_client.constants import (
    DEFAULT_CATALOG_URL,
    DEFAULT_TOKEN_URL,
    DEFAULT_MISSION,
    DEFAULT_MISSION_START,
    DEFAULT_MISSION_END,
    DEFAULT_COLLECTIONS,
    DEFAULT_DATA_DIR,
    DEFAULT_CATALOG_DIR,
    DEFAULT_BUILT_CATALOG_DIR,
    DEFAULT_REGISTRY_DIR,
    DEFAULT_CREDENTIALS_FILE,
)
from maap_client.exceptions import InvalidRequestError
from maap_client.missions import MISSIONS, get_mission

# Keys of a legacy [mission] section read as overrides of the named mission.
LEGACY_MISSION_KEYS = ("start", "end", "collections", "collections_extend")


def _config_mission(name: str, where: str) -> str:
    """Canonical name of a mission named in config.toml; an unknown name is an invalid request."""
    try:
        return get_mission(name).name
    except ValueError as e:
        raise InvalidRequestError(f"{e} (config.toml {where})") from e


@dataclass
class MaapConfig:
    """Central configuration for MAAP client."""

    # Directories
    data_dir: Path = field(default_factory=lambda: Path(DEFAULT_DATA_DIR).expanduser())
    catalog_dir: Path = field(default_factory=lambda: Path(DEFAULT_CATALOG_DIR).expanduser())
    built_catalog_dir: Path = field(default_factory=lambda: Path(DEFAULT_BUILT_CATALOG_DIR).expanduser())
    registry_dir: Path = field(default_factory=lambda: Path(DEFAULT_REGISTRY_DIR).expanduser())

    # Credentials
    credentials_file: Path = field(
        default_factory=lambda: Path(DEFAULT_CREDENTIALS_FILE).expanduser()
    )

    # API endpoints
    catalog_url: str = DEFAULT_CATALOG_URL
    token_url: str = DEFAULT_TOKEN_URL

    # Mission settings
    mission: str = DEFAULT_MISSION
    mission_start: str = DEFAULT_MISSION_START
    mission_end: str = DEFAULT_MISSION_END

    # Known collections
    collections: list[str] = field(default_factory=lambda: DEFAULT_COLLECTIONS.copy())

    # Formats tried in order when no --format is given
    default_formats: tuple[str, ...] = get_mission(DEFAULT_MISSION).default_formats

    # Mission chosen in config.toml (default_mission or legacy [mission].name)
    default_mission: Optional[str] = None

    # Parsed [missions.X] tables (and a legacy [mission] section), by canonical mission name
    mission_overrides: dict[str, dict] = field(default_factory=dict)

    def effective_collections(self, mission: str) -> list[str]:
        """Collections of a mission: its profile, replaced or extended by the config."""
        profile = get_mission(mission)
        overrides = self.mission_overrides.get(profile.name, {})
        collections = list(overrides.get("collections") or profile.collections)
        for collection in overrides.get("collections_extend") or ():
            if collection not in collections:
                collections.append(collection)
        return collections

    def extra_collections(self) -> dict[str, list[str]]:
        """
        Collections the config names for each mission (``collections`` and
        ``collections_extend``), the ``extra`` of ``missions.mission_for_collection``.
        """
        return {
            name: [*(overrides.get("collections") or ()), *(overrides.get("collections_extend") or ())]
            for name, overrides in self.mission_overrides.items()
        }

    def apply_mission(self, mission: str) -> None:
        """Set the mission settings from its profile and the config overrides."""
        profile = get_mission(mission)
        overrides = self.mission_overrides.get(profile.name, {})
        self.mission = profile.name
        self.mission_start = overrides.get("start") or profile.start
        self.mission_end = overrides.get("end") or profile.end
        self.collections = self.effective_collections(profile.name)
        default_format = overrides.get("default_format")
        self.default_formats = (default_format,) if default_format else profile.default_formats

    def _check_collections_unique(self) -> None:
        """
        A collection belongs to exactly one mission (its profile or the config
        naming it); raise InvalidRequestError otherwise, so that
        ``mission_for_collection`` is unambiguous.
        """
        extra = self.extra_collections()
        owners: dict[str, str] = {}
        for name, profile in MISSIONS.items():
            for collection in dict.fromkeys([*profile.collections, *extra.get(name, ())]):
                if collection in owners:
                    raise InvalidRequestError(
                        f"Collection '{collection}' is listed in missions {owners[collection]} "
                        f"and {name}; a collection belongs to one mission"
                    )
                owners[collection] = name

    @classmethod
    def from_env(cls) -> "MaapConfig":
        """Load configuration from environment variables."""
        config = cls()

        if env_data := os.environ.get("MAAP_DATA_DIR"):
            config.data_dir = Path(env_data).expanduser()
        if env_catalog := os.environ.get("MAAP_CATALOG_DIR"):
            config.catalog_dir = Path(env_catalog).expanduser()
        if env_built_catalog := os.environ.get("MAAP_BUILT_CATALOG_DIR"):
            config.built_catalog_dir = Path(env_built_catalog).expanduser()
        if env_registry := os.environ.get("MAAP_REGISTRY_DIR"):
            config.registry_dir = Path(env_registry).expanduser()
        if env_creds := os.environ.get("MAAP_CREDENTIALS_FILE"):
            config.credentials_file = Path(env_creds).expanduser()
        if env_catalog_url := os.environ.get("MAAP_CATALOG_URL"):
            config.catalog_url = env_catalog_url
        if env_mission_start := os.environ.get("MAAP_MISSION_START"):
            config.mission_start = env_mission_start
        if env_mission_end := os.environ.get("MAAP_MISSION_END"):
            config.mission_end = env_mission_end

        return config

    @classmethod
    def from_file(cls, config_path: Path, mission: Optional[str] = None) -> "MaapConfig":
        """
        Load configuration from TOML file.

        The mission settings come from the profile of ``mission`` (or the
        configured default mission, else EarthCARE) with its overrides applied.
        """
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib

        config = cls()

        data = {}
        if config_path.exists():
            with open(config_path, "rb") as f:
                data = tomllib.load(f)

        # Parse paths section
        if paths := data.get("paths"):
            if data_dir := paths.get("data_dir"):
                config.data_dir = Path(data_dir).expanduser()
            if catalog_dir := paths.get("catalog_dir"):
                config.catalog_dir = Path(catalog_dir).expanduser()
            if built_catalog_dir := paths.get("built_catalog_dir"):
                config.built_catalog_dir = Path(built_catalog_dir).expanduser()
            if registry_dir := paths.get("registry_dir"):
                config.registry_dir = Path(registry_dir).expanduser()
            if creds := paths.get("credentials_file"):
                config.credentials_file = Path(creds).expanduser()

        # Parse api section
        if api := data.get("api"):
            if catalog_url := api.get("catalog_url"):
                config.catalog_url = catalog_url
            if token_url := api.get("token_url"):
                config.token_url = token_url

        # Legacy [mission] section: overrides of the named mission, which is also the default
        if legacy := data.get("mission"):
            name = _config_mission(legacy.get("name") or DEFAULT_MISSION, "[mission] name")
            config.mission_overrides[name] = {
                key: legacy[key] for key in LEGACY_MISSION_KEYS if key in legacy
            }
            if legacy.get("name"):
                config.default_mission = name

        # [missions.X] tables
        for key, table in (data.get("missions") or {}).items():
            config.mission_overrides.setdefault(_config_mission(key, f"[missions.{key}]"), {}).update(table)

        if default_mission := data.get("default_mission"):
            config.default_mission = _config_mission(default_mission, "default_mission")

        config._check_collections_unique()
        config.apply_mission(mission or config.default_mission or DEFAULT_MISSION)

        return config

    @classmethod
    def load(cls, config_path: Optional[Path] = None, mission: Optional[str] = None) -> "MaapConfig":
        """
        Load configuration with priority:
        1. Environment variables
        2. Config file (if provided or default exists)
        3. Defaults

        Mission settings come from the profile of ``mission`` (or the
        configured default mission, else EarthCARE) and its config overrides;
        MAAP_MISSION_START/END apply on top.
        """
        if config_path is None:
            config_path = Path("~/.maap/config.toml").expanduser()

        config = cls.from_file(config_path, mission)

        # Override with environment variables
        env_config = cls.from_env()
        if os.environ.get("MAAP_DATA_DIR"):
            config.data_dir = env_config.data_dir
        if os.environ.get("MAAP_CATALOG_DIR"):
            config.catalog_dir = env_config.catalog_dir
        if os.environ.get("MAAP_BUILT_CATALOG_DIR"):
            config.built_catalog_dir = env_config.built_catalog_dir
        if os.environ.get("MAAP_REGISTRY_DIR"):
            config.registry_dir = env_config.registry_dir
        if os.environ.get("MAAP_CREDENTIALS_FILE"):
            config.credentials_file = env_config.credentials_file
        if os.environ.get("MAAP_CATALOG_URL"):
            config.catalog_url = env_config.catalog_url
        if os.environ.get("MAAP_MISSION_START"):
            config.mission_start = env_config.mission_start
        if os.environ.get("MAAP_MISSION_END"):
            config.mission_end = env_config.mission_end

        return config

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.catalog_dir.mkdir(parents=True, exist_ok=True)
        self.built_catalog_dir.mkdir(parents=True, exist_ok=True)
        self.registry_dir.mkdir(parents=True, exist_ok=True)

        # Ensure credentials directory exists
        self.credentials_file.parent.mkdir(parents=True, exist_ok=True)
