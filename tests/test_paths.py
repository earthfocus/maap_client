"""Tests for filter_by_orbit_frame."""

from maap_client.paths import filter_by_orbit_frame

EC_C = "https://x/ECA_EXBA_CPR_NOM_1B_20250908T232505Z_20250909T010458Z_07282C.h5"
EC_E = "https://x/ECA_EXBA_CPR_NOM_1B_20250908T235005Z_20250909T010458Z_07282E.h5"
EC_OTHER_ORBIT = "https://x/ECA_EXBA_CPR_NOM_1B_20250909T012505Z_20250909T030458Z_07283C.h5"
AEOLUS = "https://x/AE_OPER_ALD_U_N_1B_20230422T165721033_005543989_027018_0001.DBL"
NO_ORBIT = "https://x/SOME_FILE_WITHOUT_ORBIT.h5"

ALL = [EC_C, EC_E, EC_OTHER_ORBIT, AEOLUS, NO_ORBIT]


def test_no_filters_returns_input_unchanged():
    assert filter_by_orbit_frame(ALL) == ALL


def test_filter_by_frames_only():
    assert filter_by_orbit_frame(ALL, frames=["C"]) == [EC_C, EC_OTHER_ORBIT]


def test_filter_by_orbit_only():
    assert filter_by_orbit_frame(ALL, orbit=7282) == [EC_C, EC_E]


def test_filter_by_orbit_and_frames():
    assert filter_by_orbit_frame(ALL, orbit=7282, frames=["C", "D"]) == [EC_C]


def test_aeolus_orbit_without_frame_matches_orbit_filter():
    assert filter_by_orbit_frame(ALL, orbit=27018) == [AEOLUS]


def test_aeolus_dropped_by_frame_filter():
    # Aeolus has no frame letter; a frame filter cannot match it
    assert filter_by_orbit_frame([AEOLUS], frames=["C"]) == []


def test_items_without_extractable_orbit_are_dropped():
    assert filter_by_orbit_frame([NO_ORBIT], orbit=7282) == []
