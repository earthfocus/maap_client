"""Custom exceptions for MAAP client."""


class MaapError(Exception):
    """Base exception for MAAP client."""

    pass


class AuthenticationError(MaapError):
    """Failed to authenticate with MAAP IAM."""

    pass


class CredentialsError(MaapError):
    """Missing or invalid credentials."""

    pass


class CatalogError(MaapError):
    """Error fetching or parsing catalog."""

    pass


class DownloadError(MaapError):
    """Error downloading file."""

    def __init__(self, url: str, message: str, status_code: int | None = None):
        self.url = url
        self.status_code = status_code
        super().__init__(f"Download failed for {url}: {message}")


class InvalidRequestError(MaapError):
    """Raised when request parameters are invalid or conflicting.

    Examples:
        - Using orbit with start/end time
        - start > end
        - Naive (non-timezone-aware) datetime
    """

    pass
