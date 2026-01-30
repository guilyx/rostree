"""Public API: use rosdep_viz from Python or from other tools."""

from __future__ import annotations

from pathlib import Path

from rosdep_viz.core.finder import find_package_path, list_package_paths
from rosdep_viz.core.parser import parse_package_xml, PackageInfo
from rosdep_viz.core.tree import DependencyNode, build_dependency_tree


def list_known_packages() -> dict[str, Path]:
    """
    List all ROS 2 packages visible in the current environment.

    Uses AMENT_PREFIX_PATH, COLCON_PREFIX_PATH, and workspace source trees.
    Returns a mapping from package name to path to its package.xml.
    """
    return list_package_paths()


def get_package_info(package_name: str) -> PackageInfo | None:
    """
    Get metadata and dependencies for a ROS 2 package by name.

    Finds the package (install or source) and parses its package.xml.
    Returns None if the package is not found or package.xml cannot be parsed.
    """
    path = find_package_path(package_name)
    if path is None:
        return None
    return parse_package_xml(path)


def build_tree(
    root_package: str,
    *,
    max_depth: int | None = None,
    include_buildtool: bool = False,
) -> DependencyNode | None:
    """
    Build a full dependency tree for a ROS 2 package.

    Args:
        root_package: Name of the root package.
        max_depth: Optional maximum depth; None = unlimited.
        include_buildtool: Whether to include buildtool dependencies.

    Returns:
        Root DependencyNode, or None if root package is not found.
    """
    return build_dependency_tree(
        root_package,
        max_depth=max_depth,
        include_buildtool=include_buildtool,
    )
