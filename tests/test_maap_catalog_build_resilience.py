"""CatalogCollectionManager.build(): checkpoint saves + continue-and-report."""

import json
from datetime import datetime, timezone

import pytest

from maap_client.catalog_build import BaselineInfo, CatalogCollectionManager

MISSION_START = datetime(2024, 5, 28, 0, 0, 0, tzinfo=timezone.utc)
DEFAULT_NOW = datetime(2026, 7, 25, 0, 0, 0, tzinfo=timezone.utc)


class Interrupt(BaseException):
    """Not an Exception: must always abort the build (like KeyboardInterrupt)."""


class FakeSearcher:
    def search_has_any_product(self, collection, product, baseline, start, end):
        return True


class FakeMaapClient:
    """The slice of MaapClient that CatalogCollectionManager.build() consumes."""

    def __init__(self, baselines, fail=None, fail_exc=None, now_end=DEFAULT_NOW):
        self._baselines = list(baselines)
        self._fail = fail                  # baseline name whose fetch raises
        self._fail_exc = fail_exc or RuntimeError("502 Bad Gateway")
        self.now_end = now_end
        self.searcher = FakeSearcher()
        self.info_calls = []               # (baseline, f_start, f_end)

    def list_products(self, collection, from_built=False, verify=False):
        return ["PROD_A"]

    def list_baselines(self, collection, product, from_built=False, verify=False):
        return list(self._baselines)

    def normalize_time_range(self, start, end):
        return (start or MISSION_START, end or self.now_end)

    def get_baseline_info(self, collection, product, baseline,
                          f_start, f_end, from_built=False):
        self.info_calls.append((baseline, f_start, f_end))
        if baseline == self._fail:
            raise self._fail_exc
        return BaselineInfo(
            time_start=f_start, time_end=f_end,
            frame_start="00001A", frame_end="00002B", count=10,
        )


def saved_baselines(tmp_path, collection="COLL"):
    path = tmp_path / f"{collection}_collection.json"
    assert path.exists(), "catalog JSON was never written"
    data = json.loads(path.read_text())
    return set(data["products"]["PROD_A"]["baselines"].keys())


def test_checkpoint_survives_hard_abort(tmp_path):
    fake = FakeMaapClient(baselines=["AA", "AB"], fail="AB", fail_exc=Interrupt())
    manager = CatalogCollectionManager(client=fake, catalog_dir=tmp_path)

    with pytest.raises(Interrupt):
        manager.build(collection="COLL")

    assert saved_baselines(tmp_path) == {"AA"}
