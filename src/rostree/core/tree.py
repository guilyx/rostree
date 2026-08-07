"""Build and represent ROS 2 package dependency trees.

A ROS dependency graph is a DAG, not a tree: ``rcutils`` sits under almost every
branch of ``rclcpp``. Expanding every path separately turns a 200-package
workspace into tens of thousands of nodes and takes tens of seconds. rostree
walks the DAG once and prints each package's subtree once, marking later
occurrences as repeats — the same thing ``cargo tree`` does with ``(*)``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable

from rostree.core.index import PackageIndex, get_index
from rostree.core.parser import (
    RUNTIME_DEPENDENCY_TAGS,
    PackageInfo,
    parse_package_xml,
)

# Kept for backwards compatibility with callers that imported it from here.
_RUNTIME_DEPENDENCY_TAGS = RUNTIME_DEPENDENCY_TAGS


class NodeStatus(str, Enum):
    """Why a node looks the way it does."""

    OK = "ok"
    #: Already shown in full elsewhere in this tree; children omitted.
    REPEAT = "repeat"
    #: Depends (directly or transitively) on one of its own ancestors.
    CYCLE = "cycle"
    #: No package.xml anywhere on the search path (rosdep key, or not built yet).
    MISSING = "missing"
    #: Found, but the manifest could not be parsed.
    PARSE_ERROR = "parse_error"
    #: Cut off by max_depth; the real subtree continues below.
    TRUNCATED = "truncated"

    @property
    def marker(self) -> str:
        """The parenthesised marker historically stored in ``description``."""
        return _STATUS_MARKERS.get(self, "")


_STATUS_MARKERS = {
    NodeStatus.REPEAT: "(see above)",
    NodeStatus.CYCLE: "(cycle)",
    NodeStatus.MISSING: "(not found)",
    NodeStatus.PARSE_ERROR: "(parse error)",
    NodeStatus.TRUNCATED: "(depth limit)",
}

#: Markers that mean "this node is not a real, fully expanded package".
STATUS_MARKERS = tuple(_STATUS_MARKERS.values())


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
    status: NodeStatus = NodeStatus.OK

    @property
    def is_error(self) -> bool:
        """True when this node could not be resolved or parsed."""
        return self.status in (NodeStatus.MISSING, NodeStatus.PARSE_ERROR)

    @property
    def is_placeholder(self) -> bool:
        """True when this node stands in for a subtree shown (or cut) elsewhere."""
        return self.status in (NodeStatus.REPEAT, NodeStatus.CYCLE, NodeStatus.TRUNCATED)

    def walk(self) -> Iterable[DependencyNode]:
        """Yield this node and every descendant, depth-first."""
        yield self
        for child in self.children:
            yield from child.walk()

    def to_dict(self) -> dict:
        """Serialize node to a JSON-friendly dict (for API/frontend)."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "path": str(self.path),
            "status": self.status.value,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class DependencyGraph:
    """The resolved dependency DAG reachable from one or more root packages."""

    roots: list[str]
    #: package name -> its direct dependencies, in declaration order
    edges: dict[str, list[str]] = field(default_factory=dict)
    #: package name -> parsed manifest, for packages that resolved
    packages: dict[str, PackageInfo] = field(default_factory=dict)
    #: dependency names that could not be resolved to a package.xml
    missing: set[str] = field(default_factory=set)
    #: packages whose manifest exists but could not be parsed
    unparsable: set[str] = field(default_factory=set)
    #: package name -> shortest distance from any root
    depths: dict[str, int] = field(default_factory=dict)

    @property
    def node_count(self) -> int:
        """Number of distinct packages in the graph, including unresolved ones."""
        return len(set(self.edges) | self.missing)

    def edge_pairs(self, *, include_missing: bool = True) -> set[tuple[str, str]]:
        """All (parent, child) pairs, optionally dropping edges to unresolved packages."""
        pairs: set[tuple[str, str]] = set()
        for parent, children in self.edges.items():
            for child in children:
                if not include_missing and child in self.missing:
                    continue
                pairs.add((parent, child))
        return pairs

    def cycles(self) -> list[list[str]]:
        """Return dependency cycles as lists of package names (each cycle listed once)."""
        found: list[list[str]] = []
        seen_cycles: set[tuple[str, ...]] = set()
        colour: dict[str, int] = {}  # 0 = visiting, 1 = done
        stack: list[str] = []

        def visit(name: str) -> None:
            state = colour.get(name)
            if state == 1:
                return
            if state == 0:
                start = stack.index(name)
                cycle = stack[start:] + [name]
                key = tuple(sorted(cycle[:-1]))
                if key not in seen_cycles:
                    seen_cycles.add(key)
                    found.append(cycle)
                return
            colour[name] = 0
            stack.append(name)
            for dep in self.edges.get(name, ()):
                visit(dep)
            stack.pop()
            colour[name] = 1

        for root in self.roots:
            visit(root)
        return found


