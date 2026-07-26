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


class BatchDownloadAborted(MaapError):
    """Batch download aborted after too many consecutive failures.

    Raised by DownloadManager.batch_download when max_consecutive_failures
    is set and reached. Progress made before the abort is already persisted
    via the on_download callback.
    """

    def __init__(self, downloaded: int, failed: int, last_error: "DownloadError"):
        self.downloaded = downloaded
        self.failed = failed
        self.last_error = last_error
        super().__init__(
            f"Batch aborted after {failed} consecutive failures "
            f"({downloaded} downloaded); last: {last_error}"
        )


# CLI exit-code taxonomy, consumed by wrapper scripts to apply retry policy.
EXIT_OK = 0
EXIT_AUTH_FATAL = 2       # token refresh dead, persistent 401/403 - global stop
EXIT_TRANSIENT = 3        # 5xx/timeouts/connection/partial result - retry later
EXIT_NON_TRANSIENT = 4    # 400 / invalid request - retrying will not help


def _http_status_from_chain(exc: BaseException) -> int | None:
    """First HTTP status code found walking exc and its __cause__/__context__."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        response = getattr(current, "response", None)
        status = getattr(response, "status_code", None)
        if status is not None:
            return status
        current = current.__cause__ or current.__context__
    return None


def classify_exit_code(exc: BaseException) -> int:
    """Map an exception to the CLI exit-code taxonomy."""
    if isinstance(exc, (AuthenticationError, CredentialsError)):
        return EXIT_AUTH_FATAL
    if isinstance(exc, BatchDownloadAborted):
        last = exc.last_error
        if isinstance(last, DownloadError) and last.status_code in (401, 403):
            return EXIT_AUTH_FATAL
        return EXIT_TRANSIENT
    if isinstance(exc, DownloadError):
        if exc.status_code in (401, 403):
            return EXIT_AUTH_FATAL
        if exc.status_code == 400:
            return EXIT_NON_TRANSIENT
        return EXIT_TRANSIENT
    if isinstance(exc, InvalidRequestError):
        return EXIT_NON_TRANSIENT
    status = _http_status_from_chain(exc)
    if status == 400:
        return EXIT_NON_TRANSIENT
    if status in (401, 403):
        return EXIT_AUTH_FATAL
    return EXIT_TRANSIENT
