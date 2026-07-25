"""Tests for parse_frames and parse_orbit."""

import pytest

from maap_client.utils import parse_frames, parse_orbit


class TestParseFrames:
    def test_single_frame(self):
        assert parse_frames("A") == ["A"]

    def test_multiple_frames_lowercase_and_spaces(self):
        assert parse_frames(" c, d ,E") == ["C", "D", "E"]

    def test_duplicates_removed_order_kept(self):
        assert parse_frames("E,C,E") == ["E", "C"]

    def test_invalid_letter_rejected(self):
        with pytest.raises(ValueError, match="must be letters A-H"):
            parse_frames("A,X")

    def test_multichar_entry_rejected(self):
        with pytest.raises(ValueError, match="must be letters A-H"):
            parse_frames("AB")

    def test_empty_string_rejected(self):
        with pytest.raises(ValueError):
            parse_frames("")


class TestParseOrbit:
    def test_orbit_with_frame(self):
        assert parse_orbit("01525E") == (1525, "E")

    def test_orbit_with_lowercase_frame(self):
        assert parse_orbit("1525e") == (1525, "E")

    def test_orbit_without_frame(self):
        assert parse_orbit("1525") == (1525, None)

    def test_aeolus_six_digit_orbit(self):
        assert parse_orbit("027018") == (27018, None)

    def test_invalid_frame_letter(self):
        with pytest.raises(ValueError, match="must be A-H"):
            parse_orbit("1525Z")

    def test_non_numeric_rejected(self):
        with pytest.raises(ValueError, match="invalid orbit"):
            parse_orbit("15a25E")

    def test_empty_rejected(self):
        with pytest.raises(ValueError, match="invalid orbit"):
            parse_orbit("")
