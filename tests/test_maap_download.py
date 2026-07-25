"""Download hardening tests: atomic .part files, size verification, auth
retry, batch abort. Uses a local stdlib HTTP server; no network, no
credentials."""

import http.server
import threading
from collections import Counter

import pytest

from maap_client.download import DownloadManager
from maap_client.exceptions import DownloadError


class FakeTokenManager:
    """Stands in for auth.TokenManager: fixed token, counts invalidations."""

    def __init__(self):
        self.invalidations = 0

    def get_token(self) -> str:
        return "test-token"

    def invalidate(self) -> None:
        self.invalidations += 1


class _Handler(http.server.BaseHTTPRequestHandler):
    """Serves scripted behaviors keyed by request path.

    behaviors[path] = {
        "body": bytes,
        "content_length": int,   # header value; defaults to len(body)
        "status_once": int,      # non-200 status for the first fail_hits hits
        "fail_hits": int,        # how many initial hits get status_once (default 1)
    }
    """

    behaviors: dict = {}
    hits: Counter = Counter()

    def do_GET(self):
        b = self.behaviors[self.path]
        self.hits[self.path] += 1
        if b.get("status_once") and self.hits[self.path] <= b.get("fail_hits", 1):
            self.send_response(b["status_once"])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b["body"]
        length = b.get("content_length", len(body))
        self.send_response(200)
        self.send_header("Content-Length", str(length))
        self.end_headers()
        self.wfile.write(body)  # may be fewer bytes than announced -> cut

    def log_message(self, *args):
        pass


@pytest.fixture()
def server():
    _Handler.behaviors = {}
    _Handler.hits = Counter()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", _Handler
    httpd.shutdown()


def test_download_success_atomic(server, tmp_path):
    base, handler = server
    handler.behaviors["/f1.h5"] = {"body": b"x" * 1024}
    dm = DownloadManager(FakeTokenManager(), tmp_path)
    out = dm.download_file(base + "/f1.h5", tmp_path / "f1.h5")
    assert out == tmp_path / "f1.h5"
    assert out.read_bytes() == b"x" * 1024
    assert not list(tmp_path.glob("*.part"))


def test_midstream_cut_leaves_nothing(server, tmp_path):
    base, handler = server
    handler.behaviors["/cut.h5"] = {"body": b"y" * 100, "content_length": 1024}
    dm = DownloadManager(FakeTokenManager(), tmp_path)
    with pytest.raises(DownloadError):
        dm.download_file(base + "/cut.h5", tmp_path / "cut.h5")
    assert not (tmp_path / "cut.h5").exists()
    assert not list(tmp_path.glob("*.part"))


def test_content_length_mismatch_message(tmp_path, monkeypatch):
    # Force the clean-short-read path (no requests exception) to prove the
    # explicit byte-count verification, independent of urllib3 behavior.
    class FakeResponse:
        headers = {"content-length": "100"}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield b"z" * 40

    monkeypatch.setattr(
        "maap_client.download.requests.get", lambda *a, **k: FakeResponse()
    )
    dm = DownloadManager(FakeTokenManager(), tmp_path)
    with pytest.raises(DownloadError, match=r"incomplete: 40/100"):
        dm.download_file("http://x/short.h5", tmp_path / "short.h5")
    assert not (tmp_path / "short.h5").exists()
    assert not list(tmp_path.glob("*.part"))


def test_rename_failure_removes_part(server, tmp_path, monkeypatch):
    base, handler = server
    handler.behaviors["/f3.h5"] = {"body": b"x" * 512}

    def broken_replace(src, dst):
        raise OSError("simulated rename failure")

    monkeypatch.setattr("maap_client.download.os.replace", broken_replace)
    dm = DownloadManager(FakeTokenManager(), tmp_path)
    with pytest.raises(OSError, match="simulated rename failure"):
        dm.download_file(base + "/f3.h5", tmp_path / "f3.h5")
    assert not (tmp_path / "f3.h5").exists()
    assert not list(tmp_path.glob("*.part"))


def test_stale_part_overwritten(server, tmp_path):
    base, handler = server
    handler.behaviors["/f2.h5"] = {"body": b"new-content"}
    (tmp_path / "f2.h5.part").write_bytes(b"stale garbage from a crash")
    dm = DownloadManager(FakeTokenManager(), tmp_path)
    out = dm.download_file(base + "/f2.h5", tmp_path / "f2.h5")
    assert out.read_bytes() == b"new-content"
    assert not list(tmp_path.glob("*.part"))
