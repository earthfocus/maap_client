"""Tests for CLI parsing and validation of --frame/--orbit."""

import argparse

import pytest

from maap_client.cli import build_parser
from maap_client.cli_helpers import validate_time_args, validate_download_filter_args


def parse(argv):
    return build_parser().parse_args(argv)


class TestParser:
    def test_search_frame_option(self):
        args = parse(["search", "Coll", "PROD", "--frame", "c,d"])
        assert args.frame == ["C", "D"]

    def test_search_orbit_without_letter_accepted(self):
        args = parse(["search", "Coll", "PROD", "--orbit", "1525"])
        assert args.orbit == "1525"

    def test_get_frame_option(self):
        args = parse(["get", "Coll", "PROD", "--frame", "A"])
        assert args.frame == ["A"]

    def test_sync_frame_option(self):
        args = parse(["sync", "Coll", "PROD", "--frame", "A,B"])
        assert args.frame == ["A", "B"]

    def test_sync_has_no_orbit_option(self):
        with pytest.raises(SystemExit):
            parse(["sync", "Coll", "PROD", "--orbit", "1525"])

    def test_download_frame_and_orbit_options(self):
        args = parse(["download", "Coll", "PROD", "--registry", "--frame", "C", "--orbit", "1525"])
        assert args.frame == ["C"]
        assert args.orbit == "1525"

    def test_invalid_frame_letter_exits(self):
        with pytest.raises(SystemExit):
            parse(["search", "Coll", "PROD", "--frame", "X"])


def ns(**kwargs):
    defaults = dict(date=None, start=None, end=None, days_back=None, orbit=None, frame=None)
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestValidateTimeArgs:
    def test_frame_with_time_range_ok(self):
        assert validate_time_args(ns(start="2024-12-01", frame=["A"])) is None

    def test_frame_with_frameless_orbit_ok(self):
        assert validate_time_args(ns(orbit="1525", frame=["A"])) is None

    def test_frame_with_lettered_orbit_conflicts(self):
        error = validate_time_args(ns(orbit="01525E", frame=["A"]))
        assert "already includes a frame letter" in error

    def test_malformed_orbit_reported(self):
        error = validate_time_args(ns(orbit="bad"))
        assert "invalid orbit" in error

    def test_orbit_with_start_still_rejected(self):
        error = validate_time_args(ns(orbit="1525", start="2024-12-01"))
        assert "--orbit cannot be used with --start" in error


class TestValidateDownloadFilterArgs:
    def test_frame_without_registry_rejected(self):
        args = ns(frame=["C"])
        args.registry = False
        assert "--frame requires --registry" in validate_download_filter_args(args)

    def test_orbit_without_registry_rejected(self):
        args = ns(orbit="1525")
        args.registry = False
        assert "--orbit requires --registry" in validate_download_filter_args(args)

    def test_with_registry_ok(self):
        args = ns(frame=["C"], orbit="1525")
        args.registry = True
        assert validate_download_filter_args(args) is None
