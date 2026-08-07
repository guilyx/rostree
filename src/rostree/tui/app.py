"""Textual TUI for navigating ROS 2 package dependency trees."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, LoadingIndicator, Static, Tree
from textual.widgets.tree import TreeNode

from rostree.api import build_tree, get_index
from rostree.core.index import PackageEntry, PackageIndex, SourceKind
from rostree.core.tree import NodeStatus, tree_stats

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

# Children are added to the widget tree only when a node is expanded, so these
# are the limits of a single expansion step rather than of the whole tree.
MAX_TREE_DEPTH = 64
MAX_TREE_NODES = 100_000
EXPAND_DEPTH_DEFAULT = 2
TUI_TREE_MAX_DEPTH = None  # unlimited: repeats are collapsed, so trees stay small
#: Package list sections start collapsed above this size, to keep the list scannable.
LARGE_SECTION = 40

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

_SOURCE_COLOR = {
    SourceKind.SYSTEM: COLOR_SYSTEM,
    SourceKind.WORKSPACE: COLOR_WORKSPACE,
    SourceKind.OTHER: COLOR_OTHER,
    SourceKind.SOURCE: COLOR_SOURCE,
    SourceKind.ADDED: COLOR_ADDED,
}

_STATUS_SUFFIX = {
    NodeStatus.REPEAT: "[dim] ↩ shown above[/]",
    NodeStatus.CYCLE: "[yellow] ⟳ cycle[/]",
    NodeStatus.MISSING: "[red] ✗ not found[/]",
    NodeStatus.PARSE_ERROR: "[red] ! parse error[/]",
    NodeStatus.TRUNCATED: "[dim] … depth limit[/]",
}


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
        _sub_direct, sub_total, sub_depth = _node_stats(c)
        total += 1 + sub_total
        max_d = max(max_d, 1 + sub_depth)
    return direct, total, max_d


def _short_label(label: str, *, keep: int = 34) -> str:
    """
    Shorten a source label like ``Workspace (/very/long/path)`` for a narrow pane.

    The kind is what you scan for; the path only has to stay recognisable.
    """
    if "(" not in label or not label.endswith(")"):
        return label
    kind, _, rest = label.partition(" (")
    path = rest[:-1]
    home = str(Path.home())
    if path.startswith(home):
        path = "~" + path[len(home) :]
    if len(path) > keep:
        parts = Path(path).parts
        tail = str(Path(*parts[-2:])) if len(parts) > 2 else path
        path = f"…/{tail}"
    return f"{kind} ({path})"


def _dep_label(node: Any) -> str:
    """Markup for one dependency-tree row."""
    status = getattr(node, "status", NodeStatus.OK)
    version = getattr(node, "version", "")
    label = f"[{COLOR_PKG}]{node.name}[/]"
    if version:
        label += f" [dim]v{version}[/]"
    return label + _STATUS_SUFFIX.get(status, "")


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
        child_tn = tn.add(_dep_label(child), expand=False)
        child_tn.data = child
        _populate_textual_tree(
            child_tn,
            child,
            depth=depth + 1,
            max_depth=max_depth,
            max_nodes=max_nodes,
            node_count=node_count,
        )


def _add_lazy_child(tn: TreeNode, child: Any) -> TreeNode:
    """
    Add one dependency row, deferring its own children until it is expanded.

    Materialising a whole tree of widgets up front is what used to make opening a
    large package feel like a hang; this way each expansion costs only its own row.
    """
    has_children = bool(getattr(child, "children", None))
    if has_children:
        node = tn.add(_dep_label(child), expand=False)
    else:
        node = tn.add_leaf(_dep_label(child))
    node.data = child
    return node


def _populate_lazy(tn: TreeNode, node: Any) -> None:
    """Add the direct children of ``node`` to ``tn`` exactly once."""
    if getattr(tn, "_rostree_filled", False):
        return
    tn._rostree_filled = True  # type: ignore[attr-defined]
    for child in getattr(node, "children", []):
        _add_lazy_child(tn, child)


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


class HelpScreen(ModalScreen[None]):
    """Keyboard reference."""

    BINDINGS = [
        Binding("escape", "dismiss_help", "Close", show=True),
        Binding("question_mark", "dismiss_help", "Close", show=False),
    ]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen #help_body {
        width: 66;
        border: round $primary;
        padding: 1 2;
        background: $surface;
    }
    """

    HELP = """[bold cyan]rostree — keyboard reference[/]

[bold]Everywhere[/]
  [cyan]?[/]          this help          [cyan]q[/]  quit
  [cyan]r[/]          rescan packages    [cyan]a[/]  add a source path
  [cyan]Esc[/]        back / clear filter

[bold]Package list[/]
  [cyan]/[/]          filter packages as you type
  [cyan]↑ ↓[/]        move                [cyan]Enter[/]  open dependency tree

[bold]Dependency tree[/]
  [cyan]Enter[/]      focus that package as the new root
  [cyan]e[/] / [cyan]c[/]      expand all / collapse all
  [cyan]n[/] / [cyan]N[/]      next / previous search match
  [cyan]d[/]          show or hide the details panel
  [cyan]v[/]          reverse view: what depends on this package
  [cyan]t[/]          toggle runtime-only vs all dependencies

[dim]Repeated packages are expanded where they first appear and marked
"↩ shown above" elsewhere, which is what keeps big trees fast.[/]"""

    def compose(self) -> ComposeResult:
        yield Static(self.HELP, id="help_body", markup=True)

    def action_dismiss_help(self) -> None:
        self.dismiss(None)


