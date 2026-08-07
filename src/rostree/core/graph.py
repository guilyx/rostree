"""Turn a resolved dependency graph into DOT or Mermaid text.

Pure text generation with no I/O, so the CLI, the TUI and library users can all
produce the same graphs. Rendering those to images (Graphviz, matplotlib) is an
I/O concern and lives in the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rostree.core.tree import DependencyGraph, DependencyNode, NodeStatus


@dataclass
class GraphView:
    """The subset of a dependency graph that is about to be drawn."""

    edges: set[tuple[str, str]] = field(default_factory=set)
    roots: set[str] = field(default_factory=set)
    #: nodes with no package.xml — drawn dashed and grey rather than dropped
    missing: set[str] = field(default_factory=set)
    title: str | None = None

    @property
    def nodes(self) -> set[str]:
        """Every node named by an edge or listed as a root."""
        names = set(self.roots)
        for parent, child in self.edges:
            names.add(parent)
            names.add(child)
        return names

    @classmethod
    def from_graph(
        cls,
        graph: DependencyGraph,
        *,
        title: str | None = None,
        show_missing: bool = True,
    ) -> GraphView:
        """Build a view from a resolved dependency graph."""
        return cls(
            edges=graph.edge_pairs(include_missing=show_missing),
            roots=set(graph.roots),
            missing=set(graph.missing) if show_missing else set(),
            title=title,
        )

    @classmethod
    def from_trees(
        cls,
        trees: list[DependencyNode],
        *,
        title: str | None = None,
        show_missing: bool = False,
    ) -> GraphView:
        """Build a view by walking already-materialised trees."""
        view = cls(roots={t.name for t in trees}, title=title)
        for tree in trees:
            _collect_tree_edges(tree, view, set(), show_missing=show_missing)
        return view


def _collect_tree_edges(
    node: DependencyNode,
    view: GraphView,
    visited: set[str],
    *,
    show_missing: bool,
) -> None:
    if node.name in visited:
        return
    visited.add(node.name)
    for child in node.children:
        if child.status is NodeStatus.MISSING:
            if not show_missing:
                continue
            view.missing.add(child.name)
            view.edges.add((node.name, child.name))
            continue
        if child.status is NodeStatus.PARSE_ERROR:
            continue
        view.edges.add((node.name, child.name))
        _collect_tree_edges(child, view, visited, show_missing=show_missing)


def _dot_escape(name: str) -> str:
    return name.replace("\\", "\\\\").replace('"', '\\"')


def to_dot(view: GraphView, *, highlight_roots: bool = True) -> str:
    """Render a GraphView as Graphviz DOT."""
    lines = ["digraph dependencies {"]
    if view.title:
        lines.append(f'    label="{_dot_escape(view.title)}";')
        lines.append("    labelloc=t;")
        lines.append('    fontname="sans-serif";')
    lines.append("    rankdir=LR;")
    lines.append('    node [shape=box, style=rounded, fontname="sans-serif"];')

    if highlight_roots:
        for name in sorted(view.roots):
            lines.append(
                f'    "{_dot_escape(name)}" [style="rounded,filled", fillcolor=lightblue];'
            )
    for name in sorted(view.missing):
        lines.append(
            f'    "{_dot_escape(name)}" '
            '[style="rounded,dashed", color=gray50, fontcolor=gray40];'
        )

    for parent, child in sorted(view.edges):
        attrs = " [style=dashed, color=gray60]" if child in view.missing else ""
        lines.append(f'    "{_dot_escape(parent)}" -> "{_dot_escape(child)}"{attrs};')

    lines.append("}")
    return "\n".join(lines)


def mermaid_id(name: str) -> str:
    """Convert a package name to a valid Mermaid node ID."""
    return name.replace("-", "_").replace(".", "_")


def to_mermaid(view: GraphView, *, highlight_roots: bool = True) -> str:
    """Render a GraphView as a Mermaid flowchart."""
    lines = ["graph LR"]
    if view.title:
        lines[0] = f"---\ntitle: {view.title}\n---\ngraph LR"

    if highlight_roots:
        for name in sorted(view.roots):
            lines.append(f"    {mermaid_id(name)}[{name}]")
            lines.append(f"    style {mermaid_id(name)} fill:#add8e6,stroke:#4682b4")
    for name in sorted(view.missing):
        lines.append(f"    {mermaid_id(name)}[{name}]")
        lines.append(
            f"    style {mermaid_id(name)} fill:#f5f5f5,stroke:#9e9e9e,"
            "stroke-dasharray: 4 3,color:#757575"
        )

    for parent, child in sorted(view.edges):
        arrow = "-.->" if child in view.missing else "-->"
        lines.append(f"    {mermaid_id(parent)} {arrow} {mermaid_id(child)}")

    return "\n".join(lines)
