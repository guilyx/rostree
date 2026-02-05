"""Tests for rostree CLI."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from unittest import mock


from rostree.cli import cmd_scan, cmd_list, cmd_tree, main, _print_tree_text
from rostree.core.tree import DependencyNode


class TestPrintTreeText:
    """Tests for _print_tree_text helper."""

    def test_simple_node(self, capsys) -> None:
        node = DependencyNode(
            name="test_pkg",
            version="1.0.0",
            description="Test package",
            path="/path",
        )
        _print_tree_text(node)
        captured = capsys.readouterr()
        assert "test_pkg" in captured.out
        assert "1.0.0" in captured.out
        assert "Test package" in captured.out

    def test_node_with_children(self, capsys) -> None:
        child = DependencyNode(
            name="child",
            version="0.5",
            description="Child pkg",
            path="/child",
        )
        parent = DependencyNode(
            name="parent",
            version="2.0",
            description="Parent pkg",
            path="/parent",
            children=[child],
        )
        _print_tree_text(parent)
        captured = capsys.readouterr()
        assert "parent" in captured.out
        assert "child" in captured.out

    def test_not_found_node(self, capsys) -> None:
        node = DependencyNode(
            name="missing",
            version="",
            description="(not found)",
            path="",
        )
        _print_tree_text(node)
        captured = capsys.readouterr()
        assert "missing" in captured.out
        assert "(not found)" in captured.out

    def test_cycle_node(self, capsys) -> None:
        node = DependencyNode(
            name="cyclic",
            version="",
            description="(cycle)",
            path="",
        )
        _print_tree_text(node)
        captured = capsys.readouterr()
        assert "cyclic" in captured.out
        assert "(cycle)" in captured.out

    def test_parse_error_node(self, capsys) -> None:
        node = DependencyNode(
            name="bad",
            version="",
            description="(parse error)",
            path="/bad",
        )
        _print_tree_text(node)
        captured = capsys.readouterr()
        assert "(parse error)" in captured.out


class TestCmdScan:
    """Tests for cmd_scan command."""

    def test_no_args(self) -> None:
        args = argparse.Namespace(
            paths=None,
            depth=4,
            no_home=True,
            no_system=True,
            verbose=False,
            json=False,
        )
        result = cmd_scan(args)
        assert result == 0

    def test_with_paths(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "src").mkdir()

        args = argparse.Namespace(
            paths=[str(ws)],
            depth=2,
            no_home=True,
            no_system=True,
            verbose=False,
            json=False,
        )
        result = cmd_scan(args)
        assert result == 0

    def test_verbose(self, tmp_path: Path, capsys) -> None:
        ws = tmp_path / "ws"
        ws.mkdir()
        src = ws / "src"
        src.mkdir()
        # Add a package
        pkg = src / "my_pkg"
        pkg.mkdir()
        (pkg / "package.xml").write_text("<package><name>my_pkg</name></package>")

        args = argparse.Namespace(
            paths=[str(ws)],
            depth=2,
            no_home=True,
            no_system=True,
            verbose=True,
            json=False,
        )
        result = cmd_scan(args)
        captured = capsys.readouterr()
        assert result == 0
        assert "my_pkg" in captured.out

    def test_verbose_many_packages(self, tmp_path: Path, capsys) -> None:
        """Test verbose output truncation for workspaces with many packages."""
        ws = tmp_path / "ws"
        ws.mkdir()
        src = ws / "src"
        src.mkdir()
        # Add more than 20 packages
        for i in range(25):
            pkg = src / f"pkg_{i:02d}"
            pkg.mkdir()
            (pkg / "package.xml").write_text(f"<package><name>pkg_{i:02d}</name></package>")

        args = argparse.Namespace(
            paths=[str(ws)],
            depth=2,
            no_home=True,
            no_system=True,
            verbose=True,
            json=False,
        )
        result = cmd_scan(args)
        captured = capsys.readouterr()
        assert result == 0
        assert "and 5 more" in captured.out

    def test_json_output(self, tmp_path: Path, capsys) -> None:
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "src").mkdir()

        args = argparse.Namespace(
            paths=[str(ws)],
            depth=2,
            no_home=True,
            no_system=True,
            verbose=False,
            json=True,
        )
        result = cmd_scan(args)
        captured = capsys.readouterr()
        assert result == 0
        # Should be valid JSON (list)
        import json

        data = json.loads(captured.out)
        assert isinstance(data, list)

    def test_no_workspaces_found(self, tmp_path: Path, capsys) -> None:
        args = argparse.Namespace(
            paths=[str(tmp_path)],
            depth=1,
            no_home=True,
            no_system=True,
            verbose=False,
            json=False,
        )
        result = cmd_scan(args)
        captured = capsys.readouterr()
        assert result == 0
        assert "No ROS 2 workspaces found" in captured.out

    def test_workspace_with_install_only(self, tmp_path: Path, capsys) -> None:
        """Test workspace with only install directory."""
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "install").mkdir()

        args = argparse.Namespace(
            paths=[str(ws)],
            depth=2,
            no_home=True,
            no_system=True,
            verbose=False,
            json=False,
        )
        result = cmd_scan(args)
        captured = capsys.readouterr()
        assert result == 0
        assert "install" in captured.out

    def test_workspace_with_build(self, tmp_path: Path, capsys) -> None:
        """Test workspace status includes build."""
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "src").mkdir()
        (ws / "build").mkdir()

        args = argparse.Namespace(
            paths=[str(ws)],
            depth=2,
            no_home=True,
            no_system=True,
            verbose=False,
            json=False,
        )
        result = cmd_scan(args)
        captured = capsys.readouterr()
        assert result == 0
        assert "build" in captured.out


class TestCmdList:
    """Tests for cmd_list command."""

    def test_no_packages(self, capsys) -> None:
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
            args = argparse.Namespace(
                source=None,
                by_source=False,
                verbose=False,
                json=False,
            )
            result = cmd_list(args)
            assert result in (0, 1)

    def test_with_source(self, tmp_path: Path, capsys) -> None:
        pkg = tmp_path / "list_pkg"
        pkg.mkdir()
        (pkg / "package.xml").write_text("<package><name>list_pkg</name></package>")

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
            args = argparse.Namespace(
                source=[str(tmp_path)],
                by_source=False,
                verbose=False,
                json=False,
            )
            result = cmd_list(args)
            captured = capsys.readouterr()
            assert result == 0
            assert "list_pkg" in captured.out

    def test_by_source(self, tmp_path: Path, capsys) -> None:
        pkg = tmp_path / "source_pkg"
        pkg.mkdir()
        (pkg / "package.xml").write_text("<package><name>source_pkg</name></package>")

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
            args = argparse.Namespace(
                source=[str(tmp_path)],
                by_source=True,
                verbose=False,
                json=False,
            )
            result = cmd_list(args)
            captured = capsys.readouterr()
            assert result == 0
            # Without verbose, package names aren't shown, but Added section is
            assert "Added" in captured.out

    def test_by_source_verbose(self, tmp_path: Path, capsys) -> None:
        pkg = tmp_path / "verbose_pkg"
        pkg.mkdir()
        (pkg / "package.xml").write_text("<package><name>verbose_pkg</name></package>")

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
            args = argparse.Namespace(
                source=[str(tmp_path)],
                by_source=True,
                verbose=True,
                json=False,
            )
            result = cmd_list(args)
            captured = capsys.readouterr()
            assert result == 0
            assert "verbose_pkg" in captured.out

    def test_json_output(self, tmp_path: Path, capsys) -> None:
        pkg = tmp_path / "json_pkg"
        pkg.mkdir()
        (pkg / "package.xml").write_text("<package><name>json_pkg</name></package>")

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
            args = argparse.Namespace(
                source=[str(tmp_path)],
                by_source=False,
                verbose=False,
                json=True,
            )
            result = cmd_list(args)
            captured = capsys.readouterr()
            assert result == 0
            import json

            data = json.loads(captured.out)
            assert "json_pkg" in data

    def test_by_source_json(self, tmp_path: Path, capsys) -> None:
        pkg = tmp_path / "bsj_pkg"
        pkg.mkdir()
        (pkg / "package.xml").write_text("<package><name>bsj_pkg</name></package>")

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
            args = argparse.Namespace(
                source=[str(tmp_path)],
                by_source=True,
                verbose=False,
                json=True,
            )
            result = cmd_list(args)
            captured = capsys.readouterr()
            assert result == 0
            import json

            data = json.loads(captured.out)
            assert isinstance(data, dict)

    def test_verbose_list(self, tmp_path: Path, capsys) -> None:
        pkg = tmp_path / "vlist_pkg"
        pkg.mkdir()
        (pkg / "package.xml").write_text("<package><name>vlist_pkg</name></package>")

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
            args = argparse.Namespace(
                source=[str(tmp_path)],
                by_source=False,
                verbose=True,
                json=False,
            )
            result = cmd_list(args)
            captured = capsys.readouterr()
            assert result == 0
            # Verbose shows path
            assert "vlist_pkg" in captured.out

    def test_by_source_many_packages(self, tmp_path: Path, capsys) -> None:
        """Test by-source verbose with many packages (>50 truncation)."""
        # Create 55 packages
        for i in range(55):
            pkg = tmp_path / f"pkg_{i:02d}"
            pkg.mkdir()
            (pkg / "package.xml").write_text(f"<package><name>pkg_{i:02d}</name></package>")

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
            args = argparse.Namespace(
                source=[str(tmp_path)],
                by_source=True,
                verbose=True,
                json=False,
            )
            result = cmd_list(args)
            captured = capsys.readouterr()
            assert result == 0
            assert "and 5 more" in captured.out

    def test_by_source_output_format(self, tmp_path: Path, capsys) -> None:
        """Test by-source output format."""
        pkg = tmp_path / "format_pkg"
        pkg.mkdir()
        (pkg / "package.xml").write_text("<package><name>format_pkg</name></package>")

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
            args = argparse.Namespace(
                source=[str(tmp_path)],
                by_source=True,
                verbose=False,
                json=False,
            )
            result = cmd_list(args)
            captured = capsys.readouterr()
            assert result == 0
            assert "package(s)" in captured.out
            assert "source(s)" in captured.out

    def test_by_source_empty_returns_error(self, capsys) -> None:
        """Test by-source returns 1 when no packages found."""
        # Mock list_packages_by_source to return empty
        with mock.patch("rostree.cli.list_packages_by_source", return_value={}):
            args = argparse.Namespace(
                source=None,
                by_source=True,
                verbose=False,
                json=False,
            )
            result = cmd_list(args)
            captured = capsys.readouterr()
            assert result == 1
            assert "No packages found" in captured.out

    def test_no_packages_found_non_by_source(self, capsys) -> None:
        """Test list without by_source returns 1 when no packages found."""
        with mock.patch("rostree.cli.list_package_paths", return_value={}):
            args = argparse.Namespace(
                source=None,
                by_source=False,
                verbose=False,
                json=False,
            )
            result = cmd_list(args)
            captured = capsys.readouterr()
            assert result == 1
            assert "No packages found" in captured.out


class TestCmdTree:
    """Tests for cmd_tree command."""

    def test_package_not_found(self, capsys) -> None:
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
            args = argparse.Namespace(
                package="nonexistent_xyz",
                depth=None,
                runtime=False,
                source=None,
                json=False,
            )
            result = cmd_tree(args)
            captured = capsys.readouterr()
            # Returns 0 because tree is built with "(not found)"
            assert result == 0
            assert "nonexistent_xyz" in captured.out

    def test_tree_returns_none(self, capsys) -> None:
        """Test error handling when build_dependency_tree returns None."""
        with mock.patch("rostree.cli.build_dependency_tree", return_value=None):
            args = argparse.Namespace(
                package="any_pkg",
                depth=None,
                runtime=False,
                source=None,
                json=False,
            )
            result = cmd_tree(args)
            captured = capsys.readouterr()
            assert result == 1
            assert "not found" in captured.err.lower()

    def test_with_source(self, tmp_path: Path, capsys) -> None:
        pkg = tmp_path / "tree_pkg"
        pkg.mkdir()
        (pkg / "package.xml").write_text(
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
            args = argparse.Namespace(
                package="tree_pkg",
                depth=None,
                runtime=False,
                source=[str(tmp_path)],
                json=False,
            )
            result = cmd_tree(args)
            captured = capsys.readouterr()
            assert result == 0
            assert "tree_pkg" in captured.out

    def test_json_output(self, tmp_path: Path, capsys) -> None:
        pkg = tmp_path / "json_tree"
        pkg.mkdir()
        (pkg / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
    <name>json_tree</name>
    <version>2.0.0</version>
    <description>JSON test</description>
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
            args = argparse.Namespace(
                package="json_tree",
                depth=None,
                runtime=False,
                source=[str(tmp_path)],
                json=True,
            )
            result = cmd_tree(args)
            captured = capsys.readouterr()
            assert result == 0
            import json

            data = json.loads(captured.out)
            assert data["name"] == "json_tree"

    def test_with_depth(self, tmp_path: Path) -> None:
        pkg = tmp_path / "depth_tree"
        pkg.mkdir()
        (pkg / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
    <name>depth_tree</name>
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
            args = argparse.Namespace(
                package="depth_tree",
                depth=2,
                runtime=False,
                source=[str(tmp_path)],
                json=False,
            )
            result = cmd_tree(args)
            assert result == 0

    def test_runtime_only(self, tmp_path: Path) -> None:
        pkg = tmp_path / "runtime_tree"
        pkg.mkdir()
        (pkg / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
    <name>runtime_tree</name>
    <version>1.0.0</version>
    <description>Runtime test</description>
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
            args = argparse.Namespace(
                package="runtime_tree",
                depth=None,
                runtime=True,
                source=[str(tmp_path)],
                json=False,
            )
            result = cmd_tree(args)
            assert result == 0


class TestMain:
    """Tests for main entry point."""

    def test_version(self, capsys) -> None:
        try:
            main(["--version"])
        except SystemExit as e:
            assert e.code == 0
        captured = capsys.readouterr()
        assert "0.1.0" in captured.out

    def test_help(self, capsys) -> None:
        try:
            main(["--help"])
        except SystemExit as e:
            assert e.code == 0
        captured = capsys.readouterr()
        assert "rostree" in captured.out
        assert "scan" in captured.out
        assert "list" in captured.out
        assert "tree" in captured.out
        assert "tui" in captured.out

    def test_scan_help(self, capsys) -> None:
        try:
            main(["scan", "--help"])
        except SystemExit as e:
            assert e.code == 0
        captured = capsys.readouterr()
        assert "scan" in captured.out
        assert "--depth" in captured.out

    def test_list_help(self, capsys) -> None:
        try:
            main(["list", "--help"])
        except SystemExit as e:
            assert e.code == 0
        captured = capsys.readouterr()
        assert "list" in captured.out
        assert "--by-source" in captured.out

    def test_tree_help(self, capsys) -> None:
        try:
            main(["tree", "--help"])
        except SystemExit as e:
            assert e.code == 0
        captured = capsys.readouterr()
        assert "tree" in captured.out
        assert "--runtime" in captured.out

    def test_scan_command(self) -> None:
        # Run scan with no home/system to be fast
        result = main(["scan", "--no-home", "--no-system"])
        assert result == 0

    def test_list_command(self) -> None:
        result = main(["list", "--json"])
        assert result in (0, 1)  # May have no packages

    def test_tree_command(self) -> None:
        result = main(["tree", "nonexistent_test_pkg"])
        assert result == 0  # Returns placeholder node
