"""Tests for TUI utility functions (non-interactive parts)."""

from __future__ import annotations


from rostree.tui.app import (
    _count_nodes,
    _node_stats,
)


class MockNode:
    """Mock node for testing utility functions."""

    def __init__(self, name: str, children: list | None = None) -> None:
        self.name = name
        self.children = children or []


class TestCountNodes:
    """Tests for _count_nodes helper."""

    def test_single_node(self) -> None:
        node = MockNode("root")
        assert _count_nodes(node) == 1

    def test_with_children(self) -> None:
        node = MockNode(
            "root",
            children=[
                MockNode("child1"),
                MockNode("child2"),
            ],
        )
        assert _count_nodes(node) == 3

    def test_nested_children(self) -> None:
        node = MockNode(
            "root",
            children=[
                MockNode(
                    "child",
                    children=[
                        MockNode("grandchild1"),
                        MockNode("grandchild2"),
                    ],
                ),
            ],
        )
        assert _count_nodes(node) == 4

    def test_deep_tree(self) -> None:
        # Create a deep tree
        node = MockNode("level0")
        current = node
        for i in range(1, 5):
            child = MockNode(f"level{i}")
            current.children = [child]
            current = child
        assert _count_nodes(node) == 5


class TestNodeStats:
    """Tests for _node_stats helper."""

    def test_leaf_node(self) -> None:
        node = MockNode("leaf")
        direct, total, max_depth = _node_stats(node)
        assert direct == 0
        assert total == 0
        assert max_depth == 0

    def test_single_child(self) -> None:
        node = MockNode("root", children=[MockNode("child")])
        direct, total, max_depth = _node_stats(node)
        assert direct == 1
        assert total == 1
        assert max_depth == 1

    def test_multiple_children(self) -> None:
        node = MockNode(
            "root",
            children=[
                MockNode("child1"),
                MockNode("child2"),
                MockNode("child3"),
            ],
        )
        direct, total, max_depth = _node_stats(node)
        assert direct == 3
        assert total == 3
        assert max_depth == 1

    def test_nested_tree(self) -> None:
        node = MockNode(
            "root",
            children=[
                MockNode(
                    "child1",
                    children=[
                        MockNode("grandchild1"),
                        MockNode("grandchild2"),
                    ],
                ),
                MockNode("child2"),
            ],
        )
        direct, total, max_depth = _node_stats(node)
        assert direct == 2  # child1, child2
        assert total == 4  # child1 + grandchild1 + grandchild2 + child2
        assert max_depth == 2  # root -> child1 -> grandchild

    def test_unbalanced_tree(self) -> None:
        # One deep branch, one shallow
        node = MockNode(
            "root",
            children=[
                MockNode(
                    "deep1",
                    children=[
                        MockNode(
                            "deep2",
                            children=[
                                MockNode("deep3"),
                            ],
                        ),
                    ],
                ),
                MockNode("shallow"),
            ],
        )
        direct, total, max_depth = _node_stats(node)
        assert direct == 2
        assert total == 4  # deep1 + deep2 + deep3 + shallow
        assert max_depth == 3  # root -> deep1 -> deep2 -> deep3

    def test_empty_children_list(self) -> None:
        node = MockNode("root")
        node.children = []
        direct, total, max_depth = _node_stats(node)
        assert direct == 0
        assert total == 0
        assert max_depth == 0

    def test_none_children_attr(self) -> None:
        # Test with object that has no children attribute
        class NoChildren:
            pass

        obj = NoChildren()
        direct, total, max_depth = _node_stats(obj)
        assert direct == 0
        assert total == 0
        assert max_depth == 0
