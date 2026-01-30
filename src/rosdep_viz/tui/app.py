"""Textual TUI for navigating ROS 2 package dependency trees."""

from __future__ import annotations

import sys
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Static, Tree
from textual.widgets.tree import TreeNode

from rosdep_viz.api import build_tree, list_known_packages

# Big text banner for welcome screen
WELCOME_BANNER = r"""
[bold cyan]  ____  _____ ____  ____  ___  ____  __  __   ___   __   _____
 |  _ \| ____/ ___||  _ \|_ _|/ ___| \ \/ /  / _ \  \ \ / / _ \
 | |_) |  _| \___ \| |_) || | \___ \  \  /  | | | |  \ V / | | |
 |  _ <| |___ ___) |  __/ | |  ___) | /  \  | |_| |   | |  |_| |
 |_| \_\_____|____/|_|   |___||____/ /_/\_\  \___/    |_|   \___/
[/bold cyan]
"""

WELCOME_BODY = """
[dim]Visualize ROS 2 package dependencies as a navigable tree.[/]

  • [bold]Library[/]: find packages, parse package.xml, build trees
  • [bold]TUI[/]: browse packages, expand/collapse, see details
  • [bold]API[/]: same logic for scripts and the web backend

[dim]Requires ROS 2 env (source install/setup.bash).[/]
"""

# Limits to avoid huge trees and crashes
MAX_PACKAGES_IN_LIST = 150
MAX_TREE_DEPTH = 10
MAX_TREE_NODES = 800
EXPAND_DEPTH_DEFAULT = 2  # Only expand this many levels by default


def _count_nodes(node: Any) -> int:
    """Count nodes in tree (for cap)."""
    n = 1
    for c in getattr(node, "children", []):
        n += _count_nodes(c)
    return n


def _populate_textual_tree(
    tn: TreeNode,
    node: Any,
    *,
    depth: int = 0,
    max_depth: int = MAX_TREE_DEPTH,
    max_nodes: int = MAX_TREE_NODES,
    node_count: list[int] | None = None,
) -> None:
    """Recursively add DependencyNode children; cap depth and total nodes."""
    if node_count is None:
        node_count = [0]
    for child in getattr(node, "children", []):
        if node_count[0] >= max_nodes:
            tn.add_leaf(f"[dim]… truncated ({max_nodes} nodes max)[/]")
            return
        if depth >= max_depth:
            tn.add_leaf(f"[dim]{child.name} …[/]")
            continue
        node_count[0] += 1
        label = f"{child.name} [dim]v{child.version or '?'}[/]"
        child_tn = tn.add(label, expand=False)
        child_tn.data = child
        _populate_textual_tree(
            child_tn,
            child,
            depth=depth + 1,
            max_depth=max_depth,
            max_nodes=max_nodes,
            node_count=node_count,
        )


def _expand_to_depth(tn: TreeNode, depth: int, current: int = 0) -> None:
    """Expand tree nodes up to given depth (0 = root only)."""
    if current >= depth:
        return
    try:
        tn.expand()
        for child in tn.children:
            _expand_to_depth(child, depth, current + 1)
    except Exception:
        pass


