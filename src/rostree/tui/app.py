"""Textual TUI for navigating ROS 2 package dependency trees."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, LoadingIndicator, Static, Tree
from textual.widgets.tree import TreeNode
from textual.worker import Worker, WorkerState

from rostree.api import build_tree, list_known_packages_by_source

# Welcome banner: ROSTREE (all lines must be same length for proper centering)
WELCOME_BANNER = """\
[bold cyan]
██████╗  ██████╗ ███████╗████████╗██████╗ ███████╗███████╗
██╔══██╗██╔═══██╗██╔════╝╚══██╔══╝██╔══██╗██╔════╝██╔════╝
██████╔╝██║   ██║███████╗   ██║   ██████╔╝█████╗  █████╗  
██╔══██╗██║   ██║╚════██║   ██║   ██╔══██╗██╔══╝  ██╔══╝  
██║  ██║╚██████╔╝███████║   ██║   ██║  ██║███████╗███████╗
╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚══════╝
[/bold cyan]"""

WELCOME_DESC = """[dim]Navigate and visualize ROS 2 package dependency trees.
Discover packages from your workspace, system installs, and custom paths.
Search, expand, and explore the full dependency graph interactively.[/]"""

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


class SearchScreen(ModalScreen[str | None]):
    """Modal to search for packages/nodes in the tree. Keyboard-only."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    SearchScreen {
        align: center middle;
        padding: 2 4;
    }
    SearchScreen #search_title {
        text-align: center;
        padding-bottom: 1;
    }
    SearchScreen #search_input {
        width: 60;
        margin: 1 0;
    }
    SearchScreen #search_hint {
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
                "[bold cyan]Search[/]\n\n"
                "Type a package name or partial match to find in the tree.",
                id="search_title",
                markup=True,
            )
            yield Input(
                placeholder="package name...",
                id="search_input",
            )
            yield Static(
                "[dim]Enter[/] = Search  ·  [dim]Escape[/] = Cancel\n"
                "[dim]After search: [bold]n[/bold] = next match, [bold]N[/bold] = previous[/]",
                id="search_hint",
                markup=True,
            )

    def on_mount(self) -> None:
        self._input = self.query_one("#search_input", Input)
        self._input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "search_input":
            return
        value = self._input.value.strip() if self._input else ""
        self.dismiss(value if value else None)

    def action_cancel(self) -> None:
        self.dismiss(None)


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
        Binding("enter", "start_main", "Start", show=False),
        Binding("escape", "back", "Back", show=True),
        Binding("b", "back", "Back", show=False),
        Binding("a", "add_source", "Add source"),
        Binding("/", "search", "Search"),
        Binding("f", "search", "Search", show=False),
        Binding("n", "next_match", "Next match", show=False),
        Binding("N", "prev_match", "Prev match", show=False),
        Binding("d", "toggle_details", "Details"),
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
        self._search_query: str = ""
        self._search_matches: list[TreeNode] = []
        self._search_index: int = 0
        self._details_visible: bool = True
        # Background loading state
        self._packages_cache: dict[str, list[str]] | None = None
        self._packages_loading: bool = False
        self._packages_error: str | None = None

    DEFAULT_CSS = """
    /* Welcome screen styles */
    #welcome_container {
        align: center middle;
        width: 100%;
        height: 100%;
    }
    #welcome_banner {
        text-align: center;
        content-align: center middle;
        width: 100%;
    }
    #welcome_desc {
        text-align: center;
        padding: 2 4;
    }
    #welcome_hint {
        text-align: center;
        padding-top: 1;
    }
    #welcome_loading {
        text-align: center;
        padding-top: 1;
        display: none;
    }
    #welcome_loading.loading {
        display: block;
    }
    #welcome_loading LoadingIndicator {
        background: transparent;
    }
    /* Main view styles */
    #main_container {
        display: none;
    }
    #nav_hint {
        display: none;
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
        color: $text-muted;
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
        # Welcome view (initial)
        with Container(id="welcome_container"):
            yield Static(WELCOME_BANNER, id="welcome_banner", markup=True)
            yield Static(WELCOME_DESC, id="welcome_desc", markup=True)
            yield Static(
                "[cyan]Enter[/] to explore  ·  [dim]q[/] to quit",
                id="welcome_hint",
                markup=True,
            )
            # Loading indicator (shown while scanning)
            with Container(id="welcome_loading"):
                yield LoadingIndicator()
                yield Static("[dim]Scanning for packages...[/]", id="loading_text", markup=True)
        # Main view (hidden initially)
        with Container(id="main_container"):
            yield Static(
                "[dim]← Press [bold]Esc[/bold] or [bold]b[/bold] to return to package list[/]",
                id="nav_hint",
            )
            yield Tree("Dependencies", id="dep_tree")
            yield Static(
                "[dim]↑/↓[/] move  ·  [dim]Enter[/]/[dim]Space[/] select  ·  [dim]Esc[/]/[dim]b[/] = Back",
                id="details",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = "Dependency Tree Explorer"
        # Start loading packages in the background immediately
        self._start_package_scan()

    def on_key(self, event: Any) -> None:
        """Handle key events - specifically Enter on welcome screen."""
        if not self._main_started and event.key == "enter":
            event.prevent_default()
            event.stop()
            self.action_start_main()

    def _start_package_scan(self) -> None:
        """Start scanning for packages in the background."""
        if self._packages_cache is not None or self._packages_loading:
            return  # Already loaded or loading
        self._packages_loading = True
        # Show loading indicator
        try:
            loading_container = self.query_one("#welcome_loading")
            loading_container.add_class("loading")
        except Exception:
            pass
        # Start background worker
        self.run_worker(self._scan_packages_worker, thread=True)

    def _scan_packages_worker(self) -> dict[str, list[str]]:
        """Worker that scans for packages in a background thread."""
        return list_known_packages_by_source(
            extra_source_roots=self._extra_source_roots or None,
        )

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker completion."""
        if event.state == WorkerState.SUCCESS:
            self._packages_cache = event.worker.result
            self._packages_loading = False
            self._packages_error = None
            # Update loading indicator
            self._update_loading_status()
        elif event.state == WorkerState.ERROR:
            self._packages_loading = False
            self._packages_error = str(event.worker.error)
            self._update_loading_status()

    def _update_loading_status(self) -> None:
        """Update loading indicator status."""
        try:
            loading_container = self.query_one("#welcome_loading")
            loading_text = self.query_one("#loading_text", Static)
            if self._packages_cache is not None:
                total = sum(len(v) for v in self._packages_cache.values())
                loading_container.remove_class("loading")
                # Update hint to show ready status
                hint = self.query_one("#welcome_hint", Static)
                hint.update(
                    f"[green]✓[/] {total} packages found  ·  [cyan]Enter[/] to explore  ·  [dim]q[/] to quit"
                )
            elif self._packages_error:
                loading_text.update(f"[red]Error: {self._packages_error}[/]")
        except Exception:
            pass

    def _check_loading_complete(self) -> None:
        """Check if background loading is complete and update main view."""
        if self._packages_loading:
            # Still loading, check again later
            self.set_timer(0.3, self._check_loading_complete)
            return
        # Loading complete, refresh main view
        if self._main_started:
            tree = self.query_one("#dep_tree", Tree)
            self._clear_tree(tree)
            self._load_main_view()

    def action_start_main(self) -> None:
        """Transition from welcome screen to main view."""
        if self._main_started:
            return
        self._main_started = True
        # Hide welcome, show main
        try:
            self.query_one("#welcome_container").styles.display = "none"
            self.query_one("#main_container").styles.display = "block"
        except Exception:
            pass
        self._load_main_view()

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

    def _load_main_view(self) -> None:
        try:
            try:
                self.query_one("#nav_hint").styles.display = "none"
            except Exception:
                pass
            tree = self.query_one("#dep_tree", Tree)
            if self._root_package:
                self._load_tree(self._root_package)
            else:
                # Use cached packages if available, otherwise load (fallback)
                if self._packages_loading:
                    # Still loading - show loading message and wait
                    tree.root.label = f"[{COLOR_HEADER}]Loading packages...[/]"
                    tree.root.add_leaf("[dim]Scanning for packages, please wait...[/]")
                    self._set_details("[dim]Scanning for ROS 2 packages in background...[/]")
                    try:
                        tree.focus()
                    except Exception:
                        pass
                    # Set a timer to check again
                    self.set_timer(0.5, self._check_loading_complete)
                    return
                by_source = self._packages_cache
                if by_source is None:
                    # Cache not available, load synchronously (fallback)
                    by_source = list_known_packages_by_source(
                        extra_source_roots=self._extra_source_roots or None,
                    )
                    self._packages_cache = by_source
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
        self._set_details(self._format_node(self._root_node))
        try:
            self.query_one("#nav_hint").styles.display = "block"
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
            self.query_one("#nav_hint").styles.display = "none"
        except Exception:
            pass
        tree = self.query_one("#dep_tree", Tree)
        self._clear_tree(tree)
        self._load_main_view()

    def action_refresh(self) -> None:
        if not self._main_started:
            return
        if self._root_package:
            self._load_tree(self._root_package)
        else:
            # Clear cache to force rescan
            self._packages_cache = None
            self._packages_loading = False
            tree = self.query_one("#dep_tree", Tree)
            self._clear_tree(tree)
            # Start background scan and show loading
            self._start_package_scan()
            self._load_main_view()

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

    def action_search(self) -> None:
        """Open search modal."""
        if not self._main_started:
            return
        self.push_screen(SearchScreen(), self._on_search_done)

    def _on_search_done(self, query: str | None) -> None:
        if not query:
            return
        self._search_query = query.lower()
        self._search_matches = []
        self._search_index = 0

        tree = self.query_one("#dep_tree", Tree)
        self._collect_matches(tree.root, query.lower())

        if not self._search_matches:
            self.notify(f"No matches for '{query}'", severity="warning", timeout=2)
            return

        self.notify(
            f"Found {len(self._search_matches)} match(es) for '{query}'",
            severity="information",
            timeout=2,
        )
        self._goto_match(0)

    def _collect_matches(self, node: TreeNode, query: str) -> None:
        """Recursively collect nodes matching the search query."""
        label = str(node.label).lower()
        # Also check the data if it's a string (package name)
        data_str = str(node.data).lower() if node.data else ""
        if query in label or query in data_str:
            self._search_matches.append(node)
        for child in node.children:
            self._collect_matches(child, query)

    def _goto_match(self, index: int) -> None:
        """Navigate to and select a specific match."""
        if not self._search_matches:
            return
        self._search_index = index % len(self._search_matches)
        match_node = self._search_matches[self._search_index]

        # Expand all ancestors so the node is visible
        self._expand_ancestors(match_node)

        # Select the node
        tree = self.query_one("#dep_tree", Tree)
        tree.select_node(match_node)
        tree.scroll_to_node(match_node)

        # Show match info
        total = len(self._search_matches)
        current = self._search_index + 1
        self.notify(
            f"Match {current}/{total}: {match_node.label}",
            severity="information",
            timeout=2,
        )

    def _expand_ancestors(self, node: TreeNode) -> None:
        """Expand all ancestor nodes to make the target visible."""
        ancestors = []
        parent = node.parent
        while parent is not None:
            ancestors.append(parent)
            parent = parent.parent
        for ancestor in reversed(ancestors):
            ancestor.expand()

    def action_next_match(self) -> None:
        """Go to next search match."""
        if not self._search_matches:
            self.notify("No active search. Press / to search.", severity="information", timeout=2)
            return
        self._goto_match(self._search_index + 1)

    def action_prev_match(self) -> None:
        """Go to previous search match."""
        if not self._search_matches:
            self.notify("No active search. Press / to search.", severity="information", timeout=2)
            return
        self._goto_match(self._search_index - 1)

    def action_toggle_details(self) -> None:
        """Toggle visibility of the details panel."""
        self._details_visible = not self._details_visible
        try:
            details = self.query_one("#details", Static)
            details.styles.display = "block" if self._details_visible else "none"
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