def build_dependency_graph(
    root_packages: str | Iterable[str],
    *,
    max_depth: int | None = None,
    runtime_only: bool = False,
    include_buildtool: bool = False,
    include_tags: tuple[str, ...] | None = None,
    extra_source_roots: list[Path] | None = None,
    index: PackageIndex | None = None,
    on_progress: Callable[[int, str], None] | None = None,
) -> DependencyGraph:
    """
    Resolve the dependency DAG reachable from one or more packages.

    Breadth-first, so ``graph.depths`` holds each package's shortest distance from
    a root. Every package is resolved and parsed exactly once, making this linear
    in the number of reachable packages no matter how tangled the graph is. Use it
    for graphs, statistics and cycle checks; use :func:`build_dependency_tree`
    when you want a renderable tree.
    """
    if isinstance(root_packages, str):
        roots = [root_packages]
    else:
        roots = list(dict.fromkeys(root_packages))

    tags = _resolve_tags(
        runtime_only=runtime_only,
        include_buildtool=include_buildtool,
        include_tags=include_tags,
    )
    if index is None:
        index = get_index(extra_source_roots=extra_source_roots)

    graph = DependencyGraph(roots=roots)
    queue: deque[tuple[str, int]] = deque((name, 0) for name in roots)
    graph.depths = {name: 0 for name in roots}

    while queue:
        name, depth = queue.popleft()
        manifest = index.resolve(name)
        if manifest is None:
            graph.missing.add(name)
            continue
        info = parse_package_xml(manifest, include_tags=tags)
        if info is None:
            graph.unparsable.add(name)
            graph.edges.setdefault(name, [])
            continue
        graph.packages[name] = info
        graph.edges[name] = list(info.dependencies)
        if on_progress is not None:
            on_progress(len(graph.packages), name)
        if max_depth is not None and depth >= max_depth:
            continue
        for dep in info.dependencies:
            if dep not in graph.depths:
                graph.depths[dep] = depth + 1
                queue.append((dep, depth + 1))

    return graph


