"""Tests for the why, rdeps and check commands, against real packages on disk."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from unittest import mock

from defusedxml.ElementTree import parse as parse_xml

from rostree.cli import cmd_check, cmd_rdeps, cmd_tree, cmd_why
from rostree.core.tree import build_dependency_graph
from tests.conftest import write_package

EMPTY_ENV = {
    "AMENT_PREFIX_PATH": "",
    "COLCON_PREFIX_PATH": "",
    "ROS2_WORKSPACE": "",
    "COLCON_WORKSPACE": "",
}


def stack(root: Path) -> None:
    """app -> [core, util], core -> util, util -> missing_key."""
    write_package(root, "util", depends=["missing_key"])
    write_package(root, "core", depends=["util"])
    write_package(root, "app", depends=["core", "util"])


def args(tmp_path: Path, **overrides) -> argparse.Namespace:
    base = dict(
        source=[str(tmp_path)],
        runtime=False,
        dep_type=None,
        json=False,
        verbose=False,
        include=None,
        exclude=None,
        only_workspace=False,
        junit=None,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


class TestCmdWhy:
    """Tests for `rostree why`."""

    def test_reports_the_shortest_path(self, tmp_path: Path, capsys) -> None:
        stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_why(args(tmp_path, package="app", dependency="util", depth=None, limit=10))
        out = capsys.readouterr().out
        assert result == 0
        # app depends on util directly, so the shortest path is length 1.
        assert "length 1" in out
        assert "app → util" in out

    def test_finds_indirect_paths(self, tmp_path: Path, capsys) -> None:
        write_package(tmp_path, "leaf")
        write_package(tmp_path, "middle", depends=["leaf"])
        write_package(tmp_path, "top", depends=["middle"])
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_why(args(tmp_path, package="top", dependency="leaf", depth=None, limit=10))
        out = capsys.readouterr().out
        assert result == 0
        assert "top → middle → leaf" in out

    def test_reports_every_shortest_path(self, tmp_path: Path, capsys) -> None:
        write_package(tmp_path, "leaf")
        write_package(tmp_path, "left", depends=["leaf"])
        write_package(tmp_path, "right", depends=["leaf"])
        write_package(tmp_path, "top", depends=["left", "right"])
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_why(args(tmp_path, package="top", dependency="leaf", depth=None, limit=10))
        out = capsys.readouterr().out
        assert "2 shortest path(s)" in out
        assert "top → left → leaf" in out
        assert "top → right → leaf" in out

    def test_limit_caps_the_number_of_paths(self, tmp_path: Path, capsys) -> None:
        write_package(tmp_path, "leaf")
        for name in ("a", "b", "c"):
            write_package(tmp_path, name, depends=["leaf"])
        write_package(tmp_path, "top", depends=["a", "b", "c"])
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_why(args(tmp_path, package="top", dependency="leaf", depth=None, limit=2))
        out = capsys.readouterr().out
        assert out.count("→ leaf") == 2

    def test_no_path_is_a_failure(self, tmp_path: Path, capsys) -> None:
        write_package(tmp_path, "alone")
        write_package(tmp_path, "unrelated")
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_why(
                args(tmp_path, package="alone", dependency="unrelated", depth=None, limit=10)
            )
        assert result == 1
        assert "does not depend on" in capsys.readouterr().out

    def test_unknown_root_package(self, tmp_path: Path, capsys) -> None:
        stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_why(
                args(tmp_path, package="nope", dependency="util", depth=None, limit=10)
            )
        assert result == 1
        assert "Package not found" in capsys.readouterr().err

    def test_json_output(self, tmp_path: Path, capsys) -> None:
        stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_why(
                args(
                    tmp_path,
                    package="app",
                    dependency="util",
                    depth=None,
                    limit=10,
                    json=True,
                )
            )
        payload = json.loads(capsys.readouterr().out)
        assert payload["from"] == "app"
        assert payload["paths"] == [["app", "util"]]


class TestCmdRdeps:
    """Tests for `rostree rdeps`."""

    def test_lists_direct_dependents(self, tmp_path: Path, capsys) -> None:
        stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_rdeps(
                args(tmp_path, package="util", transitive=False, workspace_only=False)
            )
        out = capsys.readouterr().out
        assert result == 0
        assert "app" in out and "core" in out

    def test_transitive_walks_upwards(self, tmp_path: Path, capsys) -> None:
        write_package(tmp_path, "leaf")
        write_package(tmp_path, "middle", depends=["leaf"])
        write_package(tmp_path, "top", depends=["middle"])
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_rdeps(args(tmp_path, package="leaf", transitive=True, workspace_only=False))
        out = capsys.readouterr().out
        assert "middle" in out and "top" in out

    def test_nothing_depends_on_it(self, tmp_path: Path, capsys) -> None:
        stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_rdeps(
                args(tmp_path, package="app", transitive=False, workspace_only=False)
            )
        assert result == 0
        assert "Nothing depends on" in capsys.readouterr().out

    def test_unknown_package(self, tmp_path: Path, capsys) -> None:
        stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_rdeps(
                args(tmp_path, package="nope", transitive=False, workspace_only=False)
            )
        assert result == 1
        assert "Package not found" in capsys.readouterr().err

    def test_json_output(self, tmp_path: Path, capsys) -> None:
        stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_rdeps(
                args(
                    tmp_path,
                    package="util",
                    transitive=False,
                    workspace_only=False,
                    json=True,
                )
            )
        payload = json.loads(capsys.readouterr().out)
        assert payload["package"] == "util"
        assert payload["dependents"] == ["app", "core"]


class TestCmdCheck:
    """Tests for `rostree check`."""

    def test_reports_unresolved_dependencies(self, tmp_path: Path, capsys) -> None:
        stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_check(args(tmp_path, packages=["app"], ignore_system=False))
        out = capsys.readouterr().out
        assert result == 1
        assert "missing_key" in out
        assert "No dependency cycles" in out

    def test_reports_cycles(self, tmp_path: Path, capsys) -> None:
        write_package(tmp_path, "a", depends=["b"])
        write_package(tmp_path, "b", depends=["c"])
        write_package(tmp_path, "c", depends=["a"])
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_check(args(tmp_path, packages=["a"], ignore_system=False))
        out = capsys.readouterr().out
        assert result == 1
        assert "dependency cycle" in out
        assert "a → b → c → a" in out

    def test_clean_workspace_exits_zero(self, tmp_path: Path, capsys) -> None:
        write_package(tmp_path, "leaf")
        write_package(tmp_path, "top", depends=["leaf"])
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_check(args(tmp_path, packages=["top"], ignore_system=False))
        out = capsys.readouterr().out
        assert result == 0
        assert "No dependency cycles" in out
        assert "Every dependency resolves" in out

    def test_unknown_package_is_a_usage_error(self, tmp_path: Path, capsys) -> None:
        write_package(tmp_path, "leaf")
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_check(args(tmp_path, packages=["nope"], ignore_system=False))
        assert result == 2
        assert "Unknown package" in capsys.readouterr().err

    def test_defaults_to_every_workspace_package(self, tmp_path: Path, capsys) -> None:
        stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_check(args(tmp_path, packages=[], ignore_system=False))
        assert result == 1
        assert "from 3 root(s)" in capsys.readouterr().out

    def test_json_output(self, tmp_path: Path, capsys) -> None:
        stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_check(args(tmp_path, packages=["app"], ignore_system=False, json=True))
        payload = json.loads(capsys.readouterr().out)
        assert payload["unresolved"] == ["missing_key"]
        assert payload["cycles"] == []


class TestTreeRendering:
    """Tests for how `rostree tree` presents repeats and depth limits."""

    def test_repeats_are_summarised(self, tmp_path: Path, capsys) -> None:
        write_package(tmp_path, "leaf_a", depends=["deep"])
        write_package(tmp_path, "leaf_b", depends=["deep"])
        write_package(tmp_path, "deep")
        write_package(tmp_path, "mid", depends=["leaf_a", "leaf_b"])
        write_package(tmp_path, "top", depends=["leaf_a", "leaf_b", "mid"])
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_tree(args(tmp_path, package="top", depth=None))
        out = capsys.readouterr().out
        assert result == 0
        assert "already shown above" in out

    def test_expand_repeats_lists_them_individually(self, tmp_path: Path, capsys) -> None:
        write_package(tmp_path, "leaf_a", depends=["deep"])
        write_package(tmp_path, "leaf_b", depends=["deep"])
        write_package(tmp_path, "deep")
        write_package(tmp_path, "mid", depends=["leaf_a", "leaf_b"])
        write_package(tmp_path, "top", depends=["leaf_a", "leaf_b", "mid"])
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_tree(args(tmp_path, package="top", depth=None, expand_repeats=True))
        out = capsys.readouterr().out
        assert "already shown above" not in out
        assert "see above" in out

    def test_depth_limit_reports_hidden_dependency_count(self, tmp_path: Path, capsys) -> None:
        write_package(tmp_path, "leaf_a")
        write_package(tmp_path, "leaf_b")
        write_package(tmp_path, "mid", depends=["leaf_a", "leaf_b"])
        write_package(tmp_path, "top", depends=["mid"])
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_tree(args(tmp_path, package="top", depth=1))
        out = capsys.readouterr().out
        assert "2 more" in out

    def test_summary_counts_go_to_stderr(self, tmp_path: Path, capsys) -> None:
        stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_tree(args(tmp_path, package="app", depth=None))
        captured = capsys.readouterr()
        assert "package(s)" in captured.err
        assert "package(s)" not in captured.out

    def test_unknown_package_suggests_alternatives(self, tmp_path: Path, capsys) -> None:
        write_package(tmp_path, "navigation_core")
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_tree(args(tmp_path, package="navigation_cor", depth=None))
        err = capsys.readouterr().err
        assert result == 1
        assert "Did you mean" in err
        assert "navigation_core" in err


class TestCmdWhyValidation:
    """Argument validation for `rostree why`."""

    def test_same_package_twice_is_rejected(self, tmp_path: Path, capsys) -> None:
        stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_why(args(tmp_path, package="app", dependency="app", depth=None, limit=10))
        assert result == 1
        assert "own starting point" in capsys.readouterr().err

    def test_unknown_package_twice_is_still_rejected(self, tmp_path: Path, capsys) -> None:
        """A bogus name must not slip through just because both arguments match."""
        stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_why(
                args(tmp_path, package="bogus", dependency="bogus", depth=None, limit=10)
            )
        assert result == 1
        assert "Package not found" in capsys.readouterr().err

    def test_unresolved_dependency_name_is_allowed(self, tmp_path: Path, capsys) -> None:
        """The target may be a rosdep key that resolves to no package."""
        stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_why(
                args(tmp_path, package="app", dependency="missing_key", depth=None, limit=10)
            )
        out = capsys.readouterr().out
        assert result == 0
        assert "app → core → util → missing_key" in out or "app → util → missing_key" in out


class TestFilterFlags:
    """The scope flags shared by the graph-walking commands."""

    def test_tree_exclude_drops_a_subtree(self, tmp_path: Path, capsys) -> None:
        write_package(tmp_path, "leaf")
        write_package(tmp_path, "rosidl_thing", depends=["leaf"])
        write_package(tmp_path, "app", depends=["rosidl_thing"])
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_tree(args(tmp_path, package="app", depth=None, exclude=["rosidl_*"]))
        captured = capsys.readouterr()
        assert result == 0
        assert "rosidl_thing" not in captured.out
        assert "leaf" not in captured.out
        # ...and the tree says so rather than quietly hiding it.
        assert "hidden by filters" in captured.err

    def test_tree_include_keeps_only_matches(self, tmp_path: Path, capsys) -> None:
        write_package(tmp_path, "nav2_util")
        write_package(tmp_path, "rclcpp")
        write_package(tmp_path, "nav2_bringup", depends=["nav2_util", "rclcpp"])
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_tree(args(tmp_path, package="nav2_bringup", depth=None, include=["nav2_*"]))
        out = capsys.readouterr().out
        assert "nav2_util" in out
        assert "rclcpp" not in out

    def test_dep_type_selects_the_tags(self, tmp_path: Path, capsys) -> None:
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
  <name>app</name>
  <version>1.0.0</version>
  <description>d</description>
  <exec_depend>runtime_dep</exec_depend>
  <build_depend>build_dep</build_depend>
</package>
"""
        )
        write_package(tmp_path, "runtime_dep")
        write_package(tmp_path, "build_dep")
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_tree(args(tmp_path, package="app", depth=None, dep_type="build"))
        out = capsys.readouterr().out
        assert "build_dep" in out
        assert "runtime_dep" not in out

    def test_dep_type_overrides_the_runtime_shorthand(self, tmp_path: Path, capsys) -> None:
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
  <name>app</name>
  <version>1.0.0</version>
  <description>d</description>
  <exec_depend>runtime_dep</exec_depend>
  <test_depend>test_dep</test_depend>
