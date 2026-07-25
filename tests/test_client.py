"""Tests for MaapClient._resolve_orbit_frames."""

import pytest

from maap_client.client import MaapClient
from maap_client.exceptions import InvalidRequestError


def test_no_orbit_passes_frames_through():
    assert MaapClient._resolve_orbit_frames(None, ["C", "D"]) == (None, ["C", "D"])


def test_orbit_with_letter_becomes_orbit_plus_single_frame():
    assert MaapClient._resolve_orbit_frames("01525E", None) == (1525, ["E"])


def test_orbit_without_letter_keeps_frames():
    assert MaapClient._resolve_orbit_frames("1525", ["C", "D"]) == (1525, ["C", "D"])


def test_orbit_without_letter_and_no_frames():
    assert MaapClient._resolve_orbit_frames("1525", None) == (1525, None)


def test_orbit_with_letter_plus_frames_conflicts():
    with pytest.raises(InvalidRequestError, match="already includes a frame letter"):
        MaapClient._resolve_orbit_frames("01525E", ["A"])


def test_invalid_orbit_raises_invalid_request():
    with pytest.raises(InvalidRequestError, match="invalid orbit"):
        MaapClient._resolve_orbit_frames("bad", None)
