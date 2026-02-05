"""Tests for rostree.core.finder module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock


from rostree.core.finder import (
    WorkspaceInfo,
    scan_for_workspaces,
    find_package_path,
    list_package_paths,
    list_packages_by_source,
    _env_paths,
    _find_package_xml_in_prefix,
    _find_package_xml_in_src,
    _gather_workspace_src_roots,
    _is_system_prefix,
    _workspace_root_from_prefix,
    _list_packages_in_src,
    _list_packages_in_install,
)


class TestWorkspaceInfo:
    """Tests for WorkspaceInfo dataclass."""

    def test_is_valid_with_src(self) -> None:
        ws = WorkspaceInfo(path=Path("/test"), has_src=True)
        assert ws.is_valid is True

    def test_is_valid_with_install(self) -> None:
        ws = WorkspaceInfo(path=Path("/test"), has_install=True)
        assert ws.is_valid is True

    def test_is_valid_neither(self) -> None:
        ws = WorkspaceInfo(path=Path("/test"))
        assert ws.is_valid is False

    def test_to_dict(self) -> None:
        ws = WorkspaceInfo(
            path=Path("/test/ws"),
            has_src=True,
            has_install=True,
            has_build=True,
            packages=["pkg_a", "pkg_b"],
        )
        d = ws.to_dict()
        assert d["path"] == "/test/ws"
        assert d["has_src"] is True
        assert d["has_install"] is True
        assert d["has_build"] is True
        assert d["packages"] == ["pkg_a", "pkg_b"]
        assert d["is_valid"] is True


class TestEnvPaths:
    """Tests for _env_paths helper."""

    def test_empty_env(self) -> None:
        with mock.patch.dict(os.environ, {"NONEXISTENT_VAR": ""}, clear=False):
            assert _env_paths("NONEXISTENT_VAR") == []

    def test_nonexistent_env(self) -> None:
        assert _env_paths("TOTALLY_NONEXISTENT_VAR_XYZ") == []

    def test_paths_with_nonexistent_dirs(self, tmp_path: Path) -> None:
        existing = tmp_path / "exists"
        existing.mkdir()
        nonexistent = tmp_path / "nonexistent"
        value = f"{existing}{os.pathsep}{nonexistent}"
        with mock.patch.dict(os.environ, {"TEST_PATH": value}, clear=False):
            result = _env_paths("TEST_PATH")
            assert len(result) == 1
            assert result[0] == existing.resolve()


class TestFindPackageXmlInPrefix:
    """Tests for _find_package_xml_in_prefix."""

    def test_found(self, tmp_path: Path) -> None:
        # Create share/pkg/package.xml
        pkg_dir = tmp_path / "share" / "my_pkg"
        pkg_dir.mkdir(parents=True)
        pkg_xml = pkg_dir / "package.xml"
        pkg_xml.write_text("<package><name>my_pkg</name></package>")

        result = _find_package_xml_in_prefix(tmp_path, "my_pkg")
        assert result == pkg_xml

    def test_not_found(self, tmp_path: Path) -> None:
        result = _find_package_xml_in_prefix(tmp_path, "nonexistent")
        assert result is None


class TestFindPackageXmlInSrc:
    """Tests for _find_package_xml_in_src."""

    def test_found(self, tmp_path: Path) -> None:
        # Create nested package
        pkg_dir = tmp_path / "subdir" / "my_pkg"
        pkg_dir.mkdir(parents=True)
        pkg_xml = pkg_dir / "package.xml"
        pkg_xml.write_text("<package><name>my_pkg</name></package>")

        result = _find_package_xml_in_src(tmp_path, "my_pkg")
        assert result == pkg_xml

    def test_not_found(self, tmp_path: Path) -> None:
        result = _find_package_xml_in_src(tmp_path, "nonexistent")
        assert result is None

    def test_wrong_name(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        pkg_xml = pkg_dir / "package.xml"
        pkg_xml.write_text("<package><name>different_name</name></package>")

        result = _find_package_xml_in_src(tmp_path, "my_pkg")
        assert result is None


class TestGatherWorkspaceSrcRoots:
    """Tests for _gather_workspace_src_roots."""

    def test_extra_roots_only(self, tmp_path: Path) -> None:
        src1 = tmp_path / "ws1" / "src"
        src1.mkdir(parents=True)
        src2 = tmp_path / "ws2"
        src2.mkdir()

        with mock.patch.dict(
            os.environ,
            {
                "COLCON_PREFIX_PATH": "",
                "AMENT_PREFIX_PATH": "",
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = _gather_workspace_src_roots(extra_source_roots=[src1, src2])
            assert src1.resolve() in result
            assert src2.resolve() in result

    def test_deduplication(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()

        with mock.patch.dict(
            os.environ,
            {
                "COLCON_PREFIX_PATH": "",
                "AMENT_PREFIX_PATH": "",
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = _gather_workspace_src_roots(extra_source_roots=[src, src, src])
            # Should only appear once
            assert result.count(src.resolve()) == 1


class TestIsSystemPrefix:
    """Tests for _is_system_prefix."""

    def test_opt_ros_is_system(self) -> None:
        assert _is_system_prefix(Path("/opt/ros/humble/lib")) is True
        assert _is_system_prefix(Path("/opt/ros/iron")) is True

    def test_non_system(self) -> None:
        assert _is_system_prefix(Path("/home/user/ros_ws/install")) is False
        assert _is_system_prefix(Path("/tmp/ws")) is False


class TestWorkspaceRootFromPrefix:
    """Tests for _workspace_root_from_prefix."""

    def test_install_dir(self) -> None:
        result = _workspace_root_from_prefix(Path("/home/user/ws/install"))
        assert result == Path("/home/user/ws")

    def test_under_install(self) -> None:
        result = _workspace_root_from_prefix(Path("/home/user/ws/install/lib"))
        assert result == Path("/home/user/ws")

    def test_not_install(self) -> None:
        result = _workspace_root_from_prefix(Path("/home/user/ws/src"))
        # Returns the path itself
        assert result is not None


class TestListPackagesInSrc:
    """Tests for _list_packages_in_src."""

    def test_finds_packages(self, tmp_path: Path) -> None:
        # Create packages
        for name in ["pkg_a", "pkg_b", "pkg_c"]:
            pkg_dir = tmp_path / name
            pkg_dir.mkdir()
            (pkg_dir / "package.xml").write_text(f"<package><name>{name}</name></package>")

        result = _list_packages_in_src(tmp_path)
        assert sorted(result) == ["pkg_a", "pkg_b", "pkg_c"]

    def test_empty_dir(self, tmp_path: Path) -> None:
        result = _list_packages_in_src(tmp_path)
        assert result == []

    def test_handles_invalid_xml(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "bad_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "package.xml").write_text("not valid xml <<<")

        # Should not raise, just skip
        result = _list_packages_in_src(tmp_path)
        assert result == []


class TestListPackagesInInstall:
    """Tests for _list_packages_in_install."""

    def test_finds_packages(self, tmp_path: Path) -> None:
        share = tmp_path / "share"
        share.mkdir()
        for name in ["pkg_x", "pkg_y"]:
            pkg_dir = share / name
            pkg_dir.mkdir()
            (pkg_dir / "package.xml").write_text(f"<package><name>{name}</name></package>")

        result = _list_packages_in_install(tmp_path)
        assert sorted(result) == ["pkg_x", "pkg_y"]

    def test_empty(self, tmp_path: Path) -> None:
        result = _list_packages_in_install(tmp_path)
        assert result == []


class TestScanForWorkspaces:
    """Tests for scan_for_workspaces."""

    def test_finds_workspace_with_src(self, tmp_path: Path) -> None:
        ws = tmp_path / "my_ws"
        ws.mkdir()
        (ws / "src").mkdir()

        result = scan_for_workspaces(roots=[ws], include_home=False, include_opt_ros=False)
        assert len(result) == 1
        assert result[0].path == ws.resolve()
        assert result[0].has_src is True

    def test_finds_workspace_with_install(self, tmp_path: Path) -> None:
        ws = tmp_path / "my_ws"
        ws.mkdir()
        install = ws / "install"
        install.mkdir()

        result = scan_for_workspaces(roots=[ws], include_home=False, include_opt_ros=False)
        assert len(result) == 1
        assert result[0].has_install is True

    def test_recursive_scan(self, tmp_path: Path) -> None:
        # Create workspace nested in directory
        parent = tmp_path / "projects"
        parent.mkdir()
        ws = parent / "ros_ws"
        ws.mkdir()
        (ws / "src").mkdir()

        result = scan_for_workspaces(
            roots=[parent], max_depth=2, include_home=False, include_opt_ros=False
        )
        assert len(result) == 1
        assert result[0].path == ws.resolve()

    def test_max_depth_limits_recursion(self, tmp_path: Path) -> None:
        # Create deeply nested workspace
        deep = tmp_path / "a" / "b" / "c" / "d" / "ws"
        deep.mkdir(parents=True)
        (deep / "src").mkdir()

        result = scan_for_workspaces(
            roots=[tmp_path], max_depth=2, include_home=False, include_opt_ros=False
        )
        # Should not find it (too deep)
        assert len(result) == 0

    def test_no_duplicates(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "src").mkdir()

        result = scan_for_workspaces(
            roots=[ws, ws, tmp_path],
            include_home=False,
            include_opt_ros=False,
        )
        # Should only appear once
        assert len(result) == 1


class TestFindPackagePath:
    """Tests for find_package_path."""

    def test_finds_in_extra_roots(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "my_pkg"
        pkg_dir.mkdir()
        pkg_xml = pkg_dir / "package.xml"
        pkg_xml.write_text("<package><name>my_pkg</name></package>")

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
            result = find_package_path("my_pkg", extra_source_roots=[tmp_path])
            assert result == pkg_xml

    def test_not_found(self, tmp_path: Path) -> None:
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
            result = find_package_path("nonexistent_pkg_xyz", extra_source_roots=[tmp_path])
            assert result is None


class TestListPackagePaths:
    """Tests for list_package_paths."""

    def test_with_extra_roots(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "test_pkg"
        pkg_dir.mkdir()
        pkg_xml = pkg_dir / "package.xml"
        pkg_xml.write_text("<package><name>test_pkg</name></package>")

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
            result = list_package_paths(extra_source_roots=[tmp_path])
            assert "test_pkg" in result
            assert result["test_pkg"] == pkg_xml


class TestListPackagesBySource:
    """Tests for list_packages_by_source."""

    def test_with_extra_roots(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "added_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "package.xml").write_text("<package><name>added_pkg</name></package>")

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
            result = list_packages_by_source(extra_source_roots=[tmp_path])
            # Should have an "Added" section
            added_key = [k for k in result.keys() if "Added" in k]
            assert len(added_key) == 1
            assert "added_pkg" in result[added_key[0]]

    def test_empty_env(self, tmp_path: Path) -> None:
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
            result = list_packages_by_source()
            # May be empty or have system packages
            assert isinstance(result, dict)

    def test_nonexistent_extra_root(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "does_not_exist"
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
            result = list_packages_by_source(extra_source_roots=[nonexistent])
            # Should not crash, just skip nonexistent path
            assert isinstance(result, dict)

    def test_with_ament_prefix_path(self, tmp_path: Path) -> None:
        # Create a mock install space
        install = tmp_path / "install"
        share = install / "share"
        pkg_share = share / "my_installed_pkg"
        pkg_share.mkdir(parents=True)
        (pkg_share / "package.xml").write_text("<package><name>my_installed_pkg</name></package>")

        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": str(install),
                "COLCON_PREFIX_PATH": "",
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = list_packages_by_source()
            # Should find the installed package
            all_pkgs = []
            for pkgs in result.values():
                all_pkgs.extend(pkgs)
            assert "my_installed_pkg" in all_pkgs


class TestScanForWorkspacesAdvanced:
    """Additional tests for scan_for_workspaces edge cases."""

    def test_workspace_with_share(self, tmp_path: Path) -> None:
        # Simulate /opt/ros style workspace with share dir
        ws = tmp_path / "ros_distro"
        share = ws / "share"
        pkg_share = share / "ros_pkg"
        pkg_share.mkdir(parents=True)
        (pkg_share / "package.xml").write_text("<package><name>ros_pkg</name></package>")

        result = scan_for_workspaces(roots=[ws], include_home=False, include_opt_ros=False)
        assert len(result) == 1
        assert result[0].has_install is True
        assert "ros_pkg" in result[0].packages

    def test_workspace_with_build(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "src").mkdir()
        (ws / "build").mkdir()

        result = scan_for_workspaces(roots=[ws], include_home=False, include_opt_ros=False)
        assert len(result) == 1
        assert result[0].has_build is True

    def test_hidden_dirs_skipped(self, tmp_path: Path) -> None:
        # Create hidden directory with workspace inside
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        ws = hidden / "ws"
        ws.mkdir()
        (ws / "src").mkdir()

        result = scan_for_workspaces(
            roots=[tmp_path], max_depth=3, include_home=False, include_opt_ros=False
        )
        # Should not find the workspace in hidden directory
        assert len(result) == 0


class TestFindPackagePathAdvanced:
    """Additional tests for find_package_path."""

    def test_finds_in_ament_prefix(self, tmp_path: Path) -> None:
        # Create a mock install space
        install = tmp_path / "install"
        share = install / "share"
        pkg_share = share / "ament_pkg"
        pkg_share.mkdir(parents=True)
        pkg_xml = pkg_share / "package.xml"
        pkg_xml.write_text("<package><name>ament_pkg</name></package>")

        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": str(install),
                "COLCON_PREFIX_PATH": "",
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = find_package_path("ament_pkg")
            assert result == pkg_xml


class TestListPackagePathsAdvanced:
    """Additional tests for list_package_paths."""

    def test_with_ament_prefix(self, tmp_path: Path) -> None:
        install = tmp_path / "install"
        share = install / "share"
        pkg_share = share / "list_pkg"
        pkg_share.mkdir(parents=True)
        pkg_xml = pkg_share / "package.xml"
        pkg_xml.write_text("<package><name>list_pkg</name></package>")

        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": str(install),
                "COLCON_PREFIX_PATH": "",
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = list_package_paths()
            assert "list_pkg" in result

    def test_skips_non_packages(self, tmp_path: Path) -> None:
        install = tmp_path / "install"
        share = install / "share"
        share.mkdir(parents=True)
        # Create a non-package directory
        non_pkg = share / "not_a_package"
        non_pkg.mkdir()
        # No package.xml

        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": str(install),
                "COLCON_PREFIX_PATH": "",
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = list_package_paths()
            assert "not_a_package" not in result


class TestScanWorkspacesHomeAndSystem:
    """Tests for scanning home and system directories."""

    def test_include_home(self) -> None:
        """Test scanning with include_home=True."""
        ws = scan_for_workspaces(
            roots=None,
            include_home=True,
            include_opt_ros=False,
            max_depth=1,
        )
        # Returns a list (may be empty depending on system)
        assert isinstance(ws, list)

    def test_include_opt_ros(self) -> None:
        """Test scanning with include_opt_ros=True."""
        ws = scan_for_workspaces(
            roots=None,
            include_home=False,
            include_opt_ros=True,
            max_depth=1,
        )
        # Returns a list (may be empty or include ROS distros)
        assert isinstance(ws, list)


class TestListPackagesInInstallEdgeCases:
    """Edge case tests for _list_packages_in_install."""

    def test_empty_share(self, tmp_path: Path) -> None:
        """Test with empty share directory."""
        install = tmp_path / "install"
        share = install / "share"
        share.mkdir(parents=True)
        # No packages

        result = _list_packages_in_install(install)
        assert result == []


class TestGatherWorkspaceSrcRootsEnv:
    """Test _gather_workspace_src_roots with various env setups."""

    def test_with_ros2_workspace_env(self, tmp_path: Path) -> None:
        """Test ROS2_WORKSPACE env variable."""
        ws = tmp_path / "ws"
        src = ws / "src"
        src.mkdir(parents=True)

        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": "",
                "COLCON_PREFIX_PATH": "",
                "ROS2_WORKSPACE": str(ws),
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = _gather_workspace_src_roots()
            # Should include the src directory
            assert src in result

    def test_with_colcon_workspace_env(self, tmp_path: Path) -> None:
        """Test COLCON_WORKSPACE env variable."""
        ws = tmp_path / "colcon_ws"
        src = ws / "src"
        src.mkdir(parents=True)

        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": "",
                "COLCON_PREFIX_PATH": "",
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": str(ws),
            },
            clear=False,
        ):
            result = _gather_workspace_src_roots()
            assert src in result

    def test_with_install_prefix(self, tmp_path: Path) -> None:
        """Test with COLCON_PREFIX_PATH pointing to install space subdirectory."""
        ws = tmp_path / "ws"
        install = ws / "install"
        install_lib = install / "lib"  # prefix is lib, parent.name is "install"
        src = install / "src"
        install_lib.mkdir(parents=True)
        src.mkdir(parents=True)

        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": "",
                "COLCON_PREFIX_PATH": str(install_lib),
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = _gather_workspace_src_roots()
            assert src in result


class TestListPackagesBySourceEnvCombinations:
    """Test list_packages_by_source with various environment configurations."""

    def test_with_system_prefix(self, tmp_path: Path) -> None:
        """Test that non-system prefix is correctly labeled."""
        install = tmp_path / "install"
        share = install / "share"
        pkg = share / "test_pkg"
        pkg.mkdir(parents=True)
        (pkg / "package.xml").write_text("<package><name>test_pkg</name></package>")

        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": str(install),
                "COLCON_PREFIX_PATH": "",
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = list_packages_by_source()
            # Should have the package in some source
            all_pkgs = [p for pkgs in result.values() for p in pkgs]
            assert "test_pkg" in all_pkgs

    def test_with_colcon_prefix_and_src(self, tmp_path: Path) -> None:
        """Test with COLCON_PREFIX_PATH and corresponding src directory."""
        ws = tmp_path / "ws"
        install = ws / "install"
        src = install / "src"  # src under install (as per the code logic)
        share = install / "share"
        install_lib = install / "lib"  # prefix is lib, parent.name is "install"

        install_lib.mkdir(parents=True)
        src.mkdir(parents=True)
        share.mkdir(parents=True)

        # Add package in src
        pkg_dir = src / "src_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "package.xml").write_text("<package><name>src_pkg</name></package>")

        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": "",
                "COLCON_PREFIX_PATH": str(install_lib),
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = list_packages_by_source()
            all_pkgs = [p for pkgs in result.values() for p in pkgs]
            assert "src_pkg" in all_pkgs

    def test_duplicate_packages_across_sources(self, tmp_path: Path) -> None:
        """Test that duplicate packages are only listed once."""
        # Create the same package in two places
        ws = tmp_path / "ws"
        install = ws / "install"
        src = ws / "src"
        share = install / "share"

        install.mkdir(parents=True)
        src.mkdir(parents=True)
        share.mkdir(parents=True)

        # Package in install
        installed = share / "dupe_pkg"
        installed.mkdir()
        (installed / "package.xml").write_text("<package><name>dupe_pkg</name></package>")

        # Same package in src
        src_pkg = src / "dupe_pkg"
        src_pkg.mkdir()
        (src_pkg / "package.xml").write_text("<package><name>dupe_pkg</name></package>")

        with mock.patch.dict(
            os.environ,
            {
                "AMENT_PREFIX_PATH": "",
                "COLCON_PREFIX_PATH": str(install),
                "ROS2_WORKSPACE": "",
                "COLCON_WORKSPACE": "",
            },
            clear=False,
        ):
            result = list_packages_by_source()
            # Count how many times dupe_pkg appears
            count = sum(1 for pkgs in result.values() for p in pkgs if p == "dupe_pkg")
            assert count == 1  # Only listed once


class TestFindPackageXmlInSrcOSError:
    """Test _find_package_xml_in_src with OS errors."""

    def test_oserror_during_read(self, tmp_path: Path) -> None:
        """Test handling of OS error when reading package.xml."""
        src = tmp_path / "src"
        pkg = src / "pkg"
        pkg.mkdir(parents=True)
        pkg_xml = pkg / "package.xml"
        pkg_xml.write_text("<package><name>pkg</name></package>")

        # Mock open to raise OSError
        with mock.patch("builtins.open", side_effect=OSError("Mock error")):
            result = _find_package_xml_in_src("pkg", [src])
            assert result is None


class TestWorkspaceRootFromPrefixEdgeCases:
    """Edge case tests for _workspace_root_from_prefix."""

    def test_install_directory_directly(self, tmp_path: Path) -> None:
        """Test with prefix pointing directly to an 'install' directory."""
        ws = tmp_path / "ws"
        install = ws / "install"
        install.mkdir(parents=True)

        result = _workspace_root_from_prefix(install)
        assert result == ws

    def test_nested_install(self, tmp_path: Path) -> None:
        """Test with nested install path."""
        ws = tmp_path / "ws"
        install = ws / "install"
        nested = install / "local"  # parent.name == install
        nested.mkdir(parents=True)

        result = _workspace_root_from_prefix(nested)
        # Should return ws since parent.name == "install"
        assert result == ws


class TestScanForWorkspacesPermission:
    """Tests for permission handling in scan_for_workspaces."""

    def test_handles_permission_error(self, tmp_path: Path) -> None:
        """Test that permission errors are handled gracefully."""
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "src").mkdir()

        # Mock iterdir to raise PermissionError
        original_iterdir = Path.iterdir

        def mock_iterdir(self):
            if "ws" in str(self):
                raise PermissionError("Mock permission error")
            return original_iterdir(self)

        with mock.patch.object(Path, "iterdir", mock_iterdir):
            # Should not raise
            result = scan_for_workspaces(
                roots=[tmp_path],
                max_depth=2,
                include_home=False,
                include_opt_ros=False,
            )
            assert isinstance(result, list)
