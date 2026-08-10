"""
Build a self-contained interactive HTML view of a dependency graph.

The output is one file with no network access of any kind: the data, the styles
and the script are all inlined. That is deliberate — a dependency graph is
something you attach to a bug report, commit next to a design doc, or open on a
robot with no route to the internet. A viewer that needs a CDN is a viewer that
stops working exactly when you need it.

Layout and interaction live in ``web/graph.js``; this module's only job is to
turn a resolved :class:`DependencyGraph` into the JSON that script consumes, and
to paste the three pieces together.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from rostree.core.index import PackageIndex, SourceKind
from rostree.core.tree import DependencyGraph

#: Node kinds the viewer knows how to colour. ``missing`` is not a SourceKind —
#: it means the name never resolved to a package.xml at all.
MISSING_KIND = "missing"


def _asset(name: str) -> str:
    """Read a file shipped alongside the package."""
    return resources.files("rostree.web").joinpath(name).read_text(encoding="utf-8")


def graph_payload(
    graph: DependencyGraph,
    *,
    index: PackageIndex | None = None,
    title: str | None = None,
    show_missing: bool = True,
) -> dict[str, Any]:
    """
    Everything the viewer needs, in one JSON-serialisable dict.

    Edges are not listed separately: each node carries its own ``deps``, which is
    both smaller and the order the manifest declared them in.
    """
    nodes: dict[str, dict[str, Any]] = {}

    def ensure(name: str) -> dict[str, Any]:
        node = nodes.get(name)
        if node is None:
            node = {"deps": [], "kind": MISSING_KIND}
            nodes[name] = node
        return node

    for name, info in graph.packages.items():
        entry = index.get(name) if index is not None else None
        node = ensure(name)
        node["kind"] = entry.kind.value if entry is not None else SourceKind.OTHER.value
        if info.version:
            node["version"] = info.version
        if info.description:
            node["desc"] = info.description
        node["path"] = str(info.path.parent)
        if entry is not None:
            node["origin"] = entry.label
        if info.system_dependencies:
            # rosdep keys are not packages and get no node, but hiding them
            # entirely would misrepresent what the manifest actually declares.
            node["rosdep"] = list(info.system_dependencies)

    for name in graph.missing:
        if show_missing:
            ensure(name)

    for parent, children in graph.edges.items():
        node = ensure(parent)
        deps = [c for c in children if show_missing or c not in graph.missing]
        node["deps"] = deps
        for child in deps:
            ensure(child)

    for name in graph.unparsable:
        if name in nodes:
            nodes[name]["kind"] = MISSING_KIND
            nodes[name]["error"] = "package.xml could not be parsed"

    cycles = graph.cycles()
    return {
        "title": title or "rostree dependency graph",
        "roots": list(graph.roots),
        "nodes": nodes,
        "cycles": cycles,
        "stats": {
            "packages": len(nodes),
            "edges": sum(len(n["deps"]) for n in nodes.values()),
            "missing": len([n for n in nodes.values() if n["kind"] == MISSING_KIND]),
            "cycles": len(cycles),
        },
    }


def to_html(
    graph: DependencyGraph,
    *,
    index: PackageIndex | None = None,
    title: str | None = None,
    show_missing: bool = True,
    subtitle: str | None = None,
) -> str:
    """Render a dependency graph as a single self-contained HTML document."""
    payload = graph_payload(graph, index=index, title=title, show_missing=show_missing)
    if subtitle:
        payload["subtitle"] = subtitle

    # `</script>` inside a string literal would end the block early; the escape
    # below is the standard defence and survives JSON.parse unchanged.
    data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")

    return (
        _asset("graph.html")
        .replace("/*{{STYLE}}*/", _asset("graph.css"))
        .replace("/*{{DATA}}*/", data)
        .replace("/*{{SCRIPT}}*/", _asset("graph.js"))
        .replace("{{TITLE}}", _escape(payload["title"]))
    )


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