class AddSourceScreen(ModalScreen[Path | None]):
    """Modal to enter a path to add as an extra source root."""

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
            yield Input(placeholder="/path/to/source/dir", id="add_source_input")
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


# Kept for callers that imported it before the inline filter replaced the modal.
class SearchScreen(ModalScreen[str | None]):
    """Modal to search for packages/nodes in the tree. Keyboard-only."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=True)]

    DEFAULT_CSS = """
    SearchScreen { align: center middle; padding: 2 4; }
    SearchScreen #search_input { width: 60; margin: 1 0; }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("[bold cyan]Search[/]", id="search_title", markup=True)
            yield Input(placeholder="package name...", id="search_input")

    def on_mount(self) -> None:
        self.query_one("#search_input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        self.dismiss(value or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class DepTreeApp(App[None]):
    """Terminal UI to explore ROS 2 package dependency trees."""

    TITLE = "rostree"
    BINDINGS = [
        Binding("enter", "start_main", "Start", show=False),
        Binding("escape", "back", "Back", show=True),
        Binding("b", "back", "Back", show=False),
        Binding("slash", "focus_filter", "Filter"),
        Binding("f", "focus_filter", "Filter", show=False),
        Binding("n", "next_match", "Next match", show=False),
        Binding("N", "prev_match", "Prev match", show=False),
        Binding("d", "toggle_details", "Details"),
        Binding("v", "toggle_reverse", "Dependents"),
        Binding("t", "toggle_scope", "Dep scope"),
        Binding("a", "add_source", "Add source", show=False),
        Binding("e", "expand_all", "Expand all", show=False),
        Binding("c", "collapse_all", "Collapse", show=False),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("question_mark", "help", "Help"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        root_package: str | None = None,
        runtime_only: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._root_package = root_package
        self._root_node: Any = None
        self._main_started = False
        self._extra_source_roots: list[Path] = []
        self._runtime_only = runtime_only
        self._reverse_view = False
        self._search_query: str = ""
        self._search_matches: list[TreeNode] = []
        self._search_index: int = 0
        self._details_visible: bool = True
        self._filter: str = ""
        self._filter_timer: Any = None
        #: Last text rendered into the status bar / details panel (handy for tests).
        self.status_text: str = ""
        self.details_text: str = ""
        # Background loading state
        self._index: PackageIndex | None = None
        self._packages_cache: dict[str, list[str]] | None = None
        self._packages_loading: bool = False
        self._packages_error: str | None = None
        self._building: bool = False

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
    #status_bar {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        background: $panel;
    }
    #filter_input {
        height: 3;
        display: none;
    }
    #filter_input.visible {
        display: block;
    }
    #body {
        height: 1fr;
    }
    #dep_tree {
        width: 1fr;
    }
    #details {
        width: 46;
        padding: 1 2;
        border-left: solid $primary;
        overflow-y: auto;
    }
    #details.hidden {
        display: none;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        # Welcome view (initial)
        with Container(id="welcome_container"):
            yield Static(WELCOME_BANNER, id="welcome_banner", markup=True)
            yield Static(WELCOME_DESC, id="welcome_desc", markup=True)
            yield Static(
                "[cyan]Enter[/] to explore  ·  [dim]?[/] for help  ·  [dim]q[/] to quit",
                id="welcome_hint",
                markup=True,
            )
            # Loading indicator (shown while scanning)
            with Container(id="welcome_loading"):
                yield LoadingIndicator()
                yield Static("[dim]Scanning for packages...[/]", id="loading_text", markup=True)
        # Main view (hidden initially)
        with Vertical(id="main_container"):
            yield Static("", id="status_bar", markup=True)
            yield Input(placeholder="filter packages…", id="filter_input")
            with Horizontal(id="body"):
                yield Tree("Dependencies", id="dep_tree")
                yield Static("", id="details", markup=True)
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

    # ------------------------------------------------------------------ scanning

    def _start_package_scan(self) -> None:
        """Start scanning for packages in the background."""
        if self._packages_cache is not None or self._packages_loading:
            return  # Already loaded or loading
        self._packages_loading = True
        try:
            self.query_one("#welcome_loading").add_class("loading")
        except Exception:
            pass
        self.run_worker(self._scan_packages_worker, thread=True, exclusive=False)

    def _scan_packages_worker(self) -> None:
        """Build the package index off the UI thread, then hand it back."""
        try:
            index = get_index(
                extra_source_roots=self._extra_source_roots or None,
                refresh=True,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self.call_from_thread(self._on_scan_failed, str(exc))
            return
        self.call_from_thread(self._on_scan_done, index)

    def _on_scan_done(self, index: PackageIndex) -> None:
        self._index = index
        self._packages_cache = index.by_label()
        self._packages_loading = False
        self._packages_error = None
        self._update_loading_status()
        if self._main_started and not self._root_package:
            self._load_main_view()
        elif self._main_started and self._root_package and self._root_node is None:
            self._load_tree(self._root_package)

    def _on_scan_failed(self, message: str) -> None:
        self._packages_loading = False
        self._packages_error = message
        self._update_loading_status()

    def _update_loading_status(self) -> None:
        """Update loading indicator status."""
        try:
            loading_container = self.query_one("#welcome_loading")
            loading_text = self.query_one("#loading_text", Static)
            if self._packages_cache is not None:
                total = sum(len(v) for v in self._packages_cache.values())
                loading_container.remove_class("loading")
                hint = self.query_one("#welcome_hint", Static)
                hint.update(
                    f"[green]✓[/] {total} packages found  ·  [cyan]Enter[/] to explore  ·  "
                    "[dim]?[/] for help  ·  [dim]q[/] to quit"
                )
            elif self._packages_error:
                loading_text.update(f"[red]Error: {self._packages_error}[/]")
        except Exception:
            pass

    def action_start_main(self) -> None:
        """Transition from welcome screen to main view."""
        if self._main_started:
            return
        self._main_started = True
        try:
            self.query_one("#welcome_container").styles.display = "none"
            self.query_one("#main_container").styles.display = "block"
        except Exception:
            pass
        if self._root_package:
            self._load_tree(self._root_package)
        else:
            self._load_main_view()
        # Keys like d/v/t are app bindings; they only work when the tree, not the
        # filter box, holds focus, so claim it explicitly on entry.
        self._focus_tree(force=True)

    # ------------------------------------------------------------- package list

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

    def _set_status(self, text: str) -> None:
        self.status_text = text
        try:
            self.query_one("#status_bar", Static).update(text)
        except Exception:
            pass

    def _mode_suffix(self) -> str:
        scope = "runtime deps" if self._runtime_only else "all deps"
        return f"[dim]{scope}  ·  [/][dim]? for help[/]"

    def _load_main_view(self) -> None:
        """Show every known package, grouped by source and honouring the filter."""
        try:
            self.query_one("#filter_input").add_class("visible")
        except Exception:
            pass
        try:
            tree = self.query_one("#dep_tree", Tree)
            self._clear_tree(tree)

            tree.root.expand()
            if self._packages_loading or self._packages_cache is None:
                tree.root.label = f"[{COLOR_HEADER}]Scanning for packages…[/]"
                tree.root.add_leaf("[dim]This runs in the background; the UI stays usable.[/]")
                self._set_details("[dim]Scanning for ROS 2 packages…[/]")
                self._set_status("[dim]Scanning…[/]")
                self._focus_tree()
                return

            by_source = self._packages_cache
            if not by_source:
                self._set_details(
                    "No ROS 2 packages found. Source your setup.bash, or press "
                    "[bold]a[/] to add a source path."
                )
                tree.root.label = f"[{COLOR_HEADER}]No packages[/]"
                tree.root.add_leaf("[dim]No packages in environment[/]")
                self._set_status("[yellow]0 packages[/]")
                self._focus_tree()
                return

            needle = self._filter.lower()
            total = sum(len(names) for names in by_source.values())
            order = ["System", "Workspace", "Other", "Source", "Added"]
            sorted_keys = sorted(
                by_source.keys(),
                key=lambda k: next((i for i, o in enumerate(order) if o in k), 99),
            )

            shown = 0
            recap_parts = []
            for label in sorted_keys:
                names = [n for n in by_source[label] if needle in n.lower()]
                if not names:
                    continue
                shown += len(names)
                color = self._source_color(label)
                # Your own packages are what you came for, so they open by default;
                # a big ROS distro section stays folded until you filter or open it.
                expand = bool(needle) or "System" not in label or len(names) <= LARGE_SECTION
                section_node = tree.root.add(
                    f"[{color}]{_short_label(label)} ({len(names)})[/]",
                    expand=expand,
                )
                recap_parts.append(f"[{color}]{label.split('(')[0].strip()}: {len(names)}[/]")
                for name in names:
                    child_tn = section_node.add_leaf(f"[{color}]{name}[/]")
                    child_tn.data = name

            if self._filter:
                tree.root.label = (
                    f"[{COLOR_HEADER}]Packages matching '{self._filter}'[/] "
                    f"[dim]({shown} of {total})[/]"
                )
                self._set_status(f"[cyan]{shown}[/] of {total} packages  ·  {self._mode_suffix()}")
            else:
                tree.root.label = f"[{COLOR_HEADER}]Packages by source[/]"
                self._set_status(f"[cyan]{total}[/] packages  ·  {self._mode_suffix()}")

            if shown == 0:
                tree.root.add_leaf(f"[dim]No package matches '{self._filter}'[/]")

            self._set_details(
                f"[{COLOR_HEADER}]Package list[/]\n\n"
                f"Total: [{COLOR_STATS}]{total}[/] packages\n" + "\n".join(recap_parts) + "\n\n"
                "[dim]/[/] filter  ·  [dim]Enter[/] open a package\n"
                "[dim]a[/] add a source path  ·  [dim]?[/] help"
            )
            self._focus_tree()
        except Exception as e:
            self._set_details(f"[red]Error: {e!s}[/]")

    def _clear_tree(self, tree: Tree) -> None:
        while tree.root.children:
            tree.root.children[0].remove()

    def _focus_tree(self, *, force: bool = False) -> None:
        """Focus the tree, unless the user is mid-keystroke in the filter box."""
        focused = self.focused
        if not force and focused is not None and getattr(focused, "id", None) == "filter_input":
            return
        try:
            self.query_one("#dep_tree", Tree).focus()
        except Exception:
            pass

    # ----------------------------------------------------------- dependency tree

    def _load_tree(self, root_package: str) -> None:
        """Kick off a background build of the dependency tree for a package."""
        self._root_package = root_package
        self._search_matches = []
        if self._building:
            return
        self._building = True
        try:
            self.query_one("#filter_input").remove_class("visible")
        except Exception:
            pass
        tree = self.query_one("#dep_tree", Tree)
        self._clear_tree(tree)
        tree.root.label = f"[{COLOR_HEADER}]{root_package}[/] [dim]building…[/]"
        self._set_status(f"[dim]Resolving dependencies of {root_package}…[/]")
        self.run_worker(
            lambda: self._build_tree_worker(root_package),
            thread=True,
            exclusive=False,
        )

    def _build_tree_worker(self, root_package: str) -> None:
        """Resolve a dependency tree off the UI thread."""
        try:
            node = build_tree(
                root_package,
                max_depth=TUI_TREE_MAX_DEPTH,
                runtime_only=self._runtime_only,
                extra_source_roots=self._extra_source_roots or None,
            )
        except Exception as exc:
            self.call_from_thread(self._on_tree_failed, root_package, str(exc))
            return
        self.call_from_thread(self._on_tree_built, root_package, node)

    def _on_tree_failed(self, root_package: str, message: str) -> None:
        self._building = False
        self._set_details(f"[red]Error building tree for {root_package}: {message}[/]")
        self._set_status("[red]Build failed[/]")

    def _on_tree_built(self, root_package: str, node: Any) -> None:
        self._building = False
        if node is None:
            self._set_details(f"Package not found: {root_package}")
            self._set_status(f"[yellow]{root_package} not found[/]")
            return
        self._root_node = node
        tree = self.query_one("#dep_tree", Tree)
        self._clear_tree(tree)
        tree.root.label = _dep_label(node)
        tree.root.data = node
        tree.root._rostree_filled = True  # type: ignore[attr-defined]
        for child in node.children:
            _add_lazy_child(tree.root, child)
        _expand_to_depth(tree.root, EXPAND_DEPTH_DEFAULT)
        stats = tree_stats(node)
        self._set_status(
            f"[bold]{root_package}[/]  ·  [cyan]{stats['packages']}[/] packages  ·  "
            f"depth [cyan]{stats['depth']}[/]  ·  "
            + (f"[yellow]{stats['missing']} unresolved[/]  ·  " if stats["missing"] else "")
            + self._mode_suffix()
        )
        self._set_details(self._format_node(node))
        self._focus_tree()

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        """Materialise children the first time a node is opened."""
        node = event.node
        data = node.data
        if data is None or isinstance(data, str):
            return
        _populate_lazy(node, data)

    def _format_node(self, node: Any) -> str:
        name = getattr(node, "name", "?")
        version = getattr(node, "version", "") or "?"
        desc = getattr(node, "description", "") or "(no description)"
        path = getattr(node, "path", "") or "(n/a)"
        status = getattr(node, "status", NodeStatus.OK)

        direct, total_desc, max_depth = _node_stats(node)
        lines = [
            f"[{COLOR_HEADER}]Package[/]",
            f"  [{COLOR_PKG}]{name}[/]  [dim]v{version}[/]",
        ]
        if status is not NodeStatus.OK:
            lines.append(f"  {_STATUS_SUFFIX.get(status, '')}")
        lines += [
            "",
            f"[{COLOR_HEADER}]Description[/]",
            f"  {desc}",
            "",
            f"[{COLOR_HEADER}]Stats[/]",
            f"  Direct dependencies:   [{COLOR_STATS}]{direct}[/]",
            f"  Total descendants:     [{COLOR_STATS}]{total_desc}[/] [dim](indirect)[/]",
            f"  Max depth from here:  [{COLOR_STATS}]{max_depth}[/] [dim]levels[/]",
        ]
        entry = self._entry(name)
        if entry is not None:
            colour = _SOURCE_COLOR.get(entry.kind, COLOR_PKG)
            lines += [
                "",
                f"[{COLOR_HEADER}]Source[/]",
                f"  [{colour}]{_short_label(entry.label, keep=40)}[/]",
            ]
        lines += ["", f"[{COLOR_HEADER}]Path[/]", f"  [{COLOR_PATH}]{path}[/]"]
        return "\n".join(lines)

    def _entry(self, name: str) -> PackageEntry | None:
        if self._index is None:
            return None
        return self._index.get(name)

    def _set_details(self, text: str) -> None:
        self.details_text = text
        try:
            self.query_one("#details", Static).update(text)
        except Exception:
            pass

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        node = event.node.data
        if node is None:
            return
        if isinstance(node, str):
            self._load_tree(node)
        elif hasattr(node, "name") and hasattr(node, "children"):
            self._set_details(self._format_node(node))

    # ---------------------------------------------------------------- filtering

    def action_focus_filter(self) -> None:
        """Focus the live filter (package list) or search the open tree."""
        if not self._main_started:
            return
        if self._root_package:
            self.push_screen(SearchScreen(), self._on_search_done)
            return
        try:
            filter_input = self.query_one("#filter_input", Input)
            filter_input.add_class("visible")
            filter_input.focus()
        except Exception:
            pass

    FILTER_DEBOUNCE = 0.12

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "filter_input":
            return
        self._filter = event.value.strip()
        if self._root_package:
            return
        # Redraw once the user pauses, so typing stays smooth on big workspaces.
        if self._filter_timer is not None:
            self._filter_timer.stop()
        self._filter_timer = self.set_timer(self.FILTER_DEBOUNCE, self._load_main_view)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "filter_input":
            return
        self._focus_tree()

    # ------------------------------------------------------------------ actions

    def action_back(self) -> None:
        """Step back: clear the filter, or return to the package list."""
        if not self._main_started:
            return
        focused = self.focused
        if focused is not None and getattr(focused, "id", None) == "filter_input":
            self._focus_tree(force=True)
            return
        if self._filter and not self._root_package:
            self._filter = ""
            try:
                self.query_one("#filter_input", Input).value = ""
            except Exception:
                pass
            self._load_main_view()
            return
        if not self._root_package:
            return
        self._root_package = None
        self._root_node = None
        self._reverse_view = False
        self._load_main_view()

    def action_refresh(self) -> None:
        if not self._main_started:
            return
        if self._root_package:
            self._load_tree(self._root_package)
            return
        self._packages_cache = None
        self._packages_loading = False
        self._index = None
        self._start_package_scan()
        self._load_main_view()

    def action_expand_all(self) -> None:
        tree = self.query_one("#dep_tree", Tree)
        if self._root_node is not None:
            # expand_all() only reveals rows that exist, so fill the tree first.
            _populate_textual_tree(tree.root, self._root_node)
            tree.root._rostree_filled = True  # type: ignore[attr-defined]
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

    def action_toggle_scope(self) -> None:
        """Switch between runtime-only and all declared dependencies."""
        if not self._main_started:
            return
        self._runtime_only = not self._runtime_only
        scope = "runtime only" if self._runtime_only else "all dependencies"
        self.notify(f"Following {scope}", severity="information", timeout=2)
        if self._root_package:
            self._load_tree(self._root_package)
        else:
            self._load_main_view()

    def action_toggle_reverse(self) -> None:
        """Show which packages depend on the current one."""
        if not self._main_started or self._index is None:
            return
        target = self._root_package
        if target is None:
            node = self.query_one("#dep_tree", Tree).cursor_node
            data = node.data if node is not None else None
            target = data if isinstance(data, str) else None
        if target is None:
            self.notify("Select a package first", severity="information", timeout=2)
            return
        self._reverse_view = True
        self._set_status(f"[dim]Finding dependents of {target}…[/]")
        self.run_worker(lambda: self._reverse_worker(target), thread=True, exclusive=False)

    def _reverse_worker(self, target: str) -> None:
        index = self._index
        if index is None:
            return
        tags = ("depend", "exec_depend") if self._runtime_only else None
        try:
            reverse = index.reverse_dependencies(include_tags=tags)
        except Exception as exc:  # pragma: no cover - defensive
            self.call_from_thread(self._on_tree_failed, target, str(exc))
            return
        self.call_from_thread(self._show_reverse, target, sorted(reverse.get(target, ())))

    def _show_reverse(self, target: str, dependents: list[str]) -> None:
        tree = self.query_one("#dep_tree", Tree)
        self._clear_tree(tree)
        tree.root.label = f"[{COLOR_HEADER}]Packages depending on {target}[/]"
        tree.root.data = None
        for name in dependents:
            entry = self._entry(name)
            colour = _SOURCE_COLOR.get(entry.kind, COLOR_PKG) if entry else COLOR_PKG
            leaf = tree.root.add_leaf(f"[{colour}]{name}[/]")
            leaf.data = name
        if not dependents:
            tree.root.add_leaf("[dim]Nothing in this environment depends on it.[/]")
        tree.root.expand()
        self._set_status(
            f"[bold]{target}[/]  ·  [cyan]{len(dependents)}[/] direct dependent(s)  ·  "
            f"[dim]Esc to go back[/]"
        )
        self._set_details(
            f"[{COLOR_HEADER}]Reverse dependencies[/]\n\n"
            f"  [{COLOR_PKG}]{target}[/] is used by [{COLOR_STATS}]{len(dependents)}[/] "
            "package(s) in this environment.\n\n"
            "[dim]Enter[/] opens a dependent's own tree."
        )
        self._focus_tree()

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

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def _on_search_done(self, query: str | None) -> None:
        if not query:
            return
        self._search_query = query.lower()
        self._search_matches = []
        self._search_index = 0

        tree = self.query_one("#dep_tree", Tree)
        if self._root_node is not None:
            # Search the resolved tree, not just the rows currently on screen.
            _populate_textual_tree(tree.root, self._root_node)
            tree.root._rostree_filled = True  # type: ignore[attr-defined]
        self._collect_matches(tree.root, self._search_query)

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
        self._expand_ancestors(match_node)

        tree = self.query_one("#dep_tree", Tree)
        tree.select_node(match_node)
        tree.scroll_to_node(match_node)

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
            details.set_class(not self._details_visible, "hidden")
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
