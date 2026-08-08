"""Tests for package filtering and dependency-type selection."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from rostree.core.filters import (
    DEP_TYPE_CHOICES,
    FilterReport,
    PackageFilter,
    tags_for_dep_type,
)
from rostree.core.index import PackageEntry, SourceKind, build_index
from rostree.core.tree import build_dependency_graph, build_dependency_tree
from tests.conftest import write_package

EMPTY_ENV = {
    "AMENT_PREFIX_PATH": "",
    "COLCON_PREFIX_PATH": "",
    "ROS2_WORKSPACE": "",
    "COLCON_WORKSPACE": "",
}


def entry(name: str, kind: SourceKind) -> PackageEntry:
    return PackageEntry(
        name=name,
        manifest=Path(f"/somewhere/{name}/package.xml"),
        kind=kind,
        origin=Path("/somewhere"),
        label="test",
    )


class TestDepType:
    """Tests for --dep-type translation."""

    def test_every_choice_translates(self) -> None:
        for choice in DEP_TYPE_CHOICES:
            tags_for_dep_type(choice)  # must not raise

    def test_runtime_is_depend_and_exec_depend(self) -> None:
        assert tags_for_dep_type("runtime") == ("depend", "exec_depend")

    def test_build_includes_build_tags(self) -> None:
        tags = tags_for_dep_type("build")
        assert "build_depend" in tags
        assert "exec_depend" not in tags

    def test_test_includes_test_depend(self) -> None:
        assert "test_depend" in tags_for_dep_type("test")

    def test_all_means_every_tag(self) -> None:
        assert tags_for_dep_type("all") is None

    def test_unknown_choice_is_an_error(self) -> None:
        with pytest.raises(ValueError, match="unknown dependency type"):
            tags_for_dep_type("sideways")


class TestPackageFilter:
    """Tests for the predicate itself."""

    def test_empty_filter_allows_everything(self) -> None:
        f = PackageFilter()
        assert f.is_noop
        assert f.allows("anything")

    def test_exclude_glob(self) -> None:
        f = PackageFilter(exclude=("rosidl_*",))
        assert not f.allows("rosidl_runtime_c")
        assert f.allows("rclcpp")

    def test_include_glob_restricts(self) -> None:
        f = PackageFilter(include=("nav2_*",))
        assert f.allows("nav2_core")
        assert not f.allows("rclcpp")

    def test_exclude_beats_include(self) -> None:
        f = PackageFilter(include=("nav2_*",), exclude=("nav2_util",))
        assert f.allows("nav2_core")
        assert not f.allows("nav2_util")

    def test_multiple_patterns_are_any_of(self) -> None:
        f = PackageFilter(include=("nav2_*", "*_msgs"))
        assert f.allows("nav2_core")
        assert f.allows("sensor_msgs")
        assert not f.allows("rclcpp")

    def test_only_workspace_drops_system_packages(self) -> None:
        f = PackageFilter(only_workspace=True)
        assert not f.allows("rclcpp", entry("rclcpp", SourceKind.SYSTEM))
        assert f.allows("my_pkg", entry("my_pkg", SourceKind.WORKSPACE))
        assert f.allows("src_pkg", entry("src_pkg", SourceKind.SOURCE))

    def test_only_workspace_keeps_unresolved_names(self) -> None:
        """An unresolved rosdep key has no entry; it is not a system package."""
        assert PackageFilter(only_workspace=True).allows("some_rosdep_key", None)

    def test_matching_is_case_sensitive(self) -> None:
        assert PackageFilter(exclude=("NAV2_*",)).allows("nav2_core")

    def test_filter_names_preserves_order_and_reports(self) -> None:
        f = PackageFilter(exclude=("b*",))
        report = FilterReport()
        assert f.filter_names(["c", "b1", "a", "b2"], report=report) == ["c", "a"]
        assert report.excluded == {"b1", "b2"}

    def test_from_args_accepts_none(self) -> None:
        assert PackageFilter.from_args().is_noop


class TestFilterReport:
    """Tests for what gets reported back to the user."""

    def test_empty_report_is_falsey(self) -> None:
        report = FilterReport()
        assert not report
        assert report.summary() == ""

    def test_summary_names_and_counts(self) -> None:
        report = FilterReport()
        for name in ("a", "b"):
            report.note(name)
        assert report.summary() == "2 package(s) hidden by filters: a, b"

    def test_summary_truncates_long_lists(self) -> None:
        report = FilterReport()
        for i in range(10):
            report.note(f"pkg{i}")
        summary = report.summary(limit=3)
        assert summary.startswith("10 package(s) hidden by filters: pkg0, pkg1, pkg2")
        assert "and 7 more" in summary


class TestFilteredTraversal:
    """Filtering during tree and graph building."""

    def _stack(self, root: Path) -> None:
        write_package(root, "leaf")
        write_package(root, "rosidl_thing", depends=["leaf"])
        write_package(root, "nav2_util", depends=["rosidl_thing"])
        write_package(root, "nav2_bringup", depends=["nav2_util", "rosidl_thing"])

    def test_excluded_package_is_not_shown(self, tmp_path: Path) -> None:
        self._stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            tree = build_dependency_tree(
                "nav2_bringup",
                extra_source_roots=[tmp_path],
                package_filter=PackageFilter(exclude=("rosidl_*",)),
            )
        names = {n.name for n in tree.walk()}
        assert names == {"nav2_bringup", "nav2_util"}

    def test_excluded_package_is_not_traversed_through(self, tmp_path: Path) -> None:
        """`leaf` is only reachable via rosidl_thing, so it goes too."""
        self._stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            tree = build_dependency_tree(
                "nav2_bringup",
                extra_source_roots=[tmp_path],
                package_filter=PackageFilter(exclude=("rosidl_*",)),
            )
        assert "leaf" not in {n.name for n in tree.walk()}

    def test_filter_reports_what_it_removed(self, tmp_path: Path) -> None:
        self._stack(tmp_path)
        report = FilterReport()
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            build_dependency_tree(
                "nav2_bringup",
                extra_source_roots=[tmp_path],
                package_filter=PackageFilter(exclude=("rosidl_*",)),
                report=report,
            )
        assert report.excluded == {"rosidl_thing"}

    def test_include_keeps_only_matching_dependencies(self, tmp_path: Path) -> None:
        self._stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            tree = build_dependency_tree(
                "nav2_bringup",
                extra_source_roots=[tmp_path],
                package_filter=PackageFilter(include=("nav2_*",)),
            )
        assert {n.name for n in tree.walk()} == {"nav2_bringup", "nav2_util"}

    def test_a_package_whose_deps_are_all_filtered_is_a_leaf(self, tmp_path: Path) -> None:
        self._stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            tree = build_dependency_tree(
                "nav2_util",
                extra_source_roots=[tmp_path],
                package_filter=PackageFilter(exclude=("rosidl_*",)),
            )
        assert tree.name == "nav2_util"
        assert tree.children == []

    def test_graph_building_applies_the_filter(self, tmp_path: Path) -> None:
        self._stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            graph = build_dependency_graph(
                "nav2_bringup",
                extra_source_roots=[tmp_path],
                package_filter=PackageFilter(exclude=("rosidl_*",)),
            )
        assert set(graph.packages) == {"nav2_bringup", "nav2_util"}
        assert graph.edge_pairs() == {("nav2_bringup", "nav2_util")}

    def test_hidden_child_count_respects_the_filter(self, tmp_path: Path) -> None:
        """`… N more` must not promise dependencies the filter already removed."""
        write_package(tmp_path, "keep_me")
        write_package(tmp_path, "drop_me")
        write_package(tmp_path, "mid", depends=["keep_me", "drop_me"])
        write_package(tmp_path, "top", depends=["mid"])
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            tree = build_dependency_tree(
                "top",
                max_depth=1,
                extra_source_roots=[tmp_path],
                package_filter=PackageFilter(exclude=("drop_me",)),
            )
        assert tree.children[0].hidden_children == 1

    def test_only_workspace_drops_system_dependencies(self, tmp_path: Path) -> None:
        system = tmp_path / "opt" / "ros" / "jazzy"
        (system / "share").mkdir(parents=True)
        write_package(system / "share", "rclcpp")
        ws = tmp_path / "ws" / "install"
        (ws / "share").mkdir(parents=True)
        write_package(ws / "share", "my_node", depends=["rclcpp"])

        env = dict(EMPTY_ENV, AMENT_PREFIX_PATH=os.pathsep.join([str(system), str(ws)]))
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch("rostree.core.index.is_system_prefix", lambda p: p == system):
                index = build_index()
            tree = build_dependency_tree(
                "my_node", index=index, package_filter=PackageFilter(only_workspace=True)
            )
        assert tree.children == []


class TestDepTypeTraversal:
    """--dep-type selects which package.xml tags are followed."""

    def _pkg(self, root: Path) -> None:
        (root / "app").mkdir()
        (root / "app" / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
  <name>app</name>
  <version>1.0.0</version>
  <description>d</description>
  <exec_depend>runtime_dep</exec_depend>
  <build_depend>build_dep</build_depend>
  <test_depend>test_dep</test_depend>
</package>
"""
        )
        for name in ("runtime_dep", "build_dep", "test_dep"):
            write_package(root, name)

    def test_runtime_follows_only_runtime_tags(self, tmp_path: Path) -> None:
        self._pkg(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            tree = build_dependency_tree(
                "app",
                extra_source_roots=[tmp_path],
                include_tags=tags_for_dep_type("runtime"),
            )
        assert {c.name for c in tree.children} == {"runtime_dep"}

    def test_build_follows_build_tags(self, tmp_path: Path) -> None:
        self._pkg(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            tree = build_dependency_tree(
                "app",
                extra_source_roots=[tmp_path],
                include_tags=tags_for_dep_type("build"),
            )
        assert {c.name for c in tree.children} == {"build_dep"}

    def test_all_follows_everything(self, tmp_path: Path) -> None:
        self._pkg(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            tree = build_dependency_tree(
                "app", extra_source_roots=[tmp_path], include_tags=tags_for_dep_type("all")
            )
        assert {c.name for c in tree.children} == {"runtime_dep", "build_dep", "test_dep"}
