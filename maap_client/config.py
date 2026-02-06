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
    def from_file(cls, config_path: Path) -> "MaapConfig":
        """Load configuration from TOML file."""
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib

        config = cls()

        if not config_path.exists():
            return config

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

        # Parse mission section
        if mission := data.get("mission"):
            if name := mission.get("name"):
                config.mission = name
            if start := mission.get("start"):
                config.mission_start = start
            if end := mission.get("end"):
                config.mission_end = end
            # collections: replace entire list
            if collections := mission.get("collections"):
                config.collections = list(collections)
            # collections_extend: add to existing list
            if collections_extend := mission.get("collections_extend"):
                for c in collections_extend:
                    if c not in config.collections:
                        config.collections.append(c)

        return config

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "MaapConfig":
        """
        Load configuration with priority:
        1. Environment variables
        2. Config file (if provided or default exists)
        3. Defaults
        """
        # Start with defaults
        config = cls()

        # Try to load from file
        if config_path is None:
            config_path = Path("~/.maap/config.toml").expanduser()

        if config_path.exists():
            config = cls.from_file(config_path)

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
