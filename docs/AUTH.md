# Authentication Module Documentation

This document describes the OAuth2 authentication mechanism used by `maap_client` to access ESA MAAP EarthCARE data.

## Overview

The MAAP API requires OAuth2 Bearer token authentication. The `maap_client.auth` module implements a two-tier token system:

1. **OFFLINE_TOKEN** (90-day): Long-lived refresh token obtained manually from ESA portal
2. **ACCESS_TOKEN** (10-hour): Short-lived token used for actual API requests

## Token Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                     ESA MAAP Portal                             │
│     https://portal.maap.eo.esa.int/ini/services/auth/           │
│     token/90dToken.php                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Manual login (every 90 days)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     OFFLINE_TOKEN                               │
│                                                                 │
│  - Lifespan: 90 days                                            │
│  - Storage: credentials.txt                                     │
│  - Renewal: MANUAL (login to ESA portal)                        │
│  - Purpose: Exchange for access tokens                          │
│  - Security: Keep secret, rarely transmitted                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ _refresh_token() - automatic
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ACCESS_TOKEN                                │
│                                                                 │
│  - Lifespan: 10 hours (36000 seconds)                           │
│  - Storage: In-memory (TokenManager._access_token)              │
│  - Renewal: AUTOMATIC (when expired)                            │
│  - Purpose: Authenticate API requests                           │
│  - Security: Short-lived, safe for frequent transmission        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Used in Authorization header
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     MAAP API Requests                           │
│                                                                 │
│  GET https://catalog.maap.eo.esa.int/data/.../file.h5           │
│  Authorization: Bearer <ACCESS_TOKEN>                           │
└─────────────────────────────────────────────────────────────────┘
```

## Credentials File

Location: `~/.maap/credentials.txt` or `./credentials.txt`

Format:
```
CLIENT_ID=offline-token
CLIENT_SECRET=<your_client_secret>
OFFLINE_TOKEN=<your_90_day_token>
```

### How to obtain credentials:

1. Go to: https://portal.maap.eo.esa.int/ini/services/auth/token/90dToken.php
2. Login with your ESA credentials
3. Request a 90-day offline token
4. Copy the values to `credentials.txt`

## Module Components

### 1. Credentials Dataclass

```python
@dataclass
class Credentials:
    client_id: str       # Always "offline-token" for MAAP
    client_secret: str   # From ESA portal
    offline_token: str   # 90-day JWT token from ESA portal
```

### 2. load_credentials()

Loads credentials from file.

```python
from maap_client.auth import load_credentials

creds = load_credentials()  # Uses default path
creds = load_credentials(Path("./my_credentials.txt"))  # Custom path
```

Raises `CredentialsError` if:
- File not found
- Missing required fields (CLIENT_ID, CLIENT_SECRET, OFFLINE_TOKEN)

### 3. TokenManager

Manages the OAuth2 token lifecycle with automatic refresh.

```python
from maap_client.auth import load_credentials, TokenManager

creds = load_credentials()
tm = TokenManager(
    credentials=creds,
    token_url="https://iam.maap.eo.esa.int/realms/esa-maap/protocol/openid-connect/token",
    token_lifetime_buffer=60  # Refresh 60 seconds before expiry
)
```

#### Methods:

| Method | Description |
|--------|-------------|
| `get_token()` | Returns valid access token, auto-refreshes if needed |
| `invalidate()` | Forces refresh on next `get_token()` call |
| `_is_token_valid()` | Checks if cached token is still valid (internal) |
| `_refresh_token()` | Exchanges offline_token for new access_token (internal) |

#### Auto-refresh Logic:

```python
def get_token(self) -> str:
    if self._is_token_valid():
        return self._access_token  # Return cached token
    return self._refresh_token()   # Fetch new token

def _is_token_valid(self) -> bool:
    if self._access_token is None:
        return False
    # Refresh 60 seconds before actual expiry
    return datetime.utcnow() < (self._expires_at - timedelta(seconds=60))
```

### 4. get_auth_headers()

Returns authorization headers for requests.

```python
from maap_client.auth import get_auth_headers

headers = get_auth_headers(tm)
# Returns: {"Authorization": "Bearer eyJhbG..."}
```

### 5. authenticated_session()

Creates a pre-configured requests.Session.

```python
from maap_client.auth import authenticated_session

session = authenticated_session(tm)
response = session.get("https://catalog.maap.eo.esa.int/data/...")
```

## OAuth2 Token Exchange

When `_refresh_token()` is called, it performs this HTTP request:

```http
POST https://iam.maap.eo.esa.int/realms/esa-maap/protocol/openid-connect/token
Content-Type: application/x-www-form-urlencoded

