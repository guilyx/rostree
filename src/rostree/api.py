"""Public API: use rostree from Python or from other tools."""

from __future__ import annotations

from pathlib import Path

from rostree.core.finder import (
    find_package_path,
    list_package_paths,
    list_packages_by_source,
    scan_for_workspaces,
    WorkspaceInfo,
)
from rostree.core.parser import parse_package_xml, PackageInfo
from rostree.core.tree import DependencyNode, build_dependency_tree


def list_known_packages(
    *,
    extra_source_roots: list[Path] | None = None,
) -> dict[str, Path]:
    """
    List all ROS 2 packages visible in the current environment.

    Uses AMENT_PREFIX_PATH, COLCON_PREFIX_PATH, workspace source trees,
    and optional extra_source_roots (user-added paths).
    Returns a mapping from package name to path to its package.xml.
    """
    return list_package_paths(extra_source_roots=extra_source_roots)


def list_known_packages_by_source(
    *,
    extra_source_roots: list[Path] | None = None,
) -> dict[str, list[str]]:
    """
    List packages grouped by source (System, Workspace, Other, Source, Added).

    Lets you distinguish your workspace packages from ROS distro (System),
    third-party (Other), unbuilt source (Source), and user-added (Added).
    Returns dict mapping source_label -> sorted list of package names.
    """
    return list_packages_by_source(extra_source_roots=extra_source_roots)


def get_package_info(
    package_name: str,
    *,
    extra_source_roots: list[Path] | None = None,
) -> PackageInfo | None:
    """
    Get metadata and dependencies for a ROS 2 package by name.

    Finds the package (install or source) and parses its package.xml.
    Returns None if the package is not found or package.xml cannot be parsed.
    """
    path = find_package_path(package_name, extra_source_roots=extra_source_roots)
    if path is None:
        return None
    return parse_package_xml(path)


def build_tree(
    root_package: str,
    *,
    max_depth: int | None = None,
    include_buildtool: bool = False,
    runtime_only: bool = False,
    extra_source_roots: list[Path] | None = None,
) -> DependencyNode | None:
    """
    Build a full dependency tree for a ROS 2 package.

    Args:
        root_package: Name of the root package.
        max_depth: Optional maximum depth; None = unlimited.
        include_buildtool: Whether to include buildtool dependencies.
        runtime_only: If True, only depend and exec_depend (faster, smaller tree).
        extra_source_roots: Optional list of Paths to scan for packages (user-added).

    Returns:
        Root DependencyNode, or None if root package is not found.
    """
    return build_dependency_tree(
        root_package,
        max_depth=max_depth,
        include_buildtool=include_buildtool,
        runtime_only=runtime_only,
        extra_source_roots=extra_source_roots,
    )


def scan_workspaces(
    roots: list[Path] | None = None,
    *,
    max_depth: int = 4,
    include_home: bool = True,
    include_opt_ros: bool = True,
) -> list[WorkspaceInfo]:
    """
    Scan the host machine for ROS 2 workspaces.

    Args:
        roots: Directories to start scanning from. Defaults to common locations.
        max_depth: How deep to recurse when looking for workspaces.
        include_home: If True and roots is None, include ~/ros*_ws, etc.
        include_opt_ros: If True and roots is None, include /opt/ros/* distros.

    Returns:
        List of WorkspaceInfo for each discovered workspace.
    """
    return scan_for_workspaces(
        roots=roots,
        max_depth=max_depth,
        include_home=include_home,
        include_opt_ros=include_opt_ros,
    )
