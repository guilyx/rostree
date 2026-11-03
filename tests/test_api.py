"""Tests for rostree.api module."""

from __future__ import annotations

import os
import re
from pathlib import Path
from unittest import mock

import pytest

import rostree
from rostree.api import (
    build_tree,
    get_package_info,
    list_known_packages,
    list_known_packages_by_source,
    scan_workspaces,
)
from rostree.core.finder import WorkspaceInfo


class TestModuleExports:
    """Tests for rostree module-level exports."""

    def test_version_is_string(self) -> None:
        """Test that __version__ is a string."""
        assert isinstance(rostree.__version__, str)

    def test_version_format(self) -> None:
        """Test that __version__ follows semver or dev format."""
        # Should match X.Y.Z or X.Y.Z+something or 0.0.0+unknown
        pattern = r"^\d+\.\d+\.\d+(\+.+)?$"
        assert re.match(pattern, rostree.__version__), f"Invalid version: {rostree.__version__}"

    def test_version_fallback_logic(self) -> None:
        """Test that version fallback logic works correctly."""
        from importlib.metadata import PackageNotFoundError

        # Test the fallback pattern used in __init__.py
        def get_version_with_fallback(pkg_name: str) -> str:
            try:
                from importlib.metadata import version

                return version(pkg_name)
            except PackageNotFoundError:
                return "0.0.0+unknown"

        # Test with a non-existent package - exercises the except branch
        result = get_version_with_fallback("definitely_not_a_real_package_xyz")
        assert result == "0.0.0+unknown"

        # Test with rostree (should return actual version)
        result = get_version_with_fallback("rostree")
        # Should be a valid version string
        assert re.match(r"^\d+\.\d+\.\d+", result)

    def test_version_when_package_not_found(self) -> None:
        """Test __version__ fallback when package metadata unavailable."""
        import sys
        from importlib.metadata import PackageNotFoundError

        # Mock version to raise PackageNotFoundError
        def mock_version(name: str) -> str:
            raise PackageNotFoundError(name)

        # Remove rostree from cache to force re-import
        modules_to_restore = {}
        to_remove = [k for k in sys.modules if k.startswith("rostree")]
        for k in to_remove:
            modules_to_restore[k] = sys.modules.pop(k)

        try:
            # Patch and reload to exercise the except branch in __init__.py
            with mock.patch("importlib.metadata.version", mock_version):
                # Re-import - this will hit the except branch
                import rostree as rostree_reloaded

                assert rostree_reloaded.__version__ == "0.0.0+unknown"
        finally:
            # Restore original modules
            for k in list(sys.modules.keys()):
                if k.startswith("rostree"):
                    del sys.modules[k]
            sys.modules.update(modules_to_restore)

    def test_all_exports(self) -> None:
        """Test that __all__ contains expected exports."""
        assert "build_tree" in rostree.__all__
        assert "get_package_info" in rostree.__all__
        assert "list_known_packages" in rostree.__all__
        assert "list_known_packages_by_source" in rostree.__all__
        assert "scan_workspaces" in rostree.__all__
        assert "WorkspaceInfo" in rostree.__all__
        assert "__version__" in rostree.__all__