class WelcomeScreen(Screen[bool]):
    """Welcome / presentation screen with banner and instructions."""

    BINDINGS = [
        Binding("enter", "start", "Start", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    DEFAULT_CSS = """
    WelcomeScreen {
        align: center middle;
        padding: 2 4;
    }
    WelcomeScreen #banner {
        text-align: center;
        padding-bottom: 1;
    }
    WelcomeScreen #welcome_body {
        padding: 1 2;
        width: 60;
    }
    WelcomeScreen #welcome_footer {
        text-align: center;
        padding-top: 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(WELCOME_BANNER, id="banner", markup=True)
        yield Static(WELCOME_BODY, id="welcome_body", markup=True)
        yield Static(
            "[bold]Press [cyan]Enter[/] to start  ·  [dim]q[/] to quit[/]",
            id="welcome_footer",
            markup=True,
        )

    def action_start(self) -> None:
        self.dismiss(True)

    def action_quit(self) -> None:
        self.dismiss(False)


class DepTreeApp(App[None]):
    """Terminal UI to explore ROS 2 package dependency trees."""

    TITLE = "rosdep_viz"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("e", "expand_all", "Expand all"),
        Binding("c", "collapse_all", "Collapse"),
    ]

    def __init__(self, root_package: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._root_package = root_package
        self._root_node: Any = None
        self._main_started = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Tree("Dependencies", id="dep_tree")
        yield Static("Select a node for details.", id="details")
        yield Footer()

    def on_mount(self) -> None:
        self.push_screen(WelcomeScreen(), self._on_welcome_done)

    def _on_welcome_done(self, start: bool) -> None:
        if not start:
            self.exit(0)
            return
        self._main_started = True
        self._start_main()

    def _start_main(self) -> None:
        try:
            tree = self.query_one("#dep_tree", Tree)
            if self._root_package:
                self._load_tree(self._root_package)
            else:
                packages = list_known_packages()
                if not packages:
                    self._set_details(
                        "No ROS 2 packages found. Set AMENT_PREFIX_PATH or run from a workspace."
                    )
                    tree.root.add_leaf("[dim]No packages in environment[/]")
                    return
                tree.root.label = "Known packages"
                names = sorted(packages.keys())[:MAX_PACKAGES_IN_LIST]
                for name in names:
                    tn = tree.root.add(f"[bold]{name}[/]", expand=False)
                    tn.data = name
                if len(packages) > MAX_PACKAGES_IN_LIST:
                    tree.root.add_leaf(f"[dim]… and {len(packages) - MAX_PACKAGES_IN_LIST} more[/]")
                self._set_details(
                    f"Found {len(packages)} packages. Select one to load its dependency tree."
                )
        except Exception as e:
            self._set_details(f"[red]Error: {e!s}[/]")
            tree = self.query_one("#dep_tree", Tree)
            tree.root.add_leaf("[dim]Error loading packages[/]")

    def _clear_tree(self, tree: Tree) -> None:
        while tree.root.children:
            tree.root.children[0].remove()

    def _load_tree(self, root_package: str) -> None:
        self._root_package = root_package
        try:
            self._root_node = build_tree(root_package)
        except Exception as e:
            self._set_details(f"[red]Error building tree: {e!s}[/]")
            return
        if self._root_node is None:
            self._set_details(f"Package not found: {root_package}")
            return
        tree = self.query_one("#dep_tree", Tree)
        self._clear_tree(tree)
        tree.root.label = (
            f"[bold]{self._root_node.name}[/] [dim]v{self._root_node.version or '?'}[/]"
        )
        tree.root.data = self._root_node
        _populate_textual_tree(tree.root, self._root_node)
        try:
            _expand_to_depth(tree.root, EXPAND_DEPTH_DEFAULT)
        except Exception:
            pass
        self._set_details(self._format_node(self._root_node))

    def _format_node(self, node: Any) -> str:
        lines = [
            f"[bold]{node.name}[/]  [dim]v{node.version or '?'}[/]",
            "",
            getattr(node, "description", "") or "(no description)",
            "",
            f"[dim]path: {getattr(node, 'path', '') or '(n/a)'}[/]",
        ]
        children = getattr(node, "children", [])
        if children:
            lines.append("")
            lines.append(f"[dim]dependencies: {len(children)}[/]")
        return "\n".join(lines)

    def _set_details(self, text: str) -> None:
        details = self.query_one("#details", Static)
        details.update(text)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        node = event.node.data
        if node is None:
            return
        if hasattr(node, "name") and hasattr(node, "children"):
            self._set_details(self._format_node(node))
        elif isinstance(node, str):
            self._load_tree(node)

    def action_refresh(self) -> None:
        if not self._main_started:
            return
        if self._root_package:
            self._load_tree(self._root_package)
        else:
            tree = self.query_one("#dep_tree", Tree)
            self._clear_tree(tree)
            self._start_main()

    def action_expand_all(self) -> None:
        tree = self.query_one("#dep_tree", Tree)
        try:
            tree.root.expand_all()
        except Exception:
            tree.root.expand()

    def action_collapse_all(self) -> None:
        tree = self.query_one("#dep_tree", Tree)
        try:
            tree.root.collapse_all()
            tree.root.expand()
        except Exception:
            pass

    def action_quit(self) -> None:
        self.exit()


def main() -> None:
    """Entry point for the rosdep_viz CLI."""
    root = None
    if len(sys.argv) > 1:
        root = sys.argv[1].strip()
    app = DepTreeApp(root_package=root)
    app.run()


if __name__ == "__main__":
    main()
