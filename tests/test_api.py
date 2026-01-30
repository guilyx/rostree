"""Tests for public API (smoke tests; full tests require ROS env)."""

from unittest.mock import patch


from rosdep_viz import build_tree, list_known_packages
from rosdep_viz.core.tree import DependencyNode


def test_list_known_packages_returns_dict() -> None:
    result = list_known_packages()
    assert isinstance(result, dict)
    for k, v in result.items():
        assert isinstance(k, str)
        assert hasattr(v, "exists")  # Path-like


def test_build_tree_nonexistent() -> None:
    with patch("rosdep_viz.core.finder.find_package_path", return_value=None):
        root = build_tree("nonexistent_package_xyz_123")
        assert root is not None
        assert root.name == "nonexistent_package_xyz_123"
        assert root.path == ""


def test_dependency_node_to_dict() -> None:
    node = DependencyNode("pkg", "1.0", "desc", "/path", [])
    d = node.to_dict()
    assert d["name"] == "pkg"
    assert d["version"] == "1.0"
    assert d["description"] == "desc"
    assert d["path"] == "/path"
    assert d["children"] == []
