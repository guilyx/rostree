"""Build and represent ROS 2 package dependency trees."""

from __future__ import annotations

from dataclasses import dataclass, field

from rosdep_viz.core.parser import PackageInfo, parse_package_xml
from rosdep_viz.core.finder import find_package_path


@dataclass
class DependencyNode:
    """A node in the dependency tree: one ROS package and its direct children."""

    name: str
    version: str
    description: str
    path: str
    children: list[DependencyNode] = field(default_factory=list)
    # Optional: store raw PackageInfo for API consumers
    package_info: PackageInfo | None = None

    def to_dict(self) -> dict:
        """Serialize node to a JSON-friendly dict (for API/frontend)."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "path": str(self.path),
            "children": [c.to_dict() for c in self.children],
        }


def build_dependency_tree(
    root_package: str,
    *,
    max_depth: int | None = None,
    include_buildtool: bool = False,
    _depth: int = 0,
    _visited: set[str] | None = None,
) -> DependencyNode | None:
    """
    Build a dependency tree starting from a root package name.

    Traverses depend/exec_depend/build_depend (and optionally buildtool) and
    resolves each dependency to its package.xml, then recurses. Cycles are
    avoided by tracking visited package names.

    Args:
        root_package: Root ROS package name.
        max_depth: Optional max depth; None means no limit.
        include_buildtool: If True, include buildtool_depend in traversal.
        _depth: Internal recursion depth.
        _visited: Internal set of already-visited package names.

    Returns:
        DependencyNode for the root, or None if root package is not found.
    """
    if _visited is None:
        _visited = set()
    if root_package in _visited:
        return DependencyNode(
            name=root_package,
            version="",
            description="(cycle)",
            path="",
        )
    if max_depth is not None and _depth > max_depth:
        return None

    pkg_path = find_package_path(root_package)
    if pkg_path is None:
        return DependencyNode(
            name=root_package,
            version="",
            description="(not found)",
            path="",
        )

    info = parse_package_xml(pkg_path)
    if info is None:
        return DependencyNode(
            name=root_package,
            version="",
            description="(parse error)",
            path=str(pkg_path),
        )

    _visited.add(root_package)
    children: list[DependencyNode] = []
    for dep in info.dependencies:
        child = build_dependency_tree(
            dep,
            max_depth=max_depth,
            include_buildtool=include_buildtool,
            _depth=_depth + 1,
            _visited=set(_visited),
        )
        if child is not None:
            children.append(child)
    _visited.discard(root_package)

    return DependencyNode(
        name=info.name,
        version=info.version,
        description=info.description,
        path=str(info.path),
        children=children,
        package_info=info,
    )
