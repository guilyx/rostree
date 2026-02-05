"""Tests for rostree.api module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock


from rostree.api import (
    list_known_packages,
    list_known_packages_by_source,
    get_package_info,
    build_tree,
    scan_workspaces,
)
from rostree.core.finder import WorkspaceInfo


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
        ws = tmp_path / "test_ws"
        ws.mkdir()
        (ws / "src").mkdir()

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
