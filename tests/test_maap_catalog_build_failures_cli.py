"""build_catalog aggregates manager failures; CLI exits non-zero on any."""

import argparse
from pathlib import Path
from types import SimpleNamespace

from maap_client import cli_commands
from maap_client.catalog_build import CatalogCollection
from maap_client.client import MaapClient


class StubManager:
    """Stands in for CatalogCollectionManager inside build_catalog."""

    failures = [("PROD_A", "AB", "502 Bad Gateway")]

    def __init__(self, client=None, catalog_dir=None):
        self.last_failures = []
        self._dir = Path(catalog_dir)

    def build(self, collection, **kwargs):
        self.last_failures = list(self.failures)
        return CatalogCollection(collection=collection)

    def save(self, catalog):
        return self._dir / f"{catalog.collection}_collection.json"


def bare_client(tmp_path):
    client = MaapClient.__new__(MaapClient)  # skip config/auth loading
    client._config = SimpleNamespace(built_catalog_dir=tmp_path)
    return client


def test_build_catalog_collects_failures(monkeypatch, tmp_path):
    monkeypatch.setattr("maap_client.client.CatalogCollectionManager", StubManager)
    failures = []

    results = bare_client(tmp_path).build_catalog(
        collection="COLL", failures_out=failures
    )

    assert "COLL" in results
    assert failures == [("COLL", "PROD_A", "AB", "502 Bad Gateway")]


def test_build_catalog_records_whole_collection_error(monkeypatch, tmp_path):
    class BoomManager(StubManager):
        def build(self, collection, **kwargs):
            raise RuntimeError("nginx melted")

    monkeypatch.setattr("maap_client.client.CatalogCollectionManager", BoomManager)
    failures = []

    results = bare_client(tmp_path).build_catalog(
        collection="COLL", failures_out=failures
    )

    assert results == {}
    assert failures == [("COLL", "*", "*", "nginx melted")]


def cli_args(**overrides):
    base = dict(
        collection="COLL", product=None, baseline=None,
        latest_baseline=False, force=False, out_dir=None, verbose=0,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def run_cmd(monkeypatch, fake_client):
    monkeypatch.setattr(cli_commands, "get_client", lambda args: fake_client)
    monkeypatch.setattr(cli_commands, "validate_time_args", lambda args: None)
    monkeypatch.setattr(cli_commands, "resolve_date_args", lambda args: (None, None))
    return cli_commands.cmd_catalog_build(cli_args())


def test_cli_exits_1_and_prints_failures(monkeypatch, capsys):
    class FakeClient:
        def build_catalog(self, failures_out=None, **kwargs):
            failures_out.append(("COLL", "PROD_A", "AB", "502 Bad Gateway"))
            return {"COLL": Path("/x/COLL_collection.json")}

    assert run_cmd(monkeypatch, FakeClient()) == 1
    err = capsys.readouterr().err
    assert "COLL/PROD_A/AB" in err
    assert "502 Bad Gateway" in err


def test_cli_exits_0_when_clean(monkeypatch, capsys):
    class FakeClient:
        def build_catalog(self, failures_out=None, **kwargs):
            return {"COLL": Path("/x/COLL_collection.json")}

    assert run_cmd(monkeypatch, FakeClient()) == 0
