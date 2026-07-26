"""sync() must forward max_consecutive_failures and re-raise fatal errors."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from maap_client.client import MaapClient
from maap_client.exceptions import (
    AuthenticationError,
    BatchDownloadAborted,
    CredentialsError,
    DownloadError,
)

URL = "http://x/ECA_TEST_20250101T000000Z_A.h5"
START = datetime(2025, 1, 1, tzinfo=timezone.utc)
END = datetime(2025, 1, 2, tzinfo=timezone.utc)


def _make_client(downloader):
    """MaapClient with search/tracker/downloader mocked out (no credentials)."""
    client = MaapClient.__new__(MaapClient)
    client._config = Mock()
    client._searcher = Mock()
    client._searcher.search_urls_iter_day.return_value = [[URL]]
    tracker = Mock()
    tracker.get_pending_downloads.return_value = {URL}
    client.get_tracker = Mock(return_value=tracker)
    client._get_downloader = Mock(return_value=downloader)
    return client


def _sync(client, **kwargs):
    return client.sync("COLL", "TEST_PROD", baseline="AA",
                       start=START, end=END, **kwargs)


def test_sync_forwards_max_consecutive_failures():
    downloader = Mock()
    downloader.batch_download.return_value = {}
    client = _make_client(downloader)
    _sync(client, max_consecutive_failures=7)
    assert downloader.batch_download.call_args.kwargs["max_consecutive_failures"] == 7


def test_sync_default_forwards_none():
    downloader = Mock()
    downloader.batch_download.return_value = {}
    client = _make_client(downloader)
    _sync(client)
    assert downloader.batch_download.call_args.kwargs["max_consecutive_failures"] is None


@pytest.mark.parametrize("exc", [
    AuthenticationError("token refresh dead"),
    CredentialsError("no credentials"),
    BatchDownloadAborted(0, 3, DownloadError("u", "504", 504)),
])
def test_sync_propagates_fatal_and_abort(exc):
    downloader = Mock()
    downloader.batch_download.side_effect = exc
    client = _make_client(downloader)
    with pytest.raises(type(exc)):
        _sync(client)


def test_sync_still_swallows_generic_errors():
    downloader = Mock()
    downloader.batch_download.side_effect = RuntimeError("boom")
    client = _make_client(downloader)
    result = _sync(client)
    assert result.errors and "boom" in result.errors[0]
