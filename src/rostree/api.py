"""Public API: use rostree from Python or from other tools."""

from __future__ import annotations

from pathlib import Path

from rostree.core.finder import (
    WorkspaceInfo,
    find_package_path,
    list_package_paths,
    list_packages_by_source,
    scan_for_workspaces,
)
from rostree.core.index import PackageEntry, PackageIndex, SourceKind, get_index
from rostree.core.parser import PackageInfo, parse_package_xml
from rostree.core.tree import (
    DependencyGraph,
    DependencyNode,
    NodeStatus,
    build_dependency_graph,
    build_dependency_tree,
    tree_stats,
)

__all__ = [
    "DependencyGraph",
    "DependencyNode",
    "NodeStatus",
    "PackageEntry",
    "PackageIndex",
    "PackageInfo",
    "SourceKind",
    "WorkspaceInfo",
    "build_graph",
    "build_tree",
    "get_index",
    "get_package_info",
    "list_known_packages",
    "list_known_packages_by_source",
    "reverse_dependencies",
    "scan_workspaces",
    "tree_stats",
]


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
    collapse_repeats: bool = True,
) -> DependencyNode | None:
    """
    Build a full dependency tree for a ROS 2 package.

    Args:
        root_package: Name of the root package.
        max_depth: Optional maximum depth; None = unlimited.
        include_buildtool: Whether to include buildtool dependencies.
        runtime_only: If True, only depend and exec_depend (faster, smaller tree).
        extra_source_roots: Optional list of Paths to scan for packages (user-added).
        collapse_repeats: If True (default), a package that appears more than once is
            expanded where it first appears and marked ``NodeStatus.REPEAT`` elsewhere.
            Set to False for a fully expanded tree, which can be exponentially large.

    Returns:
        Root DependencyNode, or None if root package is not found.
    """
    return build_dependency_tree(
        root_package,
        max_depth=max_depth,
        include_buildtool=include_buildtool,
        runtime_only=runtime_only,
        extra_source_roots=extra_source_roots,
        collapse_repeats=collapse_repeats,
    )


def build_graph(
    root_packages: str | list[str],
    *,
    max_depth: int | None = None,
    runtime_only: bool = False,
    extra_source_roots: list[Path] | None = None,
) -> DependencyGraph:
    """
    Resolve the dependency DAG reachable from one or more packages.

    Linear in the number of reachable packages, so it stays cheap on workspaces
    where a fully expanded tree would not. Use it for graphs, metrics and checks.
    """
    return build_dependency_graph(
        root_packages,
        max_depth=max_depth,
        runtime_only=runtime_only,
        extra_source_roots=extra_source_roots,
    )


def reverse_dependencies(
    package: str,
    *,
    runtime_only: bool = False,
    extra_source_roots: list[Path] | None = None,
) -> list[str]:
    """
    Return the packages that directly depend on ``package``.

    Reads every visible manifest once and caches the result on the package index.
    """
    index = get_index(extra_source_roots=extra_source_roots)
    tags = ("depend", "exec_depend") if runtime_only else None
    return sorted(index.reverse_dependencies(include_tags=tags).get(package, ()))


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
