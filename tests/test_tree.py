"""Tests for rostree.core.tree module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock


from rostree.core.tree import DependencyNode, build_dependency_tree


class TestDependencyNode:
    """Tests for DependencyNode dataclass."""

    def test_basic_creation(self) -> None:
        node = DependencyNode(
            name="test_pkg",
            version="1.0.0",
            description="A test package",
            path="/path/to/pkg",
        )
        assert node.name == "test_pkg"
        assert node.version == "1.0.0"
        assert node.description == "A test package"
        assert node.path == "/path/to/pkg"
        assert node.children == []
        assert node.package_info is None

    def test_to_dict_no_children(self) -> None:
        node = DependencyNode(
            name="pkg",
            version="2.0",
            description="desc",
            path="/path",
        )
        d = node.to_dict()
        assert d == {
            "name": "pkg",
            "version": "2.0",
            "description": "desc",
            "path": "/path",
            "children": [],
        }

    def test_to_dict_with_children(self) -> None:
        child = DependencyNode(
            name="child_pkg",
            version="1.0",
            description="child",
            path="/child",
        )
        parent = DependencyNode(
            name="parent_pkg",
            version="2.0",
            description="parent",
            path="/parent",
            children=[child],
        )
        d = parent.to_dict()
        assert d["name"] == "parent_pkg"
        assert len(d["children"]) == 1
        assert d["children"][0]["name"] == "child_pkg"


class TestBuildDependencyTree:
    """Tests for build_dependency_tree function."""

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
            result = build_dependency_tree(
                "nonexistent_pkg_xyz",
                extra_source_roots=[tmp_path],
            )
            assert result is not None
            assert result.name == "nonexistent_pkg_xyz"
            assert result.description == "(not found)"

    def test_simple_package_no_deps(self, tmp_path: Path) -> None:
        # Create a simple package with no dependencies
        pkg_dir = tmp_path / "simple_pkg"
        pkg_dir.mkdir()
        pkg_xml = pkg_dir / "package.xml"
        pkg_xml.write_text(
            """<?xml version="1.0"?>
