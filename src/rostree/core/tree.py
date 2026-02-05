"""Build and represent ROS 2 package dependency trees."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rostree.core.parser import PackageInfo, parse_package_xml
from rostree.core.finder import find_package_path


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


# Tags used when runtime_only=True (smaller, faster tree; no build/test deps).
_RUNTIME_DEPENDENCY_TAGS = ("depend", "exec_depend")


def build_dependency_tree(
    root_package: str,
    *,
    max_depth: int | None = None,
    include_buildtool: bool = False,
    runtime_only: bool = False,
    extra_source_roots: list[Path] | None = None,
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
        runtime_only: If True, only depend and exec_depend (no build/test deps);
            much smaller and faster for packages with heavy build toolchains.
        extra_source_roots: Optional list of Paths to scan for packages (user-added).
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

    roots: list[Path] | None = None
    if extra_source_roots is not None:
        roots = [Path(p).resolve() for p in extra_source_roots]
    pkg_path = find_package_path(root_package, extra_source_roots=roots)
    if pkg_path is None:
        return DependencyNode(
            name=root_package,
            version="",
            description="(not found)",
            path="",
        )

    include_tags = _RUNTIME_DEPENDENCY_TAGS if runtime_only else None
    info = parse_package_xml(pkg_path, include_tags=include_tags)
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
            runtime_only=runtime_only,
            extra_source_roots=extra_source_roots,
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