</package>
"""
        )
        write_package(tmp_path, "runtime_dep")
        write_package(tmp_path, "test_dep")
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_tree(args(tmp_path, package="app", depth=None, runtime=True, dep_type="test"))
        out = capsys.readouterr().out
        assert "test_dep" in out
        assert "runtime_dep" not in out

    def test_rdeps_honours_include(self, tmp_path: Path, capsys) -> None:
        write_package(tmp_path, "leaf")
        write_package(tmp_path, "nav2_user", depends=["leaf"])
        write_package(tmp_path, "other_user", depends=["leaf"])
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_rdeps(
                args(
                    tmp_path,
                    package="leaf",
                    transitive=False,
                    only_workspace=False,
                    include=["nav2_*"],
                )
            )
        out = capsys.readouterr().out
        assert "nav2_user" in out
        assert "other_user" not in out

    def test_check_junit_report(self, tmp_path: Path) -> None:
        write_package(tmp_path, "app", depends=["missing_key"])
        report = tmp_path / "reports" / "check.xml"
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_check(
                args(tmp_path, packages=["app"], ignore_system=False, junit=str(report))
            )
        assert result == 1
        assert report.exists()
        text = report.read_text()
        assert "<testsuite" in text
        assert "UnresolvedDependency" in text
        assert "missing_key" in text

    def test_check_junit_passes_cleanly(self, tmp_path: Path) -> None:
        write_package(tmp_path, "leaf")
        write_package(tmp_path, "app", depends=["leaf"])
        report = tmp_path / "check.xml"
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            result = cmd_check(
                args(tmp_path, packages=["app"], ignore_system=False, junit=str(report))
            )
        assert result == 0
        assert "<failure" not in report.read_text()


class TestJUnitReport:
    """
    The report has to survive package names that are arbitrary text.

    Each test reads back a file it wrote to ``tmp_path`` a few lines earlier;
    parsing is the assertion, since malformed XML raises rather than compares.
    """

    def test_report_is_well_formed_xml(self, tmp_path: Path) -> None:
        write_package(tmp_path, "app", depends=["missing_key"])
        report = tmp_path / "check.xml"
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_check(args(tmp_path, packages=["app"], ignore_system=False, junit=str(report)))
        # Parsing it back is the real assertion: malformed XML raises here.
        root = parse_xml(report).getroot()
        assert root.tag == "testsuite"
        assert root.get("tests") == "2"
        assert root.get("failures") == "1"
        cases = root.findall("testcase")
        assert [c.get("name") for c in cases] == [
            "no dependency cycles",
            "all dependencies resolve",
        ]
        assert cases[0].find("failure") is None
        assert "missing_key" in cases[1].find("failure").text

    def test_cycles_are_reported_as_a_failing_case(self, tmp_path: Path) -> None:
        write_package(tmp_path, "a", depends=["b"])
        write_package(tmp_path, "b", depends=["a"])
        report = tmp_path / "check.xml"
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_check(args(tmp_path, packages=["a"], ignore_system=False, junit=str(report)))
        root = parse_xml(report).getroot()
        failure = root.findall("testcase")[0].find("failure")
        assert failure.get("type") == "DependencyCycle"
        assert "a -> b -> a" in failure.text

    def test_xml_metacharacters_in_names_are_escaped(self, tmp_path: Path) -> None:
        """A dependency name is arbitrary text; it must not break the document."""
        pkg = tmp_path / "app"
        pkg.mkdir()
        # Entities in the manifest, so the *parsed* name really holds < and &.
        pkg.joinpath("package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
  <name>app</name>
  <version>1.0.0</version>
  <description>d</description>
  <depend>weird&lt;&amp;name</depend>
</package>
"""
        )
        report = tmp_path / "check.xml"
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            cmd_check(args(tmp_path, packages=["app"], ignore_system=False, junit=str(report)))
        # Parsing succeeds only if the writer escaped the name properly.
        root = parse_xml(report).getroot()
        text = root.findall("testcase")[1].find("failure").text
        assert "weird<&name" in text

    def test_root_names_are_escaped_in_attributes(self, tmp_path: Path) -> None:
        write_package(tmp_path, "app")
        report = tmp_path / "check.xml"
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            with mock.patch(
                "rostree.cli.build_dependency_graph",
                side_effect=build_dependency_graph,
            ):
                cmd_check(args(tmp_path, packages=["app"], ignore_system=False, junit=str(report)))
        root = parse_xml(report).getroot()
        assert root.get("package") == "app"