class TestListKnownPackages:
    """Tests for list_known_packages API."""

    def test_with_extra_roots(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "api_test_pkg"
        pkg_dir.mkdir()
        pkg_xml = pkg_dir / "package.xml"
        pkg_xml.write_text("<package><name>api_test_pkg</name></package>")

        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": "",
                "COLCON_PREFIX_PATH": "",
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = list_known_packages(extra_source_roots=[tmp_path])
            assert "api_test_pkg" in result

    def test_empty_env(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": "",
                "COLCON_PREFIX_PATH": "",
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = list_known_packages()
            assert isinstance(result, dict)


class TestListKnownPackagesBySource:
    """Tests for list_known_packages_by_source API."""

    def test_with_extra_roots(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "source_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "package.xml").write_text("<package><name>source_pkg</name></package>")

        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": "",
                "COLCON_PREFIX_PATH": "",
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = list_known_packages_by_source(extra_source_roots=[tmp_path])
            assert isinstance(result, dict)
            # Should have Added section
            added_keys = [k for k in result.keys() if "Added" in k]
            assert len(added_keys) == 1


class TestGetPackageInfo:
    """Tests for get_package_info API."""

    def test_package_found(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "info_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
    <name>info_pkg</name>
    <version>2.3.4</version>
    <description>Info test package</description>
    <depend>rclpy</depend>
</package>
"""
        )
        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": "",
                "COLCON_PREFIX_PATH": "",
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = get_package_info("info_pkg", extra_source_roots=[tmp_path])
            assert result is not None
            assert result.name == "info_pkg"
            assert result.version == "2.3.4"
            assert result.description == "Info test package"
            assert "rclpy" in result.dependencies

    def test_package_not_found(self, tmp_path: Path) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": "",
                "COLCON_PREFIX_PATH": "",
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = get_package_info("nonexistent_xyz", extra_source_roots=[tmp_path])
            assert result is None


class TestBuildTree:
    """Tests for build_tree API."""

    def test_simple_tree(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "tree_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
    <name>tree_pkg</name>
    <version>1.0.0</version>
    <description>Tree test</description>
</package>
"""
        )
        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": "",
                "COLCON_PREFIX_PATH": "",
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = build_tree("tree_pkg", extra_source_roots=[tmp_path])
            assert result is not None
            assert result.name == "tree_pkg"

    def test_with_max_depth(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "depth_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
    <name>depth_pkg</name>
    <version>1.0.0</version>
    <description>Depth test</description>
</package>
"""
        )
        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": "",
                "COLCON_PREFIX_PATH": "",
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = build_tree("depth_pkg", max_depth=2, extra_source_roots=[tmp_path])
            assert result is not None

    def test_runtime_only(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "runtime_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
    <name>runtime_pkg</name>
    <version>1.0.0</version>
    <description>Runtime test</description>
    <depend>dep_a</depend>
    <build_depend>build_only</build_depend>
</package>
"""
        )
        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": "",
                "COLCON_PREFIX_PATH": "",
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = build_tree("runtime_pkg", runtime_only=True, extra_source_roots=[tmp_path])
            assert result is not None
            child_names = [c.name for c in result.children]
            assert "dep_a" in child_names
            assert "build_only" not in child_names


class TestScanWorkspaces:
    """Tests for scan_workspaces API."""

    def test_finds_workspace(self, tmp_path: Path) -> None:
        from tests.conftest import make_ros_workspace

        ws = make_ros_workspace(tmp_path / "test_ws")

        result = scan_workspaces(roots=[ws], include_home=False, include_opt_ros=False)
        assert len(result) == 1
        assert isinstance(result[0], WorkspaceInfo)
        assert result[0].has_src is True

    def test_empty_roots(self, tmp_path: Path) -> None:
        result = scan_workspaces(roots=[tmp_path], include_home=False, include_opt_ros=False)
        # tmp_path has no workspace structure
        assert isinstance(result, list)

    def test_max_depth(self, tmp_path: Path) -> None:
        result = scan_workspaces(
            roots=[tmp_path],
            max_depth=1,
            include_home=False,
            include_opt_ros=False,
        )
        assert isinstance(result, list)


class TestBuildingOnTheLibrary:
    """Everything the CLI can tell you, a script can ask for directly."""

    EMPTY = {
        "AMENT_PREFIX_PATH": "",
        "COLCON_PREFIX_PATH": "",
        "ROS2_WORKSPACE": "",
        "COLCON_WORKSPACE": "",
    }

    @pytest.fixture
    def ws(self, tmp_path: Path) -> Path:
        from tests.conftest import write_package

        write_package(tmp_path, "msgs")
        write_package(tmp_path, "lib", depends=["msgs"])
        write_package(tmp_path, "nav_core", depends=["lib"])
        write_package(tmp_path, "app", depends=["nav_core", "lib"], exec_depends=["tool"])
        write_package(tmp_path, "tool")
        return tmp_path

    def _env(self):
        return mock.patch.dict(os.environ, self.EMPTY, clear=False)

    def test_every_public_name_resolves(self) -> None:
        from rostree import api

        assert [n for n in api.__all__ if not hasattr(api, n)] == []

    def test_build_tree_with_scope_and_filter(self, ws: Path) -> None:
        from rostree.api import FilterReport, PackageFilter, build_tree

        report = FilterReport()
        with self._env():
            tree = build_tree(
                "app",
                extra_source_roots=[ws],
                package_filter=PackageFilter(exclude=("lib",)),
                report=report,
            )
        assert [c.name for c in tree.children] == ["nav_core", "tool"]
        assert report.excluded == {"lib"}

    def test_dep_type_selects_tags(self, ws: Path) -> None:
        from rostree.api import build_graph

        with self._env():
            build_only = build_graph("app", extra_source_roots=[ws], dep_type="build")
            runtime = build_graph("app", extra_source_roots=[ws], dep_type="runtime")
        assert "tool" not in build_only.edges["app"]  # exec_depend only
        assert "tool" in runtime.edges["app"]

    def test_unknown_dep_type_is_an_error_not_a_silent_default(self, ws: Path) -> None:
        from rostree.api import build_graph

        with pytest.raises(ValueError):
            build_graph("app", extra_source_roots=[ws], dep_type="runtim")

    def test_dependency_paths_is_rostree_why(self, ws: Path) -> None:
        from rostree.api import dependency_paths

        with self._env():
            paths = dependency_paths("app", "msgs", extra_source_roots=[ws])
        assert paths == [["app", "lib", "msgs"]]

    def test_transitive_reverse_dependencies(self, ws: Path) -> None:
        from rostree.api import reverse_dependencies

        with self._env():
            assert reverse_dependencies("msgs", extra_source_roots=[ws]) == ["lib"]
            assert reverse_dependencies("msgs", extra_source_roots=[ws], transitive=True) == [
                "app",
                "lib",
                "nav_core",
            ]

    def test_snapshot_and_diff(self, ws: Path) -> None:
        from rostree.api import build_graph, dependency_versions, diff_dependencies
        from tests.conftest import write_package

        with self._env():
            before = dependency_versions(
                build_graph("nav_core", extra_source_roots=[ws]), exclude=["nav_core"]
            )
            write_package(ws, "nav_core", depends=["lib", "tool"])
            after = dependency_versions(
                build_graph("nav_core", extra_source_roots=[ws]), exclude=["nav_core"]
            )
        diff = diff_dependencies(before, after)
        assert diff.added == ["tool"] and not diff.removed

    def test_rendering_is_public(self, ws: Path) -> None:
        from rostree.api import GraphView, build_graph, to_dot, to_html, to_mermaid

        with self._env():
            graph = build_graph("app", extra_source_roots=[ws])
        view = GraphView.from_graph(graph)
        assert to_dot(view).startswith("digraph")
        assert to_mermaid(view).startswith("graph")
        assert to_html(graph).lstrip().lower().startswith("<!doctype html>")

    def test_include_buildtool_warns_that_it_does_nothing(self, ws: Path) -> None:
        from rostree.api import build_tree

        with self._env(), pytest.warns(DeprecationWarning, match="no effect"):
            build_tree("app", extra_source_roots=[ws], include_buildtool=True)


class TestJsonCarriesHiddenChildren:
    def test_only_on_nodes_that_hide_some(self) -> None:
        from rostree.core.tree import DependencyNode, NodeStatus

        cut = DependencyNode("a", "1", "", "/a", status=NodeStatus.TRUNCATED, hidden_children=3)
        whole = DependencyNode("b", "1", "", "/b")
        assert cut.to_dict()["hidden_children"] == 3
        assert "hidden_children" not in whole.to_dict()


class TestParseCacheIsBounded:
    def test_an_edited_manifest_replaces_its_entry(self, tmp_path: Path) -> None:
        """Keyed on mtime, every superseded parse used to stay for the process's life."""
        from rostree.core import parser
        from tests.conftest import write_package

        manifest = write_package(tmp_path, "pkg")
        parser.clear_parse_cache()
        for version in ("1.0.0", "1.1.0", "1.2.0"):
            write_package(tmp_path, "pkg", version=version)
            st = manifest.stat()
            os.utime(manifest, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
            assert parser.parse_package_xml(manifest).version == version
        assert len([k for k in parser._PARSE_CACHE if k[0] == str(manifest)]) == 1
