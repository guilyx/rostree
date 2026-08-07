"""Tests for DOT/Mermaid generation."""

from __future__ import annotations

from rostree.core.graph import GraphView, mermaid_id, to_dot, to_mermaid
from rostree.core.tree import DependencyGraph, DependencyNode, NodeStatus


def make_graph() -> DependencyGraph:
    graph = DependencyGraph(roots=["app"])
    graph.edges = {"app": ["lib", "ghost"], "lib": []}
    graph.missing = {"ghost"}
    graph.depths = {"app": 0, "lib": 1, "ghost": 1}
    return graph


class TestGraphView:
    """Tests for building a view from graphs and trees."""

    def test_from_graph_keeps_missing_edges(self) -> None:
        view = GraphView.from_graph(make_graph())
        assert ("app", "ghost") in view.edges
        assert view.missing == {"ghost"}
        assert view.nodes == {"app", "lib", "ghost"}

    def test_from_graph_can_drop_missing_edges(self) -> None:
        view = GraphView.from_graph(make_graph(), show_missing=False)
        assert ("app", "ghost") not in view.edges
        assert view.missing == set()

    def test_from_trees_walks_children(self) -> None:
        child = DependencyNode(name="lib", version="1.0", description="", path="")
        root = DependencyNode(name="app", version="1.0", description="", path="", children=[child])
        view = GraphView.from_trees([root], title="t")
        assert view.edges == {("app", "lib")}
        assert view.roots == {"app"}
        assert view.title == "t"

    def test_from_trees_skips_placeholders_by_default(self) -> None:
        missing = DependencyNode(
            name="ghost", version="", description="", path="", status=NodeStatus.MISSING
        )
        broken = DependencyNode(
            name="bad", version="", description="", path="", status=NodeStatus.PARSE_ERROR
        )
        root = DependencyNode(
            name="app", version="1.0", description="", path="", children=[missing, broken]
        )
        assert GraphView.from_trees([root]).edges == set()

    def test_from_trees_can_include_missing(self) -> None:
        missing = DependencyNode(
            name="ghost", version="", description="", path="", status=NodeStatus.MISSING
        )
        root = DependencyNode(
            name="app", version="1.0", description="", path="", children=[missing]
        )
        view = GraphView.from_trees([root], show_missing=True)
        assert view.edges == {("app", "ghost")}
        assert view.missing == {"ghost"}

    def test_from_trees_stops_at_repeated_nodes(self) -> None:
        """A tree that references itself must not send the walker into a loop."""
        root = DependencyNode(name="app", version="1.0", description="", path="")
        root.children = [root]
        assert GraphView.from_trees([root]).edges == {("app", "app")}


class TestDot:
    """Tests for DOT output."""

    def test_edges_and_root_highlight(self) -> None:
        dot = to_dot(GraphView.from_graph(make_graph(), title="deps"))
        assert dot.startswith("digraph dependencies {")
        assert '"app" -> "lib";' in dot
        assert 'label="deps";' in dot
        assert "fillcolor=lightblue" in dot
        assert dot.rstrip().endswith("}")

    def test_missing_nodes_are_dashed(self) -> None:
        dot = to_dot(GraphView.from_graph(make_graph()))
        assert '"ghost" [style="rounded,dashed"' in dot
        assert '"app" -> "ghost" [style=dashed' in dot

    def test_highlight_can_be_disabled(self) -> None:
        dot = to_dot(GraphView.from_graph(make_graph()), highlight_roots=False)
        assert "fillcolor=lightblue" not in dot

    def test_quotes_are_escaped(self) -> None:
        view = GraphView(edges={('we"ird', "child")}, roots={'we"ird'})
        dot = to_dot(view)
        assert '\\"' in dot


class TestMermaid:
    """Tests for Mermaid output."""

    def test_edges_and_title(self) -> None:
        text = to_mermaid(GraphView.from_graph(make_graph(), title="deps"))
        assert "title: deps" in text
        assert "app --> lib" in text

    def test_missing_nodes_use_dotted_arrows(self) -> None:
        text = to_mermaid(GraphView.from_graph(make_graph()))
        assert "app -.-> ghost" in text
        assert "stroke-dasharray" in text

    def test_identifier_sanitising(self) -> None:
        assert mermaid_id("a-b.c") == "a_b_c"
