"""Download hardening tests: atomic .part files, size verification, auth
retry, batch abort. Uses a local stdlib HTTP server; no network, no
credentials."""

import http.server
import threading
from collections import Counter

import pytest

from maap_client.download import DownloadManager
from maap_client.exceptions import BatchDownloadAborted, DownloadError
from maap_client.paths import extract_sensing_time, generate_data_path


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


def test_403_then_success_refreshes_once(server, tmp_path):
    base, handler = server
    handler.behaviors["/auth.h5"] = {"body": b"ok", "status_once": 403, "fail_hits": 1}
    tm = FakeTokenManager()
    dm = DownloadManager(tm, tmp_path)
    out = dm.download_file(base + "/auth.h5", tmp_path / "auth.h5")
    assert out.read_bytes() == b"ok"
    assert tm.invalidations == 1
    assert handler.hits["/auth.h5"] == 2


def test_persistent_403_raises_after_one_retry(server, tmp_path):
    base, handler = server
    handler.behaviors["/deny.h5"] = {"body": b"no", "status_once": 403, "fail_hits": 99}
    tm = FakeTokenManager()
    dm = DownloadManager(tm, tmp_path)
    with pytest.raises(DownloadError) as exc_info:
        dm.download_file(base + "/deny.h5", tmp_path / "deny.h5")
    assert exc_info.value.status_code == 403
    assert tm.invalidations == 1          # exactly one refresh attempt
    assert handler.hits["/deny.h5"] == 2  # exactly one retry
    assert not (tmp_path / "deny.h5").exists()
    assert not list(tmp_path.glob("*.part"))


def _batch_urls(base, handler, n_failing, behavior):
    """Register n_failing failing granule URLs (distinct sensing days)."""
    urls = []
    for i in range(1, n_failing + 1):
        path = f"/ECA_TEST_2025010{i}T000000Z_A.h5"
        handler.behaviors[path] = dict(behavior)
        urls.append(base + path)
    return urls


def test_batch_aborts_after_consecutive_failures(server, tmp_path):
    base, handler = server
    ok_path = "/ECA_TEST_20250109T000000Z_A.h5"
    handler.behaviors[ok_path] = {"body": b"ok"}
    fail_urls = _batch_urls(
        base, handler, 4, {"body": b"no", "status_once": 500, "fail_hits": 99}
    )
    urls = [base + ok_path] + fail_urls
    marked = []
    dm = DownloadManager(FakeTokenManager(), tmp_path)
    with pytest.raises(BatchDownloadAborted) as exc_info:
        dm.batch_download(
            urls, "COLL", "TEST_PROD", "AA",
            on_download=lambda url, p: marked.append((url, p)),
            max_consecutive_failures=3,
        )
    assert exc_info.value.downloaded == 1
    assert exc_info.value.failed == 3
    assert isinstance(exc_info.value.last_error, DownloadError)
    assert len(marked) == 1                      # earlier success still marked
    assert marked[0][1].exists()
    fourth = fail_urls[3].replace(base, "")
    assert handler.hits[fourth] == 0             # abort stopped the churn


def test_batch_default_none_keeps_current_behavior(server, tmp_path):
    base, handler = server
    fail_urls = _batch_urls(
        base, handler, 4, {"body": b"no", "status_once": 500, "fail_hits": 99}
    )
    dm = DownloadManager(FakeTokenManager(), tmp_path)
    results = dm.batch_download(fail_urls, "COLL", "TEST_PROD", "AA")
    assert results == {}                         # no raise, all attempted
    for url in fail_urls:
        assert handler.hits[url.replace(base, "")] == 1


def test_on_download_only_fires_for_complete_files(server, tmp_path):
    base, handler = server
    ok = "/ECA_TEST_20250101T000000Z_A.h5"
    cut = "/ECA_TEST_20250102T000000Z_A.h5"
    handler.behaviors[ok] = {"body": b"data"}
    handler.behaviors[cut] = {"body": b"d", "content_length": 999}
    seen = []

    def record(url, path):
        # Registry invariant: only final, complete files are ever marked
        assert path.exists()
        assert path.suffix != ".part"
        seen.append(url)

    dm = DownloadManager(FakeTokenManager(), tmp_path)
    dm.batch_download([base + ok, base + cut], "COLL", "TEST_PROD", "AA",
                      on_download=record)
    assert seen == [base + ok]


def test_dedup_glob_ignores_part_files(server, tmp_path):
    filename = "ECA_EXAA_AUX_MET_1D_20250101T000000Z_20250101T000000Z_00123A.h5"
    base, handler = server
    handler.behaviors["/" + filename] = {"body": b"met-data"}
    dt = extract_sensing_time(filename)
    final = generate_data_path(
        data_dir=tmp_path, mission="EarthCARE", collection="COLL",
        product_type="AUX_MET_1D", baseline="AA", dt=dt, filename=filename,
    )
    final.parent.mkdir(parents=True, exist_ok=True)
    (final.parent / (filename + ".part")).write_bytes(b"stale")
    dm = DownloadManager(FakeTokenManager(), tmp_path)
    results = dm.batch_download([base + "/" + filename], "COLL", "AUX_MET_1D", "AA")
    # Without the fix the stale .part matches the dedup glob and the granule
    # is "skipped" with the .part path marked as downloaded.
    assert results[base + "/" + filename] == final
    assert final.read_bytes() == b"met-data"
    assert not list(final.parent.glob("*.part"))