client_id=offline-token
client_secret=<CLIENT_SECRET>
grant_type=refresh_token
refresh_token=<OFFLINE_TOKEN>
scope=offline_access openid
```

Response:
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "expires_in": 36000,
  "refresh_expires_in": 0,
  "token_type": "Bearer",
  "scope": "openid profile offline_access"
}
```

## Security Design

### Why two tokens?

| Concern | OFFLINE_TOKEN | ACCESS_TOKEN |
|---------|---------------|--------------|
| Transmission frequency | Once per 10 hours | Every API request |
| If intercepted | 90 days of access | 10 hours of access |
| Appears in logs | Rarely | Frequently |
| Risk level | High | Low |

The OFFLINE_TOKEN is transmitted only to the IAM token endpoint (HTTPS, secure). The ACCESS_TOKEN is used for all data requests. If an ACCESS_TOKEN is compromised, the attacker has limited time (10 hours) before it expires.

### Token Validation

Both tokens are JWTs (JSON Web Tokens) with embedded expiration:

```python
# Decode OFFLINE_TOKEN to see expiration
import base64, json

token_parts = offline_token.split('.')
payload = json.loads(base64.urlsafe_b64decode(token_parts[1] + '=='))
print(payload['exp'])  # Unix timestamp of expiration
```

## Usage Examples

### Basic Usage

```python
from maap_client.auth import load_credentials, TokenManager, get_auth_headers
import requests

# Setup
creds = load_credentials()
tm = TokenManager(credentials=creds)

# Make authenticated request
headers = get_auth_headers(tm)
response = requests.get(
    "https://catalog.maap.eo.esa.int/data/.../file.h5",
    headers=headers
)
```

### With MaapClient (Recommended)

```python
from maap_client import MaapClient

# MaapClient handles auth internally
client = MaapClient()
result = client.search(
    collection="EarthCAREL2Products_MAAP",
    product_type="CPR_CLD_2A",
    baseline="BA",
)
client.download(result.urls, collection="EarthCAREL2Products_MAAP")  # Auth headers added automatically
```

### Checking Token Status

```python
from maap_client.auth import load_credentials, TokenManager
from datetime import datetime
import base64, json

creds = load_credentials()

# Decode OFFLINE_TOKEN expiration
payload_b64 = creds.offline_token.split('.')[1]
payload_b64 += '=' * (4 - len(payload_b64) % 4)
payload = json.loads(base64.urlsafe_b64decode(payload_b64))

expires_at = datetime.fromtimestamp(payload['exp'])
days_left = (expires_at - datetime.now()).days

print(f"OFFLINE_TOKEN expires: {expires_at}")
print(f"Days remaining: {days_left}")

if days_left < 7:
    print("WARNING: Token expiring soon! Renew at ESA portal.")
```

## Error Handling

### CredentialsError

Raised when credentials file is missing or incomplete.

```python
try:
    creds = load_credentials()
except CredentialsError as e:
    print(f"Credentials problem: {e}")
    # Fix: Create/update credentials.txt
```

### AuthenticationError

Raised when token exchange fails.

```python
try:
    token = tm.get_token()
except AuthenticationError as e:
    print(f"Auth failed: {e}")
    # Possible causes:
    # - OFFLINE_TOKEN expired (get new one from ESA)
    # - Invalid CLIENT_SECRET
    # - Network issues
```

## Token Lifecycle Summary

| Event | Action Required |
|-------|-----------------|
| First API call | Automatic: `get_token()` fetches ACCESS_TOKEN |
| ACCESS_TOKEN expires (10h) | Automatic: `get_token()` refreshes |
| ACCESS_TOKEN near expiry (60s buffer) | Automatic: `get_token()` refreshes early |
| OFFLINE_TOKEN expires (90 days) | **MANUAL**: Login to ESA portal, get new token |
| Network error during refresh | Retry or check connectivity |
| 401 Unauthorized | Check if OFFLINE_TOKEN expired |

## File Locations

| File | Purpose |
|------|---------|
| `maap_client/auth.py` | Authentication module source |
| `maap_client/constants.py` | TOKEN_URL, DEFAULT_CREDENTIALS_FILE |
| `maap_client/exceptions.py` | AuthenticationError, CredentialsError |
| `credentials.txt` | User credentials (do not commit to git!) |

## Important Notes

1. **Never commit credentials.txt to version control**
2. The OFFLINE_TOKEN cannot be renewed programmatically - ESA requires web login
3. ACCESS_TOKEN is cached in memory only (not persisted to disk)
4. If running multiple processes, each will manage its own ACCESS_TOKEN
5. The 60-second buffer ensures tokens are refreshed before actual expiry
