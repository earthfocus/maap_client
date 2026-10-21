"""OAuth2 authentication for MAAP API."""

import base64
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import requests

from maap_client.constants import (
    DEFAULT_CREDENTIALS_FILE,
    DEFAULT_TOKEN_URL,
    TOKEN_RETRY_BACKOFF_FACTOR,
    TOKEN_RETRY_STATUSES,
    TOKEN_RETRY_TOTAL,
)
from maap_client.exceptions import AuthenticationError, AuthServiceUnavailable, CredentialsError

logger = logging.getLogger(__name__)


@dataclass
class Credentials:
    """OAuth2 credentials container."""

    client_id: str
    client_secret: str
    offline_token: str


def load_credentials(credentials_file: Optional[Path] = None) -> Credentials:
    """
    Load credentials from file.

    File format (one key=value per line):
        CLIENT_ID=...
        CLIENT_SECRET=...
        OFFLINE_TOKEN=...
    """
    if credentials_file is None:
        credentials_file = Path(DEFAULT_CREDENTIALS_FILE).expanduser()

    if not credentials_file.exists():
        raise CredentialsError(f"Credentials file not found: {credentials_file}")

    creds = {}
    with open(credentials_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            creds[key.strip()] = value.strip()

    client_id = creds.get("CLIENT_ID")
    client_secret = creds.get("CLIENT_SECRET")
    offline_token = creds.get("OFFLINE_TOKEN")

    if not all([client_id, client_secret, offline_token]):
        missing = []
        if not client_id:
            missing.append("CLIENT_ID")
        if not client_secret:
            missing.append("CLIENT_SECRET")
        if not offline_token:
            missing.append("OFFLINE_TOKEN")
        raise CredentialsError(f"Missing credentials: {', '.join(missing)}")

    return Credentials(
        client_id=client_id,
        client_secret=client_secret,
        offline_token=offline_token,
    )


def offline_token_expiry(credentials: Credentials) -> datetime:
    """When the offline token expires: the "exp" claim of its JWT payload."""
    try:
        payload = credentials.offline_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return datetime.fromtimestamp(int(claims["exp"]), timezone.utc)
    except (IndexError, ValueError, TypeError, KeyError) as e:
        raise CredentialsError(f"Cannot read the offline token expiry: {e!r}") from e


def _error_response_detail(response: Optional[requests.Response]) -> str:
    """Extract a human-readable reason from an IAM error response, if any."""
    if response is None:
        return ""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip()[:200]
    if isinstance(body, dict):
        return body.get("error_description") or body.get("error") or ""
    return ""


class TokenManager:
    """Manages OAuth2 token lifecycle with caching."""

    def __init__(
        self,
        credentials: Credentials,
        token_url: str = DEFAULT_TOKEN_URL,
        token_lifetime_buffer: int = 60,
    ):
        """
        Initialize token manager.

        Args:
            credentials: OAuth2 credentials
            token_url: Token endpoint URL
            token_lifetime_buffer: Seconds before expiry to refresh token
        """
        self._credentials = credentials
        self._token_url = token_url
        self._buffer = token_lifetime_buffer
        self._access_token: Optional[str] = None
        self._expires_at: Optional[datetime] = None

    def get_token(self) -> str:
        """Get a valid access token, refreshing if necessary."""
        if self._is_token_valid():
            return self._access_token
        return self._refresh_token()

    def _is_token_valid(self) -> bool:
        """Check if current token is still valid (with buffer)."""
        if self._access_token is None or self._expires_at is None:
            return False
        return datetime.now(timezone.utc) < (self._expires_at - timedelta(seconds=self._buffer))

    def _refresh_token(self) -> str:
        """Exchange offline token for new access token."""
        data = {
            "client_id": self._credentials.client_id,
            "client_secret": self._credentials.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self._credentials.offline_token,
            "scope": "offline_access openid",
        }

        for attempt in range(TOKEN_RETRY_TOTAL + 1):
            try:
                response = requests.post(self._token_url, data=data, timeout=30)
                response.raise_for_status()
                break
            except requests.RequestException as e:
                message = f"Failed to refresh token: {e}"
                detail = _error_response_detail(e.response)
                if detail:
                    message += f" ({detail})"
                status = e.response.status_code if e.response is not None else None
                if status is not None and status not in TOKEN_RETRY_STATUSES:
                    raise AuthenticationError(message)
                if attempt == TOKEN_RETRY_TOTAL:
                    raise AuthServiceUnavailable(message)
                delay = TOKEN_RETRY_BACKOFF_FACTOR * 2 ** attempt if attempt else 0
                logger.warning(f"Token refresh retry {attempt + 1}/{TOKEN_RETRY_TOTAL} in {delay} s: {message}")
                time.sleep(delay)

        response_json = response.json()
        access_token = response_json.get("access_token")
        expires_in = response_json.get("expires_in", 300)  # Default 5 min

        if not access_token:
            raise AuthenticationError("No access_token in IAM response")

        self._access_token = access_token
        self._expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        return self._access_token

    def invalidate(self) -> None:
        """Force token refresh on next get_token() call."""
        self._access_token = None
        self._expires_at = None


def get_auth_headers(token_manager: TokenManager) -> dict:
    """Get authorization headers for authenticated requests."""
    token = token_manager.get_token()
    return {"Authorization": f"Bearer {token}"}


def authenticated_session(token_manager: TokenManager) -> requests.Session:
    """Create a requests session with authentication headers."""
    session = requests.Session()
    session.headers.update(get_auth_headers(token_manager))
    return session
