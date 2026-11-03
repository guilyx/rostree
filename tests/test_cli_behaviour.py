"""CLI behaviour found wrong in review, exercised end to end through ``main()``."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

import pytest
from rich.console import Console

from rostree import cli
from rostree.cli import main
from tests.conftest import write_package

EMPTY_ENV = {
    "AMENT_PREFIX_PATH": "",
    "COLCON_PREFIX_PATH": "",
    "ROS2_WORKSPACE": "",
    "COLCON_WORKSPACE": "",
}


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    """app -> [core, util, ext_msgs]; core -> util; util -> eigen (a rosdep-style key)."""
    write_package(tmp_path, "ext_msgs")
    write_package(tmp_path, "util", depends=["eigen", "unbuilt_pkg"])
    write_package(tmp_path, "core", depends=["util", "ext_msgs"])
    write_package(tmp_path, "app", depends=["core", "util", "ext_msgs"])
    return tmp_path


@pytest.fixture
def fresh_consoles(monkeypatch):
    """`--no-color` swaps module-level consoles; never let that leak between tests."""
    monkeypatch.setattr(cli, "_out", Console(highlight=False, soft_wrap=True))
    monkeypatch.setattr(cli, "_err", Console(stderr=True, highlight=False, soft_wrap=True))


def run(ws: Path, *argv: str) -> int:
    with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
        return main([*argv, "-s", str(ws)])


class TestNoColor:
    """`rostree --no-color <cmd>` set the flag and then silently unset it again."""

    @pytest.fixture(autouse=True)
    def _force_colour(self, monkeypatch, fresh_consoles):
        monkeypatch.setenv("FORCE_COLOR", "1")
        monkeypatch.delenv("NO_COLOR", raising=False)
        # Rebuild the consoles under FORCE_COLOR so they would emit ANSI.
        monkeypatch.setattr(cli, "_out", Console(highlight=False, soft_wrap=True))

    def test_colour_is_on_without_the_flag(self, ws: Path, capsys) -> None:
        """Proves the assertions below can see colour at all."""
        run(ws, "why", "app", "util")
        assert "\x1b[" in capsys.readouterr().out

    def test_flag_before_the_subcommand(self, ws: Path, capsys) -> None:
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            main(["--no-color", "why", "app", "util", "-s", str(ws)])
        assert "\x1b[" not in capsys.readouterr().out

    def test_flag_after_the_subcommand(self, ws: Path, capsys) -> None:
        run(ws, "why", "app", "util", "--no-color")
        assert "\x1b[" not in capsys.readouterr().out


@pytest.mark.usefixtures("fresh_consoles")
class TestFiltersAreAlwaysReported:
    """A filter must never make output quietly smaller. tree and why said so; the rest did not."""

    def test_graph(self, ws: Path, capsys) -> None:
        run(ws, "graph", "app", "--exclude", "ext_*")
        err = capsys.readouterr().err
        assert "hidden by filters: ext_msgs" in err

    def test_check(self, ws: Path, capsys) -> None:
        run(ws, "check", "app", "--exclude", "ext_*", "--json")
        payload = json.loads(capsys.readouterr().out)
        assert payload["filtered"] == ["ext_msgs"]

    def test_check_text(self, ws: Path, capsys) -> None:
        run(ws, "check", "app", "--exclude", "ext_*")
        assert "hidden by filters: ext_msgs" in capsys.readouterr().err

    def test_rdeps(self, ws: Path, capsys) -> None:
        run(ws, "rdeps", "util", "--transitive", "--exclude", "core")
        captured = capsys.readouterr()
        assert "hidden by filters: core" in captured.err
        # Filtered after the walk on purpose: app still breaks *through* core.
        assert "app" in captured.out

    def test_rdeps_json(self, ws: Path, capsys) -> None:
        run(ws, "rdeps", "util", "--transitive", "--exclude", "core", "--json")
        payload = json.loads(capsys.readouterr().out)
        assert payload == {"package": "util", "dependents": ["app"], "filtered": ["core"]}

    def test_diff(self, ws: Path, tmp_path_factory, capsys) -> None:
        snap = tmp_path_factory.mktemp("snap") / "before.json"
        run(ws, "diff", "app", "--save", str(snap), "--exclude", "ext_*")
        assert "hidden by filters: ext_msgs" in capsys.readouterr().err
        run(ws, "diff", "app", "--against", str(snap), "--exclude", "ext_*", "--json")
        payload = json.loads(capsys.readouterr().out)
        assert payload["filtered"] == ["ext_msgs"]

    def test_why_json(self, ws: Path, capsys) -> None:
        run(ws, "why", "app", "util", "--exclude", "ext_*", "--json")
        payload = json.loads(capsys.readouterr().out)
        assert payload["filtered"] == ["ext_msgs"]


@pytest.mark.usefixtures("fresh_consoles")
class TestWhyNamesTheScopeItSearched:
    def test_build_scope_is_not_called_runtime(self, tmp_path: Path, capsys) -> None:
        write_package(tmp_path, "lib")
        write_package(tmp_path, "tool", exec_depends=["lib"])  # runtime only
        assert run(tmp_path, "why", "tool", "lib", "--dep-type", "build") == 1
        out = capsys.readouterr().out
        assert "(build dependencies only)" in out
        assert "runtime" not in out

    def test_depth_limit_is_named(self, ws: Path, capsys) -> None:
        assert run(ws, "why", "app", "eigen", "--depth", "0") == 1
        assert "within depth 0" in capsys.readouterr().out


@pytest.mark.usefixtures("fresh_consoles")
class TestIgnoreSystemIsNeverSilent:
    """--ignore-system guesses from the name, so it must show what it held back."""

    def test_text_lists_what_was_ignored(self, ws: Path, capsys) -> None:
        result = run(ws, "check", "app", "--ignore-system")
        captured = capsys.readouterr()
        assert "not counted (--ignore-system): eigen" in captured.err
        # unbuilt_pkg has an underscore, so it still counts and still fails.
        assert "unbuilt_pkg" in captured.out
        assert result == 1

    def test_json_carries_both_lists(self, ws: Path, capsys) -> None:
        run(ws, "check", "app", "--ignore-system", "--json")
        payload = json.loads(capsys.readouterr().out)
        assert payload["unresolved"] == ["unbuilt_pkg"]
        assert payload["ignored"] == ["eigen"]


@pytest.mark.usefixtures("fresh_consoles")
class TestWorkspaceWideGraph:
    def test_roots_honour_the_filter(self, tmp_path: Path, capsys) -> None:
        """A workspace graph starts from what the filter allows, like `check`."""
        write_package(tmp_path, "nav_a")
        write_package(tmp_path, "nav_b")
        write_package(tmp_path, "other")
        run(tmp_path, "graph", "--include", "nav_*")
        out = capsys.readouterr().out
        assert '"nav_a"' in out and '"nav_b"' in out
        assert '"other"' not in out

    def test_extra_source_roots_are_graphed(self, tmp_path: Path, capsys) -> None:
        """Roots came from a second index built without the -s paths."""
        write_package(tmp_path, "only_via_s")
        assert run(tmp_path, "graph") == 0
        assert "only_via_s" in capsys.readouterr().out
