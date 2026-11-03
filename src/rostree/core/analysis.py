"""
Questions you ask of a dependency graph: why, who depends on this, what changed.

These used to live inside the CLI, interleaved with printing, so the only way to
use them from another tool was to shell out to ``rostree`` and parse its output.
Here they are plain functions over a :class:`~rostree.core.index.PackageIndex`
and a :class:`~rostree.core.tree.DependencyGraph`; the CLI is now one caller
among many. Nothing in this module prints, exits, or reads the environment.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from rostree.core.filters import FilterReport, PackageFilter
from rostree.core.index import PackageIndex
from rostree.core.tree import DependencyGraph

__all__ = [
    "DependencyDiff",
    "dependency_versions",
    "dependents",
    "diff_dependencies",
    "shortest_paths",
]


def shortest_paths(
    graph: DependencyGraph,
    start: str,
    target: str,
    *,
    limit: int = 10,
) -> list[list[str]]:
    """
    Every shortest dependency path from ``start`` to ``target``, up to ``limit``.

    Shortest only, deliberately. The full set of paths through a ROS graph is
    enormous and unreadable; the shortest ones answer the question actually being
    asked — "how did this get pulled in?" Breadth-first from ``start``, recording
    every parent that reaches a node at its minimal depth, then walking back from
    ``target``. Paths are ordered by parent name, so the output is deterministic.

    Returns ``[[start]]`` when the two are the same and ``[]`` when there is no path.
    """
    if start == target:
        return [[start]]

    parents: dict[str, set[str]] = {}
    depth: dict[str, int] = {start: 0}
    queue: deque[str] = deque([start])
    found_depth: int | None = None

    while queue:
        node = queue.popleft()
        if found_depth is not None and depth[node] >= found_depth:
            continue  # anything from here on is longer than the paths already found
        for dep in graph.edges.get(node, ()):
            if dep not in depth:
                depth[dep] = depth[node] + 1
                parents.setdefault(dep, set()).add(node)
                if dep == target:
                    found_depth = depth[dep]
                else:
                    queue.append(dep)
            elif depth[dep] == depth[node] + 1:
                # A second route of the same, minimal length.
                parents.setdefault(dep, set()).add(node)

    if target not in depth:
        return []

    paths: list[list[str]] = []

    def walk_back(node: str, tail: list[str]) -> None:
        if len(paths) >= limit:
            return
        if node == start:
            paths.append([start] + tail)
            return
        for parent in sorted(parents.get(node, ())):
            if depth.get(parent, -1) == depth[node] - 1:
                walk_back(parent, [node] + tail)

    walk_back(target, [])
    return paths[:limit]


def dependents(
    index: PackageIndex,
    package: str,
    *,
    transitive: bool = False,
    include_tags: tuple[str, ...] | None = None,
    package_filter: PackageFilter | None = None,
    report: FilterReport | None = None,
) -> list[str]:
    """
    The packages that depend on ``package`` — "what breaks if this changes?"

    With ``transitive=True``, everything that depends on it through any chain.
    ``package`` itself is never listed, even when a cycle leads back to it: you
    already know the package you are changing is affected.

    The filter is applied to the answer, not to the walk. That is the opposite of
    tree building, and deliberate: excluding an intermediate package must not
    hide the dependents behind it, or the filter would hide the very breakage
    this exists to find. What it removed is noted on ``report``.
    """
    reverse = index.reverse_dependencies(include_tags=include_tags)
    direct = reverse.get(package, set())
    if transitive:
        seen: set[str] = set()
        frontier = list(direct)
        while frontier:
            name = frontier.pop()
            if name in seen:
                continue
            seen.add(name)
            frontier.extend(reverse.get(name, ()))
        seen.discard(package)
        names = sorted(seen)
    else:
        names = sorted(direct - {package})
    if package_filter is not None:
        names = package_filter.filter_names(names, index, report)
    return names


def dependency_versions(
    graph: DependencyGraph,
    *,
    exclude: Iterable[str] = (),
) -> dict[str, str]:
    """
    Every package in ``graph`` mapped to its version — a comparable snapshot.

    Names that never resolved are kept with an empty version, so a dependency
    that disappears or appears is still seen as a change. Pass the roots in
    ``exclude`` to describe a package by what it depends on, not by itself.
    """
    versions = {name: info.version for name, info in graph.packages.items()}
    for name in graph.missing:
        versions[name] = ""
    for name in exclude:
        versions.pop(name, None)
    return versions


@dataclass
class DependencyDiff:
    """What changed between two dependency snapshots. Truthy when anything did."""

    before: str
    after: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    #: name -> (version before, version after), only where both are known
    changed: dict[str, tuple[str, str]] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.added or self.removed or self.changed)

    def to_dict(self) -> dict:
        """JSON-friendly form; the same shape ``rostree diff --json`` prints."""
        return {
            "before": self.before,
            "after": self.after,
            "added": list(self.added),
            "removed": list(self.removed),
            "changed": {n: {"from": a, "to": b} for n, (a, b) in self.changed.items()},
        }


def diff_dependencies(
    before: Mapping[str, str],
    after: Mapping[str, str],
    *,
    before_name: str = "before",
    after_name: str = "after",
) -> DependencyDiff:
    """
    Compare two ``name -> version`` maps, such as two :func:`dependency_versions`.

    A version that went from unknown to known (a dependency that now resolves) is
    not reported as *changed*: there is nothing to compare it against.
    """
    shared = set(before) & set(after)
    return DependencyDiff(
        before=before_name,
        after=after_name,
        added=sorted(set(after) - set(before)),
        removed=sorted(set(before) - set(after)),
        changed={
            name: (before[name], after[name])
            for name in sorted(shared)
            if before[name] != after[name] and before[name] and after[name]
        },
    )
