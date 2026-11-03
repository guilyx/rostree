"""
Public API: use rostree from Python or from other tools.

Everything named in ``__all__`` follows semantic versioning from 1.0. The CLI is
built on these same functions, so anything ``rostree`` can tell you on the
command line, a script can ask for directly — no parsing of terminal output.

Every function that walks the graph takes the same scope arguments as the CLI:

- ``dep_type``: ``"runtime"``, ``"build"``, ``"test"`` or ``"all"`` (the default).
  ``runtime_only=True`` is the older spelling of ``dep_type="runtime"``.
- ``package_filter``: a :class:`PackageFilter` (include/exclude globs, workspace
  only). A filtered-out package is neither returned nor followed.
- ``report``: pass a :class:`FilterReport` to learn what the filter removed.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from rostree.core.analysis import (
    DependencyDiff,
    dependency_versions,
    dependents,
    diff_dependencies,
    shortest_paths,
)
from rostree.core.filters import (
    DEP_TYPE_CHOICES,
    FilterReport,
    PackageFilter,
    tags_for_dep_type,
)
from rostree.core.finder import (
    WorkspaceInfo,
    find_package_path,
    list_package_paths,
    list_packages_by_source,
    scan_for_workspaces,
)
from rostree.core.graph import GraphView, to_dot, to_mermaid
from rostree.core.index import PackageEntry, PackageIndex, SourceKind, get_index
from rostree.core.parser import RUNTIME_DEPENDENCY_TAGS, PackageInfo, parse_package_xml
from rostree.core.tree import (
    DependencyGraph,
    DependencyNode,
    NodeStatus,
    build_dependency_graph,
    build_dependency_tree,
    tree_stats,
)

__all__ = [
    # data
    "DependencyDiff",
    "DependencyGraph",
    "DependencyNode",
    "FilterReport",
    "GraphView",
    "NodeStatus",
    "PackageEntry",
    "PackageFilter",
    "PackageIndex",
    "PackageInfo",
    "SourceKind",
    "WorkspaceInfo",
    "DEP_TYPE_CHOICES",
    # discovery
    "get_index",
    "get_package_info",
    "list_known_packages",
    "list_known_packages_by_source",
    "scan_workspaces",
    # the graph
    "build_graph",
    "build_tree",
    "tree_stats",
    # questions about it
    "dependency_paths",
    "dependency_versions",
    "diff_dependencies",
    "reverse_dependencies",
    # rendering
    "to_dot",
    "to_html",
    "to_mermaid",
]


def _tags(*, runtime_only: bool, dep_type: str | None) -> tuple[str, ...] | None:
    """One answer for "which dependency tags", from either spelling of the scope."""
    if dep_type is not None:
        return tags_for_dep_type(dep_type)  # raises ValueError on an unknown name
    return RUNTIME_DEPENDENCY_TAGS if runtime_only else None


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
    dep_type: str | None = None,
    package_filter: PackageFilter | None = None,
    report: FilterReport | None = None,
    max_nodes: int | None = None,
    index: PackageIndex | None = None,
) -> DependencyNode | None:
    """
    Build a renderable dependency tree for a ROS 2 package.

    Args:
        root_package: Name of the root package.
        max_depth: Optional maximum depth; None = unlimited.
        include_buildtool: **Has no effect**, and never has: ``buildtool_depend``
            entries are build tooling (ament_cmake, ament_python) and are not
            traversed. Passing ``True`` warns; the parameter goes in 2.0.
        runtime_only: Older spelling of ``dep_type="runtime"``.
        extra_source_roots: Optional list of Paths to scan for packages (user-added).
        collapse_repeats: If True (default), a package that appears more than once is
            expanded where it first appears and marked ``NodeStatus.REPEAT`` elsewhere.
            Set to False for a fully expanded tree, which can be exponentially large.
        dep_type: ``"runtime"``, ``"build"``, ``"test"`` or ``"all"``.
        package_filter: Leave out (and do not follow) what this filter rejects.
        report: Collects what ``package_filter`` removed.
        max_nodes: Stop after this many nodes — a safety valve for ``collapse_repeats=False``.
        index: Reuse a :class:`PackageIndex` instead of the process-wide cached one.

    Returns:
        Root DependencyNode, or None if root package is not found.
    """
    if include_buildtool:
        warnings.warn(
            "build_tree(include_buildtool=True) has no effect: buildtool_depend "
            "entries are never traversed. The parameter will be removed in 2.0.",
            DeprecationWarning,
            stacklevel=2,
        )
    return build_dependency_tree(
        root_package,
        max_depth=max_depth,
        include_tags=_tags(runtime_only=runtime_only, dep_type=dep_type),
        extra_source_roots=extra_source_roots,
        collapse_repeats=collapse_repeats,
        package_filter=package_filter,
        report=report,
        max_nodes=max_nodes,
        index=index,
    )


def build_graph(
    root_packages: str | list[str],
    *,
    max_depth: int | None = None,
    runtime_only: bool = False,
    extra_source_roots: list[Path] | None = None,
    dep_type: str | None = None,
    package_filter: PackageFilter | None = None,
    report: FilterReport | None = None,
    index: PackageIndex | None = None,
) -> DependencyGraph:
    """
    Resolve the dependency DAG reachable from one or more packages.

    Linear in the number of reachable packages, so it stays cheap on workspaces
    where a fully expanded tree would not. Use it for graphs, metrics, checks, and
    as the input to :func:`dependency_paths`, :func:`dependency_versions`,
    :func:`to_dot`, :func:`to_mermaid` and :func:`to_html`.
    """
    return build_dependency_graph(
        root_packages,
        max_depth=max_depth,
        include_tags=_tags(runtime_only=runtime_only, dep_type=dep_type),
        extra_source_roots=extra_source_roots,
        package_filter=package_filter,
        report=report,
        index=index,
    )


def reverse_dependencies(
    package: str,
    *,
    runtime_only: bool = False,
    extra_source_roots: list[Path] | None = None,
    transitive: bool = False,
    dep_type: str | None = None,
    package_filter: PackageFilter | None = None,
    report: FilterReport | None = None,
    index: PackageIndex | None = None,
) -> list[str]:
    """
    The packages that depend on ``package`` — "what breaks if this changes?"

    Directly by default; ``transitive=True`` follows every chain. Reads every
    visible manifest once and caches the result on the package index. Unlike the
    other functions here, ``package_filter`` is applied to the answer rather than
    the walk, so excluding a package never hides the dependents behind it.
    """
    if index is None:
        index = get_index(extra_source_roots=extra_source_roots)
    return dependents(
        index,
        package,
        transitive=transitive,
        include_tags=_tags(runtime_only=runtime_only, dep_type=dep_type),
        package_filter=package_filter,
        report=report,
    )


def dependency_paths(
    package: str,
    dependency: str,
    *,
    limit: int = 10,
    max_depth: int | None = None,
    runtime_only: bool = False,
    extra_source_roots: list[Path] | None = None,
    dep_type: str | None = None,
    package_filter: PackageFilter | None = None,
    report: FilterReport | None = None,
    index: PackageIndex | None = None,
) -> list[list[str]]:
    """
    Why does ``package`` depend on ``dependency``? The shortest paths, up to ``limit``.

    The library form of ``rostree why``. Each path starts at ``package`` and ends
    at ``dependency``; an empty list means it does not depend on it (within
    ``max_depth`` and the given scope). Already have a graph? Use
    :func:`rostree.core.analysis.shortest_paths` on it directly.
    """
    graph = build_graph(
        package,
        max_depth=max_depth,
        runtime_only=runtime_only,
        extra_source_roots=extra_source_roots,
        dep_type=dep_type,
        package_filter=package_filter,
        report=report,
        index=index,
    )
    return shortest_paths(graph, package, dependency, limit=limit)


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


def to_html(
    graph: DependencyGraph,
    *,
    index: PackageIndex | None = None,
    title: str | None = None,
    show_missing: bool = True,
    subtitle: str | None = None,
) -> str:
    """
    Render a graph as the self-contained interactive HTML viewer.

    One file, nothing external: write it to disk and open it in any browser,
    offline. Pass the ``index`` the graph was built from so packages are coloured
    by where they come from.
    """
    # Imported here: it reads the packaged web assets, which no other API needs.
    from rostree.core.webview import to_html as _to_html

    return _to_html(graph, index=index, title=title, show_missing=show_missing, subtitle=subtitle)
