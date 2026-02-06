"""Constants for MAAP client."""

__version__ = "0.1.0"

# API endpoints (defaults)
DEFAULT_CATALOG_URL = "https://catalog.maap.eo.esa.int/catalogue"
DEFAULT_TOKEN_URL = "https://iam.maap.eo.esa.int/realms/esa-maap/protocol/openid-connect/token"

# Mission info (defaults - can be overridden in config.toml)
DEFAULT_MISSION = "EarthCARE"
DEFAULT_MISSION_START = "2024-05-28T00:00:00Z"
DEFAULT_MISSION_END = "2045-12-31T23:59:59Z"

# All known MAAP collections (defaults - can be extended in config.toml)
DEFAULT_COLLECTIONS = [
    # EarthCARE
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
]

# DEFAULT_COLLECTIONS = [
#     # Aeolus
#     "AeolusL1BProducts",
#     "AeolusL2AProducts",
#     "AeolusL2BProducts",
#     "AeolusL2CProducts",
#     "AeolusAuxProducts",
# ]

# Default directories (under ~/.maap/ so pip installs work from any directory)
DEFAULT_DATA_DIR = "~/.maap/data"
DEFAULT_CATALOG_DIR = "~/.maap/catalogs"
DEFAULT_BUILT_CATALOG_DIR = "~/.maap/built_catalogs"
DEFAULT_REGISTRY_DIR = "~/.maap/registry"
DEFAULT_CREDENTIALS_FILE = "~/.maap/credentials.txt"

# Download settings
DEFAULT_CHUNK_SIZE = 8192
DEFAULT_TIMEOUT = 30