<package format="3">
    <name>simple_pkg</name>
    <version>1.2.3</version>
    <description>A simple package</description>
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
            result = build_dependency_tree(
                "simple_pkg",
                extra_source_roots=[tmp_path],
            )
            assert result is not None
            assert result.name == "simple_pkg"
            assert result.version == "1.2.3"
            assert result.description == "A simple package"
            assert result.children == []

    def test_package_with_deps(self, tmp_path: Path) -> None:
        # Create parent package
        parent_dir = tmp_path / "parent_pkg"
        parent_dir.mkdir()
        (parent_dir / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
    <name>parent_pkg</name>
    <version>1.0.0</version>
    <description>Parent</description>
    <depend>child_pkg</depend>
</package>
"""
        )
        # Create child package
        child_dir = tmp_path / "child_pkg"
        child_dir.mkdir()
        (child_dir / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
    <name>child_pkg</name>
    <version>0.5.0</version>
    <description>Child</description>
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
            result = build_dependency_tree(
                "parent_pkg",
                extra_source_roots=[tmp_path],
            )
            assert result is not None
            assert result.name == "parent_pkg"
            assert len(result.children) == 1
            assert result.children[0].name == "child_pkg"
            assert result.children[0].version == "0.5.0"

    def test_max_depth_zero(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
    <name>pkg</name>
    <version>1.0</version>
    <description>Test</description>
    <depend>other_pkg</depend>
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
            result = build_dependency_tree(
                "pkg",
                max_depth=0,
                extra_source_roots=[tmp_path],
            )
            # Root is at depth 0, so it should be returned
            assert result is not None
            assert result.name == "pkg"
            # Children would be at depth 1, but max_depth=0 means they return None
            # However, the child is still added but the recursion for grandchildren stops
            # Actually, looking at the code: if _depth > max_depth, return None
            # So at _depth=0, max_depth=0, 0 > 0 is False, so root is built
            # Children are called with _depth=1, max_depth=0, 1 > 0 is True, return None
            assert result.children == []

    def test_max_depth_one(self, tmp_path: Path) -> None:
        # Create chain: pkg -> child -> grandchild
        for name in ["pkg", "child", "grandchild"]:
            d = tmp_path / name
            d.mkdir()
        (tmp_path / "pkg" / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
    <name>pkg</name>
    <version>1.0</version>
    <description>Root</description>
    <depend>child</depend>
</package>
"""
        )
        (tmp_path / "child" / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
    <name>child</name>
    <version>1.0</version>
    <description>Child</description>
    <depend>grandchild</depend>
</package>
"""
        )
        (tmp_path / "grandchild" / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
    <name>grandchild</name>
    <version>1.0</version>
    <description>Grandchild</description>
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
            result = build_dependency_tree(
                "pkg",
                max_depth=1,
                extra_source_roots=[tmp_path],
            )
            assert result is not None
            assert len(result.children) == 1
            assert result.children[0].name == "child"
            # Grandchild should not be included (depth 2 > max_depth 1)
            assert result.children[0].children == []

    def test_cycle_detection(self, tmp_path: Path) -> None:
        # Create cycle: pkg_a -> pkg_b -> pkg_a
        (tmp_path / "pkg_a").mkdir()
        (tmp_path / "pkg_b").mkdir()
        (tmp_path / "pkg_a" / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
    <name>pkg_a</name>
    <version>1.0</version>
    <description>A</description>
    <depend>pkg_b</depend>
</package>
"""
        )
        (tmp_path / "pkg_b" / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
    <name>pkg_b</name>
    <version>1.0</version>
    <description>B</description>
    <depend>pkg_a</depend>
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
            result = build_dependency_tree(
                "pkg_a",
                extra_source_roots=[tmp_path],
            )
            assert result is not None
            assert result.name == "pkg_a"
            assert len(result.children) == 1
            assert result.children[0].name == "pkg_b"
            # pkg_b's dep on pkg_a should be marked as cycle
            assert len(result.children[0].children) == 1
            assert result.children[0].children[0].name == "pkg_a"
            assert result.children[0].children[0].description == "(cycle)"

    def test_runtime_only(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
    <name>pkg</name>
    <version>1.0</version>
    <description>Test</description>
    <depend>runtime_dep</depend>
    <exec_depend>exec_dep</exec_depend>
    <build_depend>build_dep</build_depend>
    <test_depend>test_dep</test_depend>
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
            result = build_dependency_tree(
                "pkg",
                runtime_only=True,
                extra_source_roots=[tmp_path],
            )
            assert result is not None
            # Should only have runtime_dep and exec_dep (not build_dep or test_dep)
            child_names = [c.name for c in result.children]
            assert "runtime_dep" in child_names
            assert "exec_dep" in child_names
            assert "build_dep" not in child_names
            assert "test_dep" not in child_names

    def test_invalid_package_xml(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "bad_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "package.xml").write_text("not valid xml <<<")

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
            # This will find the file but fail to parse it
            # The finder finds based on name inside XML, so it won't find "bad_pkg"
            result = build_dependency_tree(
                "bad_pkg",
                extra_source_roots=[tmp_path],
            )
            # Since finder can't match the name, it returns not found
            assert result is not None
            assert result.description == "(not found)"

    def test_parse_error_returns_node(self, tmp_path: Path) -> None:
        """Test that parse error returns a DependencyNode with (parse error) description."""
        pkg_dir = tmp_path / "parseerr_pkg"
        pkg_dir.mkdir()
        pkg_xml = pkg_dir / "package.xml"
        pkg_xml.write_text("<package><name>parseerr_pkg</name></package>")

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
            # Mock parse_package_xml to return None (simulate parse failure)
            with mock.patch("rostree.core.tree.parse_package_xml", return_value=None):
                result = build_dependency_tree(
                    "parseerr_pkg",
                    extra_source_roots=[tmp_path],
                )
                assert result is not None
                assert result.name == "parseerr_pkg"
                assert result.description == "(parse error)"
                assert str(pkg_xml) in result.path
