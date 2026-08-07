"""Tests for `rostree diff`."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from unittest import mock

from rostree.cli import cmd_diff
from tests.conftest import write_package

EMPTY_ENV = {
    "AMENT_PREFIX_PATH": "",
    "COLCON_PREFIX_PATH": "",
    "ROS2_WORKSPACE": "",
    "COLCON_WORKSPACE": "",
}


def args(tmp_path: Path, **overrides) -> argparse.Namespace:
    base = dict(
        package="app_a",
        other=None,
        save=None,
        against=None,
        depth=None,
        runtime=False,
        dep_type=None,
        source=[str(tmp_path)],
        include=None,
        exclude=None,
        only_workspace=False,
        json=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def two_apps(root: Path) -> None:
    """app_a and app_b share `common`; each has one dependency of its own."""
    write_package(root, "common", version="1.0.0")
    write_package(root, "only_a", version="2.0.0")
    write_package(root, "only_b", version="3.0.0")
    write_package(root, "app_a", depends=["common", "only_a"])
    write_package(root, "app_b", depends=["common", "only_b"])


class TestComparingTwoPackages:
    """`rostree diff a b`."""

    def test_reports_added_and_removed(self, tmp_path: Path, capsys) -> None:
        two_apps(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_diff(args(tmp_path, package="app_a", other="app_b"))
        out = capsys.readouterr().out
        assert result == 1  # a difference is "drift", for CI
        assert "only_a" in out
        assert "only_b" in out
        assert "common" not in out  # shared, so not reported

    def test_identical_packages_report_no_difference(self, tmp_path: Path, capsys) -> None:
        write_package(tmp_path, "leaf")
        write_package(tmp_path, "app_a", depends=["leaf"])
        write_package(tmp_path, "app_b", depends=["leaf"])
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_diff(args(tmp_path, package="app_a", other="app_b"))
        assert result == 0
        assert "No difference" in capsys.readouterr().out

    def test_unknown_package_is_reported(self, tmp_path: Path, capsys) -> None:
        two_apps(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_diff(args(tmp_path, package="nope", other="app_b"))
        assert result == 1
        assert "Package not found" in capsys.readouterr().err

    def test_unknown_comparison_target_is_reported(self, tmp_path: Path, capsys) -> None:
        two_apps(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_diff(args(tmp_path, package="app_a", other="nope"))
        assert result == 1
        assert "Package not found" in capsys.readouterr().err

    def test_nothing_to_compare_against_is_a_usage_error(self, tmp_path: Path, capsys) -> None:
        two_apps(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_diff(args(tmp_path, package="app_a"))
        assert result == 2
        assert "Nothing to compare against" in capsys.readouterr().err

    def test_json_output(self, tmp_path: Path, capsys) -> None:
        two_apps(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_diff(args(tmp_path, package="app_a", other="app_b", json=True))
        payload = json.loads(capsys.readouterr().out)
        assert payload["before"] == "app_b"
        assert payload["after"] == "app_a"
        assert payload["added"] == ["only_a"]
        assert payload["removed"] == ["only_b"]


class TestSnapshots:
    """`--save` then `--against`."""

    def test_round_trip_reports_no_difference(self, tmp_path: Path, capsys) -> None:
        two_apps(tmp_path)
        snapshot = tmp_path / "snap.json"
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            saved = cmd_diff(args(tmp_path, package="app_a", save=str(snapshot)))
            assert saved == 0
            assert snapshot.exists()
            result = cmd_diff(args(tmp_path, package="app_a", against=str(snapshot)))
        assert result == 0
        assert "No difference" in capsys.readouterr().out

    def test_detects_a_new_dependency_after_the_snapshot(self, tmp_path: Path, capsys) -> None:
        two_apps(tmp_path)
        snapshot = tmp_path / "snap.json"
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_diff(args(tmp_path, package="app_a", save=str(snapshot)))
            # The workspace moves on: app_a picks up another dependency.
            write_package(tmp_path, "newcomer", version="0.1.0")
            write_package(tmp_path, "app_a", depends=["common", "only_a", "newcomer"])
            result = cmd_diff(args(tmp_path, package="app_a", against=str(snapshot)))
        out = capsys.readouterr().out
        assert result == 1
        assert "newcomer" in out

    def test_detects_a_version_bump(self, tmp_path: Path, capsys) -> None:
        two_apps(tmp_path)
        snapshot = tmp_path / "snap.json"
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_diff(args(tmp_path, package="app_a", save=str(snapshot)))
            write_package(tmp_path, "common", version="2.0.0")
            result = cmd_diff(args(tmp_path, package="app_a", against=str(snapshot)))
        out = capsys.readouterr().out
        assert result == 1
        assert "Changed" in out
        assert "1.0.0 → 2.0.0" in out

    def test_unreadable_snapshot_is_a_usage_error(self, tmp_path: Path, capsys) -> None:
        two_apps(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_diff(args(tmp_path, package="app_a", against=str(tmp_path / "nope")))
        assert result == 2
        assert "Could not read snapshot" in capsys.readouterr().err

    def test_malformed_snapshot_is_a_usage_error(self, tmp_path: Path, capsys) -> None:
        two_apps(tmp_path)
        bad = tmp_path / "bad.json"
        bad.write_text('{"not": "a snapshot"}')
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_diff(args(tmp_path, package="app_a", against=str(bad)))
        assert result == 2
        assert "Could not read snapshot" in capsys.readouterr().err

    def test_saving_an_unknown_package_is_reported(self, tmp_path: Path, capsys) -> None:
        two_apps(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_diff(args(tmp_path, package="nope", save=str(tmp_path / "snap.json")))
        assert result == 1
        assert "Package not found" in capsys.readouterr().err


class TestDiffRespectsScope:
    """Filters and dependency type apply to both sides of the comparison."""

    def test_filter_applies_to_both_sides(self, tmp_path: Path, capsys) -> None:
        two_apps(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_diff(args(tmp_path, package="app_a", other="app_b", exclude=["only_*"]))
        out = capsys.readouterr().out
        assert result == 0
        assert "No difference" in out
