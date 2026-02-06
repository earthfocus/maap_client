# Exceptions Module Documentation

This document describes the custom exceptions defined in `maap_client/exceptions.py`.

## Overview

The `exceptions.py` module defines a hierarchy of custom exceptions for the MAAP client. All exceptions inherit from `MaapError`, enabling catch-all error handling while allowing specific exception types when needed.

## Exception Hierarchy

```
Exception (built-in)
└── MaapError (base for all MAAP exceptions)
    ├── AuthenticationError    # OAuth2 token failures
    ├── CredentialsError       # Missing/invalid credentials file
    ├── CatalogError           # Catalog API errors
    ├── DownloadError          # File download failures
    └── InvalidRequestError    # Invalid request parameters
```

## Exception Reference

### MaapError

Base exception for all MAAP client errors.

```python
class MaapError(Exception):
    """Base exception for MAAP client."""
    pass
```

**Use case**: Catch-all for any MAAP-related error.

```python
from maap_client import MaapClient
from maap_client.exceptions import MaapError

try:
    client = MaapClient()
    result = client.search(...)
    client.download(result.urls, ...)
except MaapError as e:
    print(f"MAAP operation failed: {e}")
```

### AuthenticationError

Raised when OAuth2 token exchange fails.

```python
class AuthenticationError(MaapError):
    """Failed to authenticate with MAAP IAM."""
    pass
```

**Common causes**:
- Expired OFFLINE_TOKEN (90-day token)
- Invalid CLIENT_SECRET
- Network connectivity issues
- IAM server unavailable

```python
from maap_client.exceptions import AuthenticationError

try:
    result = client.download(urls, collection="...")
except AuthenticationError as e:
    print("Token expired! Renew at: https://portal.maap.eo.esa.int/...")
```

### CredentialsError

Raised when credentials file is missing or invalid.

```python
class CredentialsError(MaapError):
    """Missing or invalid credentials."""
    pass
```

**Common causes**:
- `credentials.txt` file not found
- Missing required fields (CLIENT_ID, CLIENT_SECRET, OFFLINE_TOKEN)
- Malformed credentials file

```python
from maap_client.exceptions import CredentialsError

try:
    result = client.download(urls, collection="...")
except CredentialsError as e:
    print(f"Setup credentials first: {e}")
    print("Create ~/.maap/credentials.txt with:")
    print("  CLIENT_ID=offline-token")
    print("  CLIENT_SECRET=...")
    print("  OFFLINE_TOKEN=...")
```

### CatalogError

Raised when catalog operations fail.

```python
class CatalogError(MaapError):
    """Error fetching or parsing catalog."""
    pass
```

**Common causes**:
- Invalid collection name
- Catalog API unavailable
- Malformed queryables response

```python
from maap_client.exceptions import CatalogError

try:
    products = client.list_products("InvalidCollection")
except CatalogError as e:
    print(f"Catalog error: {e}")
```

### DownloadError

Raised when file download fails. Includes additional context.

```python
class DownloadError(MaapError):
    """Error downloading file."""

    def __init__(self, url: str, message: str, status_code: int | None = None):
        self.url = url
        self.status_code = status_code
        super().__init__(f"Download failed for {url}: {message}")
```

**Attributes**:
- `url`: The URL that failed to download
- `status_code`: HTTP status code (if available)
- `message`: Error description

**Common causes**:
- HTTP 401: Authentication failed
- HTTP 403: Access denied
- HTTP 404: File not found
- HTTP 5xx: Server errors
- Network timeout

```python
from maap_client.exceptions import DownloadError

try:
    result = client.download(urls, collection="...")
except DownloadError as e:
    print(f"Download failed: {e}")
    print(f"  URL: {e.url}")
    print(f"  Status: {e.status_code}")

    if e.status_code == 401:
        print("  -> Check your credentials")
    elif e.status_code == 404:
        print("  -> File may have been removed")
```

### InvalidRequestError

Raised when request parameters are invalid or conflicting.

```python
class InvalidRequestError(MaapError):
    """Raised when request parameters are invalid or conflicting.

    Examples:
        - Using orbit with start/end time
        - start > end
        - Naive (non-timezone-aware) datetime
    """
    pass
```

**Common causes**:
- Using `orbit` with `start`/`end` time (mutually exclusive)
- `start` datetime is after `end`
- Passing naive datetime (without timezone info)

```python
from datetime import datetime, timezone
from maap_client.exceptions import InvalidRequestError

try:
    # This will raise InvalidRequestError - naive datetime
    result = client.search(
        collection="EarthCAREL2Validated_MAAP",
        product_type="CPR_CLD_2A",
        start=datetime(2024, 12, 1),  # Missing tzinfo!
    )
except InvalidRequestError as e:
    print(f"Invalid request: {e}")
    # Fix: use timezone-aware datetime
    result = client.search(
        collection="EarthCAREL2Validated_MAAP",
        product_type="CPR_CLD_2A",
        start=datetime(2024, 12, 1, tzinfo=timezone.utc),
    )
```

## Error Handling Patterns

### Specific Handling

```python
from maap_client import MaapClient
from maap_client.exceptions import (
    InvalidRequestError,
    CredentialsError,
    AuthenticationError,
    DownloadError,
)

client = MaapClient()

try:
    result = client.download(urls, collection="EarthCAREL2Validated_MAAP")
except InvalidRequestError as e:
    print(f"Invalid parameters: {e}")
except CredentialsError:
    print("No credentials file found")
except AuthenticationError:
    print("Token expired - renew at ESA portal")
except DownloadError as e:
    if e.status_code == 404:
        print("File not found - may have been removed")
    else:
        print(f"Download failed: {e}")
```

### Catch-All

```python
from maap_client.exceptions import MaapError

try:
    # Multiple MAAP operations
    client = MaapClient()
    result = client.search(...)
    client.download(result.urls, ...)
except MaapError as e:
    # Handle any MAAP error
    logger.error(f"MAAP error: {e}")
    raise
```

### Retry Pattern

```python
from maap_client.exceptions import DownloadError, AuthenticationError
import time

def download_with_retry(client, urls, collection, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.download(urls, collection=collection)
        except DownloadError as e:
            if e.status_code in (500, 502, 503, 504):
                # Server error - retry
                time.sleep(2 ** attempt)
                continue
            raise  # Other errors - don't retry
        except AuthenticationError:
            # Token may have expired mid-batch
            client._token_manager = None  # Force re-auth
            continue
    raise DownloadError("batch", "Max retries exceeded")
```

## Exception Usage by Module

| Module | Raises |
|--------|--------|
| `auth.py` | `CredentialsError`, `AuthenticationError` |
| `catalog_query.py` | `CatalogError` |
| `download.py` | `DownloadError` |
| `client.py` | `InvalidRequestError` |
| `cli.py` | - (catches `MaapError`) |
| `cli_commands.py` | - (catches `MaapError`) |

## Design Decisions

### Why a Custom Exception Hierarchy?

1. **Specificity**: Users can catch exactly what they care about
2. **Context**: Exceptions carry relevant information (e.g., URL, status code)
3. **Catch-all**: `MaapError` enables blanket handling when needed
4. **Separation**: MAAP errors distinct from Python built-in errors

### Why Not Use Standard Exceptions?

1. **Clarity**: `DownloadError` is clearer than `requests.HTTPError`
2. **Encapsulation**: Internal library details hidden from users
3. **Extension**: Can add attributes like `url`, `status_code`
4. **Consistency**: All MAAP errors have same base class

## File Location

| File | Purpose |
|------|---------|
| `maap_client/exceptions.py` | This module |
