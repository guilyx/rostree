"""Textual TUI for navigating ROS 2 package dependency trees."""

from __future__ import annotations

import sys
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Static, Tree
from textual.widgets.tree import TreeNode

from rosdep_viz.api import build_tree, list_known_packages


def _populate_textual_tree(tn: TreeNode, node: Any) -> None:
    """Recursively add DependencyNode children to a Textual TreeNode."""
    for child in node.children:
        label = f"[dim]{child.name}[/] [dim]({child.version or '?'})[/]"
        if child.description and child.description not in ("(not found)", "(cycle)", "(parse error)"):
            # Truncate long descriptions in tree label
            desc = child.description[:40] + "…" if len(child.description) > 40 else child.description
            label = f"{child.name} [dim]— {desc}[/]"
        child_tn = tn.add(label, expand=False)
        child_tn.data = child
        _populate_textual_tree(child_tn, child)


class DepTreeApp(App[None]):
    """Terminal UI to explore ROS 2 package dependency trees."""

    TITLE = "rosdep_viz — ROS 2 dependency tree"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh tree"),
        Binding("e", "expand_all", "Expand all"),
        Binding("c", "collapse_all", "Collapse all"),
    ]

    def __init__(self, root_package: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._root_package = root_package
        self._root_node: Any = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Tree("Dependencies", id="dep_tree")
        yield Static("Select a node to see details.", id="details")
        yield Footer()

    def on_mount(self) -> None:
        tree = self.query_one("#dep_tree", Tree)
        if self._root_package:
            self._load_tree(self._root_package)
        else:
            packages = list_known_packages()
            if not packages:
                self._set_details("No ROS 2 packages found. Set AMENT_PREFIX_PATH or run from a workspace.")
                tree.root.add_leaf("[dim]No packages in environment[/]")
                return
            # Show list of packages as roots; user can expand to see deps on demand
            tree.root.label = "Known packages (expand to load deps)"
            for name in sorted(packages.keys())[:200]:  # Limit initial list
                tn = tree.root.add(f"[bold]{name}[/]", expand=False)
                tn.data = name
            if len(packages) > 200:
                tree.root.add_leaf(f"[dim]… and {len(packages) - 200} more[/]")
            self._set_details(f"Found {len(packages)} packages. Select a package to load its dependency tree.")
            return
        self._render_tree(tree)

    def _clear_tree(self, tree: Tree) -> None:
        """Remove all children of the tree root (Textual has no Tree.clear())."""
        while tree.root.children:
            tree.root.children[0].remove()

    def _load_tree(self, root_package: str) -> None:
        self._root_package = root_package
        self._root_node = build_tree(root_package)
        if self._root_node is None:
            self._set_details(f"Package not found: {root_package}")
            return
        tree = self.query_one("#dep_tree", Tree)
        self._clear_tree(tree)
        tree.root.label = f"[bold]{self._root_node.name}[/] [dim]v{self._root_node.version or '?'}[/]"
        tree.root.data = self._root_node
        _populate_textual_tree(tree.root, self._root_node)
        tree.root.expand_all()
        self._set_details(self._format_node(self._root_node))

    def _render_tree(self, tree: Tree) -> None:
        if self._root_node is None:
            return
        tree.root.label = f"[bold]{self._root_node.name}[/] [dim]v{self._root_node.version or '?'}[/]"
        tree.root.data = self._root_node
        _populate_textual_tree(tree.root, self._root_node)
        tree.root.expand_all()

    def _format_node(self, node: Any) -> str:
        lines = [
            f"[bold]{node.name}[/]  [dim]v{node.version or '?'}[/]",
            "",
            node.description or "(no description)",
            "",
            f"[dim]path: {node.path or '(n/a)'}[/]",
        ]
        if node.children:
            lines.append("")
            lines.append(f"[dim]dependencies: {len(node.children)}[/]")
        return "\n".join(lines)

    def _set_details(self, text: str) -> None:
        details = self.query_one("#details", Static)
        details.update(text)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        node = event.node.data
        if node is None:
            return
        if hasattr(node, "name"):
            self._set_details(self._format_node(node))
        elif isinstance(node, str):
            # Lazy load: selecting a package name from the "known packages" list loads its tree
            self._load_tree(node)

    def action_refresh(self) -> None:
        if self._root_package:
            self._load_tree(self._root_package)

    def action_expand_all(self) -> None:
        tree = self.query_one("#dep_tree", Tree)
        tree.root.expand_all()

    def action_collapse_all(self) -> None:
        tree = self.query_one("#dep_tree", Tree)
        tree.root.collapse_all()
        tree.root.expand()

    def action_quit(self) -> None:
        self.exit()


def main() -> None:
    """Entry point for the rosdep-viz CLI."""
    root = None
    if len(sys.argv) > 1:
        root = sys.argv[1].strip()
    app = DepTreeApp(root_package=root)
    app.run()


if __name__ == "__main__":
    main()
