"""Textual TUI for navigating ROS 2 package dependency trees."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Static, Tree
from textual.widgets.tree import TreeNode

from rostree.api import build_tree, list_known_packages_by_source

# Welcome banner: ROSTREE
WELCOME_BANNER = """
[bold cyan]
██████╗  ██████╗ ███████╗████████╗██████╗ ███████╗███████╗
██╔══██╗██╔═══██╗██╔════╝╚══██╔══╝██╔══██╗██╔════╝██╔════╝
██████╔╝██║   ██║███████╗   ██║   ██████╔╝█████╗  █████╗
██╔══██╗██║   ██║╚════██║   ██║   ██╔══██╗██╔══╝  ██╔══╝
██║  ██║╚██████╔╝███████║   ██║   ██║  ██║███████╗███████╗
╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚══════╝
[/bold cyan]
"""

WELCOME_BODY = """
[dim]Visualize ROS 2 package dependencies as a navigable tree.[/]

  • [bold]CLI[/]:  rostree scan, rostree list, rostree tree <pkg>
  • [bold]TUI[/]:  browse packages, expand/collapse, see details
  • [bold]Library[/]: Python API for scripts and automation

[dim]Requires ROS 2 env (source install/setup.bash).[/]
"""

# Limits to avoid huge trees and crashes
MAX_PACKAGES_PER_SOURCE = 80  # max package names per source section
MAX_TREE_DEPTH = 8
MAX_TREE_NODES = 500
EXPAND_DEPTH_DEFAULT = 2
# TUI uses runtime_only=True (depend + exec_depend only)
TUI_TREE_MAX_DEPTH = 6

# Colors: source sections and tree
COLOR_SYSTEM = "dim"  # /opt/ros/...
COLOR_WORKSPACE = "bold green"  # your workspace
COLOR_OTHER = "bold cyan"  # third-party installs
COLOR_SOURCE = "bold yellow"  # unbuilt source
COLOR_ADDED = "bold magenta"  # user-added paths
COLOR_HEADER = "bold magenta"
COLOR_PKG = "white"
COLOR_STATS = "cyan"
COLOR_PATH = "dim"


def _count_nodes(node: Any) -> int:
    """Count nodes in tree (for cap)."""
    n = 1
    for c in getattr(node, "children", []):
        n += _count_nodes(c)
    return n


def _node_stats(node: Any) -> tuple[int, int, int]:
    """Return (direct_children, total_descendants, max_depth) for a node."""
    children = getattr(node, "children", []) or []
    direct = len(children)
    total = 0
    max_d = 0
    for c in children:
        sub_direct, sub_total, sub_depth = _node_stats(c)
        total += 1 + sub_total
        max_d = max(max_d, 1 + sub_depth)
    return direct, total, max_d


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
        label = f"[{COLOR_PKG}]{child.name}[/] [dim]v{child.version or '?'}[/]"
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


class WelcomeScreen(ModalScreen[bool]):
    """Welcome / presentation screen. Modal so Enter/q always work."""

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
            "[bold]This screen has focus.[/]  Press [cyan]Enter[/] to start  ·  [dim]q[/] to quit",
            id="welcome_footer",
            markup=True,
        )

    def on_mount(self) -> None:
        self.sub_title = "Enter = start · q = quit"

    def action_start(self) -> None:
        self.dismiss(True)

    def action_quit(self) -> None:
        self.dismiss(False)


class AddSourceScreen(ModalScreen[Path | None]):
    """Modal to enter a path to add as an extra source root. Keyboard-only: type path, Enter to add, Escape to cancel."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    AddSourceScreen {
        align: center middle;
        padding: 2 4;
    }
    AddSourceScreen #add_source_title {
        text-align: center;
        padding-bottom: 1;
    }
    AddSourceScreen #add_source_input {
        width: 60;
        margin: 1 0;
    }
    AddSourceScreen #add_source_hint {
        text-align: center;
        padding-top: 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._input: Input | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(
                "[bold cyan]Add source path[/]\n\n"
                "Type a directory path to scan for ROS 2 packages (e.g. /path/to/ws/src).",
                id="add_source_title",
                markup=True,
            )
            yield Input(
                placeholder="/path/to/source/dir",
                id="add_source_input",
            )
            yield Static(
                "[dim]Enter[/] = Add  ·  [dim]Escape[/] = Cancel",
                id="add_source_hint",
                markup=True,
            )

    def on_mount(self) -> None:
        self._input = self.query_one("#add_source_input", Input)
        self._input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Submit on Enter so no mouse/click needed."""
        if event.input.id != "add_source_input":
            return
        self._do_submit()

    def _do_submit(self) -> None:
        value = self._input.value.strip() if self._input else ""
        if not value:
            self.dismiss(None)
            return
        p = Path(value).expanduser().resolve()
        if not p.exists():
            self.notify(f"Path does not exist: {p}", severity="warning", timeout=3)
            return
        if not p.is_dir():
            self.notify(f"Not a directory: {p}", severity="warning", timeout=3)
            return
        self.dismiss(p)

    def action_cancel(self) -> None:
        self.dismiss(None)


class DepTreeApp(App[None]):
    """Terminal UI to explore ROS 2 package dependency trees."""

    TITLE = "rostree"
    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("b", "back", "Back", show=False),
        Binding("a", "add_source", "Add source"),
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
        self._extra_source_roots: list[Path] = []

    DEFAULT_CSS = """
    #back_bar {
        display: none;
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
    }
    #details {
        padding: 1 2;
        border: solid $primary;
        height: auto;
        min-height: 8;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="back_bar"):
            yield Button("← Back to package list", id="back_btn", variant="primary")
        yield Tree("Dependencies", id="dep_tree")
        yield Static(
            "[dim]↑/↓[/] move  ·  [dim]Enter[/]/[dim]Space[/] select  ·  [dim]Tab[/] = switch focus  ·  [dim]Esc[/]/[dim]b[/] = Back",
            id="details",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = "Tab = move focus · Esc = Back · Keys shown in footer"
        self.push_screen(WelcomeScreen(), self._on_welcome_done)

    def _on_welcome_done(self, start: bool) -> None:
        if not start:
            self.exit(0)
            return
        self._main_started = True
        self._start_main()

    def _source_color(self, label: str) -> str:
        if "System" in label:
            return COLOR_SYSTEM
        if "Workspace" in label:
            return COLOR_WORKSPACE
        if "Other" in label:
            return COLOR_OTHER
        if "Added" in label:
            return COLOR_ADDED
        return COLOR_SOURCE

    def _start_main(self) -> None:
        try:
            try:
                self.query_one("#back_bar").styles.display = "none"
            except Exception:
                pass
            tree = self.query_one("#dep_tree", Tree)
            if self._root_package:
                self._load_tree(self._root_package)
            else:
                by_source = list_known_packages_by_source(
                    extra_source_roots=self._extra_source_roots or None,
                )
                if not by_source:
                    self._set_details(
                        "No ROS 2 packages found. Set AMENT_PREFIX_PATH or run from a workspace.\n\n"
                        "[dim]a[/] = Add source path"
                    )
                    tree.root.add_leaf("[dim]No packages in environment[/]")
                    try:
                        tree.focus()
                    except Exception:
                        pass
                    return
                total = sum(len(names) for names in by_source.values())
                tree.root.label = f"[{COLOR_HEADER}]Packages by source[/]"
                # Order: System, Workspace, Other, Source, Added
                order = ["System", "Workspace", "Other", "Source", "Added"]
                sorted_keys = sorted(
                    by_source.keys(),
                    key=lambda k: next((i for i, o in enumerate(order) if o in k), 99),
                )
                recap_parts = []
                for label in sorted_keys:
                    names = by_source[label]
                    color = self._source_color(label)
                    section_node = tree.root.add(
                        f"[{color}]{label} ({len(names)})[/]",
                        expand=True,
                    )
                    recap_parts.append(f"[{color}]{label.split('(')[0].strip()}: {len(names)}[/]")
                    for name in names[:MAX_PACKAGES_PER_SOURCE]:
                        child_tn = section_node.add(f"[{color}]{name}[/]", expand=False)
                        child_tn.data = name
                    if len(names) > MAX_PACKAGES_PER_SOURCE:
                        section_node.add_leaf(
                            f"[dim]… and {len(names) - MAX_PACKAGES_PER_SOURCE} more[/]"
                        )
                self._set_details(
                    f"[{COLOR_HEADER}]Package list[/]\n\n"
                    f"Total: [{COLOR_STATS}]{total}[/] packages  ·  "
                    + "  ·  ".join(recap_parts)
                    + "\n\n"
                    "[dim]↑/↓[/] move  ·  [dim]Enter[/] or [dim]Space[/] on a package = load tree  ·  "
                    "[dim]a[/] = Add source  ·  [dim]Esc[/]/[dim]b[/] = Back (when viewing a tree)"
                )
            try:
                self.query_one("#dep_tree", Tree).focus()
            except Exception:
                pass
        except Exception as e:
            self._set_details(f"[red]Error: {e!s}[/]")
            tree = self.query_one("#dep_tree", Tree)
            tree.root.add_leaf("[dim]Error loading packages[/]")
            try:
                tree.focus()
            except Exception:
                pass

    def _clear_tree(self, tree: Tree) -> None:
        while tree.root.children:
            tree.root.children[0].remove()

    def _load_tree(self, root_package: str) -> None:
        self._root_package = root_package
        try:
            self._root_node = build_tree(
                root_package,
                max_depth=TUI_TREE_MAX_DEPTH,
                runtime_only=True,
                extra_source_roots=self._extra_source_roots or None,
            )
        except Exception as e:
            self._set_details(f"[red]Error building tree: {e!s}[/]")
            return
        if self._root_node is None:
            self._set_details(f"Package not found: {root_package}")
            return
        tree = self.query_one("#dep_tree", Tree)
        self._clear_tree(tree)
        tree.root.label = (
            f"[{COLOR_HEADER}]{self._root_node.name}[/] [dim]v{self._root_node.version or '?'}[/]"
        )
        tree.root.data = self._root_node
        _populate_textual_tree(tree.root, self._root_node)
        try:
            _expand_to_depth(tree.root, EXPAND_DEPTH_DEFAULT)
        except Exception:
            pass
        self._set_details(
            self._format_node(self._root_node)
            + "\n\n[dim]Esc[/] or [dim]b[/] = Back to package list  ·  [dim]Tab[/] then [dim]Enter[/] = Back button"
        )
        try:
            self.query_one("#back_bar").styles.display = "block"
            self.query_one("#dep_tree", Tree).focus()
        except Exception:
            pass

    def _format_node(self, node: Any) -> str:
        name = getattr(node, "name", "?")
        version = getattr(node, "version", "") or "?"
        desc = getattr(node, "description", "") or "(no description)"
        path = getattr(node, "path", "") or "(n/a)"

        direct, total_desc, max_depth = _node_stats(node)

        lines = [
            f"[{COLOR_HEADER}]Package[/]",
            f"  [{COLOR_PKG}]{name}[/]  [dim]v{version}[/]",
            "",
            f"[{COLOR_HEADER}]Description[/]",
            f"  {desc}",
            "",
            f"[{COLOR_HEADER}]Stats[/]",
            f"  Direct dependencies:   [{COLOR_STATS}]{direct}[/]",
            f"  Total descendants:     [{COLOR_STATS}]{total_desc}[/] [dim](indirect)[/]",
            f"  Max depth from here:  [{COLOR_STATS}]{max_depth}[/] [dim]levels[/]",
            "",
            f"[{COLOR_HEADER}]Path[/]",
            f"  [{COLOR_PATH}]{path}[/]",
        ]
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

    def action_back(self) -> None:
        """Return to the known packages list (only when viewing a tree)."""
        if not self._main_started or not self._root_package:
            return
        self._root_package = None
        self._root_node = None
        try:
            self.query_one("#back_bar").styles.display = "none"
        except Exception:
            pass
        tree = self.query_one("#dep_tree", Tree)
        self._clear_tree(tree)
        self._start_main()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back_btn":
            self.action_back()

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

    def action_add_source(self) -> None:
        """Open modal to add an extra source path."""
        if not self._main_started:
            return
        self.push_screen(AddSourceScreen(), self._on_add_source_done)

    def _on_add_source_done(self, path: Path | None) -> None:
        if path is None:
            return
        if path in self._extra_source_roots:
            self.notify("Path already added", severity="information", timeout=2)
            return
        self._extra_source_roots.append(path)
        self.notify(f"Added: {path}", severity="information", timeout=2)
        self.action_refresh()
        try:
            self.query_one("#dep_tree", Tree).focus()
        except Exception:
            pass

    def action_quit(self) -> None:
        self.exit()


def main() -> None:
    """Entry point for the rostree TUI."""
    root = None
    if len(sys.argv) > 1:
        root = sys.argv[1].strip()
    app = DepTreeApp(root_package=root)
    app.run()


if __name__ == "__main__":
    main()
