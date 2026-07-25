"""MaapSearcher opens the STAC client with transport-level retries."""

from maap_client.constants import (
    STAC_RETRY_BACKOFF_FACTOR,
    STAC_RETRY_STATUS_FORCELIST,
    STAC_RETRY_TOTAL,
)
from maap_client.search import MaapSearcher


def test_stac_client_opened_with_retry(monkeypatch):
    captured = {}

    class FakeStacApiIO:
        def __init__(self, max_retries=None):
            captured["retry"] = max_retries

    monkeypatch.setattr("maap_client.search.StacApiIO", FakeStacApiIO)
    monkeypatch.setattr(
        "maap_client.search.Client.open",
        staticmethod(lambda url, stac_io=None: object()),
    )

    searcher = MaapSearcher()
    _ = searcher.client  # trigger lazy open

    retry = captured["retry"]
    assert retry is not None, "Client.open must receive a StacApiIO with max_retries"
    assert retry.total == STAC_RETRY_TOTAL
    assert retry.backoff_factor == STAC_RETRY_BACKOFF_FACTOR
    assert set(STAC_RETRY_STATUS_FORCELIST) <= set(retry.status_forcelist)
    assert {"GET", "POST"} <= set(retry.allowed_methods)
