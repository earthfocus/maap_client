"""Constants for MAAP client."""

from maap_client.missions import EARTHCARE

__version__ = "0.3.0"

# API endpoints (defaults)
DEFAULT_CATALOG_URL = "https://catalog.maap.eo.esa.int/catalogue"
DEFAULT_TOKEN_URL = "https://iam.maap.eo.esa.int/realms/esa-maap/protocol/openid-connect/token"

# Mission info (defaults - can be overridden in config.toml)
DEFAULT_MISSION = EARTHCARE.name
DEFAULT_MISSION_START = EARTHCARE.start
DEFAULT_MISSION_END = EARTHCARE.end

# Collections of the default mission (can be extended in config.toml)
DEFAULT_COLLECTIONS = list(EARTHCARE.collections)

# Default directories (under ~/.maap/ so pip installs work from any directory)
DEFAULT_DATA_DIR = "~/.maap/data"
DEFAULT_CATALOG_DIR = "~/.maap/catalogs"
DEFAULT_BUILT_CATALOG_DIR = "~/.maap/built_catalogs"
DEFAULT_REGISTRY_DIR = "~/.maap/registry"
DEFAULT_CREDENTIALS_FILE = "~/.maap/credentials.txt"

# Download settings
DEFAULT_CHUNK_SIZE = 8192
DEFAULT_TIMEOUT = 30

# STAC transport retries (transient gateway errors: nginx 502/503/504).
# Backoff factor 2 -> sleeps of 0, 4, 8, 16, 32 s across 5 retries
# (urllib3 skips the backoff before the first retry).
# POST is safe to retry: STAC searches are read-only queries.
STAC_RETRY_TOTAL = 5
STAC_RETRY_BACKOFF_FACTOR = 2
STAC_RETRY_STATUS_FORCELIST = (429, 500, 502, 503, 504)
STAC_RETRY_ALLOWED_METHODS = ("GET", "POST")

# Scope, deliberate: these apply to STAC search only. Downloads get one
# attempt per file (plus the 401/403 token refresh in download.py) and no
# transient retry loop — retry cadence lives in the wrapper

# Where a new 90-day offline token is issued.
TOKEN_RENEW_URL = "https://portal.maap.eo.esa.int/ini/services/auth/token/90dToken.php"

# Token refresh retries when IAM cannot answer (proxy/connection errors or
# a busy status), with the STAC cadence: sleeps of 0, 4, 8, 16, 32 s.
TOKEN_RETRY_TOTAL = 5
TOKEN_RETRY_BACKOFF_FACTOR = 2
TOKEN_RETRY_STATUSES = (429, 500, 502, 503, 504)