def _resolve_tags(
    *,
    runtime_only: bool,
    include_buildtool: bool,
    include_tags: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    if include_tags is not None:
        return include_tags
    if runtime_only:
        return RUNTIME_DEPENDENCY_TAGS
    # include_buildtool is accepted for API compatibility; buildtool_depend entries
    # are ament/cmake tooling rather than runtime packages and are never traversed.
    return None


def build_dependency_tree(
    root_package: str,
    *,
    max_depth: int | None = None,
    include_buildtool: bool = False,
    runtime_only: bool = False,
    extra_source_roots: list[Path] | None = None,
    collapse_repeats: bool = True,
    index: PackageIndex | None = None,
    max_nodes: int | None = None,
    on_progress: Callable[[int, str], None] | None = None,
    _depth: int = 0,
    _visited: set[str] | None = None,
) -> DependencyNode | None:
    """
    Build a dependency tree starting from a root package name.

    Args:
        root_package: Root ROS package name.
        max_depth: Optional max depth; None means no limit.
        include_buildtool: Accepted for API compatibility (buildtool deps are tooling,
            not runtime packages, and are never traversed).
        runtime_only: If True, only depend and exec_depend (no build/test deps);
            much smaller and faster for packages with heavy build toolchains.
        extra_source_roots: Optional list of Paths to scan for packages (user-added).
        collapse_repeats: When True (the default) a package that already appears in
            full elsewhere in the tree is emitted once as a ``REPEAT`` leaf instead of
            being expanded again. This is what keeps large trees linear rather than
            exponential; set it to False for a fully expanded tree.
        index: Reuse an existing package index instead of building one.
        max_nodes: Stop after emitting this many nodes (a safety valve for
            ``collapse_repeats=False``).
        on_progress: Called as ``(nodes_so_far, package_name)`` while building.
        _depth: Internal recursion depth.
        _visited: Internal set of package names on the current path.

    Returns:
        DependencyNode for the root, or None if the root is cut off by max_depth.
    """
    if index is None:
        index = get_index(extra_source_roots=extra_source_roots)
    tags = _resolve_tags(
        runtime_only=runtime_only,
        include_buildtool=include_buildtool,
        include_tags=None,
    )

    if max_depth is not None and _depth > max_depth:
        return None

    visited = set(_visited or ())
    if root_package in visited:
        return _marker_node(root_package, NodeStatus.CYCLE)

    remaining_depth = None if max_depth is None else max_depth - _depth
    builder = _TreeBuilder(
        index=index,
        tags=tags,
        max_depth=remaining_depth,
        collapse_repeats=collapse_repeats,
        max_nodes=max_nodes,
        on_progress=on_progress,
    )
    return builder.build(root_package, depth=0, path=visited)


class _TreeBuilder:
    """Depth-first tree materialisation with repeat collapsing and a node budget."""

    def __init__(
        self,
        *,
        index: PackageIndex,
        tags: tuple[str, ...] | None,
        max_depth: int | None,
        collapse_repeats: bool,
        max_nodes: int | None,
        on_progress: Callable[[int, str], None] | None,
    ) -> None:
        self.index = index
        self.tags = tags
        self.max_depth = max_depth
        self.collapse_repeats = collapse_repeats
        self.max_nodes = max_nodes
        self.on_progress = on_progress
        self.expanded: set[str] = set()
        self.count = 0
        self.truncated = False

    def build(self, name: str, *, depth: int, path: set[str]) -> DependencyNode:
        self.count += 1
        if self.on_progress is not None:
            self.on_progress(self.count, name)

        if name in path:
            return _marker_node(name, NodeStatus.CYCLE)

        manifest = self.index.resolve(name)
        if manifest is None:
            return _marker_node(name, NodeStatus.MISSING)

        info = parse_package_xml(manifest, include_tags=self.tags)
        if info is None:
            return _marker_node(name, NodeStatus.PARSE_ERROR, path=str(manifest))

        node = DependencyNode(
            name=info.name,
            version=info.version,
            description=info.description,
            path=str(info.path),
            package_info=info,
        )
        if not info.dependencies:
            self.expanded.add(name)
            return node

        if not self._should_expand(name):
            node.description = NodeStatus.REPEAT.marker
            node.status = NodeStatus.REPEAT
            return node

        if self.max_depth is not None and depth >= self.max_depth:
            node.status = NodeStatus.TRUNCATED
            return node

        if self.max_nodes is not None and self.count >= self.max_nodes:
            self.truncated = True
            node.status = NodeStatus.TRUNCATED
            return node

        self.expanded.add(name)
        child_path = path | {name}
        node.children = [
            self.build(dep, depth=depth + 1, path=child_path) for dep in info.dependencies
        ]
        return node

    def _should_expand(self, name: str) -> bool:
        """
        Expand a package at the first place the tree *prints* it.

        Traversal is depth-first and so is the rendered output, so keying off
        first encounter is what makes "see above" true: every later occurrence
        is, by construction, printed after the one that carries the subtree. A
        package cut off by ``max_depth`` is not counted as expanded, so a later
        occurrence with room to expand still gets the full subtree.
        """
        if not self.collapse_repeats:
            return True  # fully expanded tree: every occurrence gets its own subtree
        return name not in self.expanded


def _marker_node(name: str, status: NodeStatus, *, path: str = "") -> DependencyNode:
    return DependencyNode(
        name=name,
        version="",
        description=status.marker,
        path=path,
        status=status,
    )


def tree_stats(node: DependencyNode) -> dict[str, int]:
    """Summarise a built tree: node count, distinct packages, depth, unresolved deps."""
    total = 0
    distinct: set[str] = set()
    missing: set[str] = set()
    repeats = 0
    cycles = 0
    max_depth = 0

    def visit(n: DependencyNode, depth: int) -> None:
        nonlocal total, repeats, cycles, max_depth
        total += 1
        max_depth = max(max_depth, depth)
        if n.status is NodeStatus.MISSING:
            missing.add(n.name)
        else:
            distinct.add(n.name)
        if n.status is NodeStatus.REPEAT:
            repeats += 1
        elif n.status is NodeStatus.CYCLE:
            cycles += 1
        for child in n.children:
            visit(child, depth + 1)

    visit(node, 0)
    return {
        "nodes": total,
        "packages": len(distinct),
        "missing": len(missing),
        "repeats": repeats,
        "cycles": cycles,
        "depth": max_depth,
    }
