"""Tests for MaapSearcher._build_filter."""

from maap_client.search import MaapSearcher


def test_product_only():
    assert MaapSearcher._build_filter("CPR_NOM_1B") == "productType = 'CPR_NOM_1B'"


def test_product_and_baseline():
    assert MaapSearcher._build_filter("CPR_NOM_1B", baseline="DA") == (
        "productType = 'CPR_NOM_1B' AND productVersion = 'DA'"
    )


def test_orbit_without_frames():
    assert MaapSearcher._build_filter("CPR_NOM_1B", orbit=1525) == (
        "productType = 'CPR_NOM_1B' AND orbitNumber = 1525"
    )


def test_single_frame_uses_equality():
    assert MaapSearcher._build_filter("CPR_NOM_1B", frames=["A"]) == (
        "productType = 'CPR_NOM_1B' AND frame = 'A'"
    )


def test_multiple_frames_use_in_clause():
    assert MaapSearcher._build_filter("CPR_NOM_1B", frames=["C", "D", "E"]) == (
        "productType = 'CPR_NOM_1B' AND frame IN ('C', 'D', 'E')"
    )


def test_all_parts_combined():
    assert MaapSearcher._build_filter("CPR_NOM_1B", baseline="DA", orbit=1525, frames=["C", "D"]) == (
        "productType = 'CPR_NOM_1B' AND productVersion = 'DA' "
        "AND orbitNumber = 1525 AND frame IN ('C', 'D')"
    )
