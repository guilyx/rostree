"""Command-line interface for rostree: scan workspaces, list packages, show dependency trees."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.text import Text

from rostree.core.filters import (
    DEP_TYPE_CHOICES,
    FilterReport,
    PackageFilter,
    tags_for_dep_type,
)
from rostree.core.finder import (
    get_index,
    list_package_paths,
    list_packages_by_source,
    scan_for_workspaces,
)
from rostree.core.graph import GraphView, mermaid_id, to_dot, to_mermaid
from rostree.core.index import PackageIndex, SourceKind
from rostree.core.tree import (
    DependencyGraph,
    DependencyNode,
    NodeStatus,
    build_dependency_graph,
    build_dependency_tree,
    tree_stats,
)

# Historical status markers, still recognised on nodes built by older callers.
_LEGACY_MARKERS = {
    "(cycle)": NodeStatus.CYCLE,
    "(not found)": NodeStatus.MISSING,
    "(parse error)": NodeStatus.PARSE_ERROR,
    "(see above)": NodeStatus.REPEAT,
    "(depth limit)": NodeStatus.TRUNCATED,
}

_STATUS_LABEL = {
    NodeStatus.REPEAT: ("↩", "see above", "dim"),
    NodeStatus.CYCLE: ("⟳", "cycle", "yellow"),
    NodeStatus.MISSING: ("✗", "not found", "red"),
    NodeStatus.PARSE_ERROR: ("!", "parse error", "red"),
    NodeStatus.TRUNCATED: ("…", "depth limit", "dim"),
}

# Published from here since v0.1; the implementation now lives in core.graph.
_mermaid_id = mermaid_id

_SOURCE_STYLE = {
    SourceKind.SYSTEM: "dim",
    SourceKind.WORKSPACE: "green",
    SourceKind.OTHER: "cyan",
    SourceKind.SOURCE: "yellow",
    SourceKind.ADDED: "magenta",
}

# Graphs of a whole workspace are linear to build now, but Graphviz still has to
# lay them out, so warn rather than silently truncating.
GRAPH_DEFAULT_DEPTH = 4
GRAPH_MAX_PACKAGES = 400

_out = Console(highlight=False, soft_wrap=True)
_err = Console(stderr=True, highlight=False, soft_wrap=True)


def _configure_console(args: argparse.Namespace) -> None:
    """Honour --no-color (and NO_COLOR, which rich already respects)."""
    global _out, _err
    if getattr(args, "no_color", False):
        _out = Console(highlight=False, soft_wrap=True, no_color=True, force_terminal=False)
        _err = Console(
            stderr=True, highlight=False, soft_wrap=True, no_color=True, force_terminal=False
        )


def _status_of(node: DependencyNode) -> NodeStatus:
    """Node status, falling back to the legacy description markers."""
    if node.status is not NodeStatus.OK:
        return node.status
    return _LEGACY_MARKERS.get(node.description, NodeStatus.OK)


def _node_label(node: DependencyNode, *, show_desc: bool) -> Text:
    """One rendered tree line: name, version, status marker, optional description."""
    status = _status_of(node)
    label = Text()
    style = "bold" if status is NodeStatus.OK else "default"
    label.append(node.name, style=style)
    if node.version:
        label.append(f" {node.version}", style="cyan")
    if status is NodeStatus.TRUNCATED:
        hidden = node.hidden_children
        label.append(f"  … {hidden} more" if hidden else "  … depth limit", style="dim")
    elif status is not NodeStatus.OK:
        glyph, text, colour = _STATUS_LABEL[status]
        label.append(f"  {glyph} {text}", style=colour)
    elif show_desc and node.description:
        desc = node.description
        if len(desc) > 70:
            desc = desc[:69] + "…"
        label.append(f"  {desc}", style="dim")
    return label


#: How many back-reference names to spell out before summarising the rest.
#: Kept small because these lines sit at the deepest indentation in the tree.
_REPEAT_PREVIEW = 4


def _repeat_summary(repeats: list[DependencyNode]) -> Text:
    """One line standing in for several dependencies already shown further up."""
    names = [n.name for n in repeats]
    shown = names[:_REPEAT_PREVIEW]
    line = Text("↩ ", style="dim")
    line.append(f"{len(names)} already shown above: ", style="dim")
    line.append(", ".join(shown), style="dim")
    if len(names) > len(shown):
        line.append(f", and {len(names) - len(shown)} more", style="dim")
    return line


def _print_tree_text(
    node: DependencyNode,
    indent: int = 0,
    prefix: str = "",
    *,
    show_desc: bool = False,
    expand_repeats: bool = False,
    _is_root: bool = True,
) -> None:
    """Print a dependency tree using box-drawing characters."""
    if _is_root:
        # The package you asked about always gets its description.
        _out.print(_node_label(node, show_desc=True))

    children = list(node.children)
    grouped: list[DependencyNode] = []
    if not expand_repeats:
        # Most lines of a real ROS tree are back-references to a package already
        # printed further up. Collapsing sibling back-references onto one line
        # keeps the novel structure visible instead of burying it.
        repeats = [c for c in children if _status_of(c) is NodeStatus.REPEAT]
        if len(repeats) > 1:
            grouped = repeats
            children = [c for c in children if _status_of(c) is not NodeStatus.REPEAT]

    for i, child in enumerate(children):
        last = i == len(children) - 1 and not grouped
        connector = "└── " if last else "├── "
        line = Text(prefix + connector, style="dim")
        line.append_text(_node_label(child, show_desc=show_desc))
        _out.print(line)
        if child.children:
            _print_tree_text(
                child,
                indent + 1,
                prefix + ("    " if last else "│   "),
                show_desc=show_desc,
                expand_repeats=expand_repeats,
                _is_root=False,
            )

    if grouped:
        line = Text(prefix + "└── ", style="dim")
        line.append_text(_repeat_summary(grouped))
        _out.print(line)


def _summary_line(stats: dict[str, int]) -> str:
    parts = [
        f"{stats['packages']} package(s)",
        f"depth {stats['depth']}",
        f"{stats['nodes']} line(s)",
    ]
    if stats["repeats"]:
        parts.append(f"{stats['repeats']} repeat(s) collapsed")
    if stats["cycles"]:
        parts.append(f"{stats['cycles']} cycle(s)")
    if stats["missing"]:
        parts.append(f"{stats['missing']} unresolved")
    return "  ·  ".join(parts)


def _extra_roots(args: argparse.Namespace) -> list[Path] | None:
    source = getattr(args, "source", None)
    return [Path(p) for p in source] if source else None


def _load_index(
    args: argparse.Namespace,
    *,
    message: str = "Scanning packages",
    roots: list[Path] | None = None,
) -> PackageIndex:
    """Build the package index once, with a spinner when attached to a terminal."""
    if roots is None:
        roots = _extra_roots(args)
    if _err.is_terminal and not getattr(args, "json", False):
        with _err.status(f"[dim]{message}…[/]", spinner="dots"):
            return get_index(extra_source_roots=roots)
    return get_index(extra_source_roots=roots)


def cmd_scan(args: argparse.Namespace) -> int:
    """Scan for ROS 2 workspaces on the host."""
    roots = [Path(p) for p in args.paths] if args.paths else None
    workspaces = scan_for_workspaces(
        roots=roots,
        max_depth=args.depth,
        include_home=not args.no_home,
        include_opt_ros=not args.no_system,
    )

    if getattr(args, "json", False):
        print(json.dumps([ws.to_dict() for ws in workspaces], indent=2))
    else:
        if not workspaces:
            print("No ROS 2 workspaces found.")
            return 0
        print(f"Found {len(workspaces)} workspace(s):\n")
        for ws in workspaces:
            status = []
            if ws.has_src:
                status.append("src")
            if ws.has_install:
                status.append("install")
            if ws.has_build:
                status.append("build")
            status_str = ", ".join(status) if status else "empty"
            print(f"  {ws.path}")
            print(f"    Status: {status_str}")
            print(f"    Packages: {len(ws.packages)}")
            if getattr(args, "verbose", False) and ws.packages:
                for pkg in ws.packages[:20]:
                    print(f"      - {pkg}")
                if len(ws.packages) > 20:
                    print(f"      ... and {len(ws.packages) - 20} more")
            print()
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List known ROS 2 packages."""
    extra_roots = _extra_roots(args)
    pattern = getattr(args, "filter", None)

    def matches(name: str) -> bool:
        return pattern is None or pattern.lower() in name.lower()

    if getattr(args, "by_source", False):
        by_source = list_packages_by_source(extra_source_roots=extra_roots)
        by_source = {
            label: [n for n in names if matches(n)]
            for label, names in by_source.items()
            if any(matches(n) for n in names)
        }
        if getattr(args, "json", False):
            print(json.dumps(by_source, indent=2))
        else:
            if not by_source:
                print("No packages found. Is your ROS 2 environment sourced?")
                return 1
            total = sum(len(pkgs) for pkgs in by_source.values())
            print(f"Found {total} package(s) from {len(by_source)} source(s):\n")
            for source, packages in by_source.items():
                print(f"  {source} ({len(packages)})")
                if getattr(args, "verbose", False):
                    for pkg in packages[:50]:
                        print(f"    - {pkg}")
                    if len(packages) > 50:
                        print(f"    ... and {len(packages) - 50} more")
                print()
    else:
        packages = list_package_paths(extra_source_roots=extra_roots)
        packages = {name: path for name, path in packages.items() if matches(name)}
        if getattr(args, "json", False):
            print(json.dumps({name: str(path) for name, path in packages.items()}, indent=2))
        else:
            if not packages:
                print("No packages found. Is your ROS 2 environment sourced?")
                return 1
            print(f"Found {len(packages)} package(s):\n")
            for name in sorted(packages.keys()):
                if getattr(args, "verbose", False):
                    print(f"  {name}: {packages[name]}")
                else:
                    print(f"  {name}")
    return 0


def cmd_tree(args: argparse.Namespace) -> int:
    """Show dependency tree for a package."""
    index = _load_index(args)
    if index.get(args.package) is None:
        _err.print(f"[red]Package not found:[/] {args.package}")
        _suggest(args.package, index)
        return 1

    full = getattr(args, "full", False)
    report = FilterReport()
    tree = build_dependency_tree(
        args.package,
        max_depth=getattr(args, "depth", None),
        include_tags=_dep_tags(args),
        collapse_repeats=not full,
        index=index,
        package_filter=_package_filter(args),
        report=report,
        max_nodes=getattr(args, "max_nodes", None),
    )

    if tree is None:
        _err.print(f"[red]Package not found:[/] {args.package}")
        return 1

    if getattr(args, "json", False):
        print(json.dumps(tree.to_dict(), indent=2))
        return 0

    _print_tree_text(
        tree,
        show_desc=getattr(args, "verbose", False),
        expand_repeats=getattr(args, "expand_repeats", False) or full,
    )
    stats = tree_stats(tree)
    _err.print(f"\n[dim]{_summary_line(stats)}[/]")
    _report_filtered(report)
    if stats["repeats"] and not full:
        _err.print(
            "[dim]Packages already shown above are summarised; "
            "--expand-repeats lists them, --full re-expands their subtrees.[/]"
        )
    return 0


def _suggest(name: str, index: PackageIndex, limit: int = 5) -> None:
    """Print near-miss package names to soften a typo."""
    import difflib

    names = index.names()
    close = difflib.get_close_matches(name, names, n=limit, cutoff=0.6)
    if not close:
        close = [n for n in names if name.lower() in n.lower()][:limit]
    if close:
        _err.print("[dim]Did you mean:[/] " + ", ".join(close))
    elif not names:
        _err.print("[dim]No packages are visible. Source your ROS 2 setup.bash first.[/]")


def cmd_why(args: argparse.Namespace) -> int:
    """Explain how one package ends up depending on another."""
    index = _load_index(args)
    # Only the starting package has to exist. The dependency may legitimately be
    # an unresolved name (a rosdep key, or something not built yet) that still
    # shows up as an edge in the graph.
    if index.get(args.package) is None:
        _err.print(f"[red]Package not found:[/] {args.package}")
        _suggest(args.package, index)
        return 1
    if args.package == args.dependency:
        _err.print(f"[yellow]{args.package} is its own starting point.[/]")
        return 1

    report = FilterReport()
    graph = build_dependency_graph(
        args.package,
        max_depth=args.depth,
        include_tags=_dep_tags(args),
        index=index,
        package_filter=_package_filter(args),
        report=report,
    )
    paths = _shortest_paths(graph, args.package, args.dependency, limit=args.limit)

    if not paths:
        if args.json:
            print(json.dumps({"from": args.package, "to": args.dependency, "paths": []}))
        else:
            _out.print(
                f"[yellow]{args.package}[/] does not depend on [yellow]{args.dependency}[/]"
                + (" (runtime dependencies only)" if _dep_tags(args) else "")
            )
            _report_filtered(report)
        return 1

    if args.json:
        print(json.dumps({"from": args.package, "to": args.dependency, "paths": paths}, indent=2))
        return 0

    _out.print(
        f"[bold]{args.package}[/] depends on [bold]{args.dependency}[/] "
        f"via {len(paths)} shortest path(s) of length {len(paths[0]) - 1}:\n"
    )
    for path in paths:
        line = Text("  ")
        for i, name in enumerate(path):
            if i:
                line.append(" → ", style="dim")
            line.append(name, style="bold" if i in (0, len(path) - 1) else "default")
        _out.print(line)
    return 0


def _shortest_paths(
    graph: DependencyGraph,
    start: str,
    target: str,
    *,
    limit: int = 10,
) -> list[list[str]]:
    """All shortest dependency paths from start to target (breadth-first)."""
    if start == target:
        return [[start]]
    from collections import deque

    parents: dict[str, set[str]] = {}
    depth: dict[str, int] = {start: 0}
    queue: deque[str] = deque([start])
    found_depth: int | None = None

    while queue:
        node = queue.popleft()
        if found_depth is not None and depth[node] >= found_depth:
            continue
        for dep in graph.edges.get(node, ()):
            if dep not in depth:
                depth[dep] = depth[node] + 1
                parents.setdefault(dep, set()).add(node)
                if dep == target:
                    found_depth = depth[dep]
                else:
                    queue.append(dep)
            elif depth[dep] == depth[node] + 1:
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


def cmd_rdeps(args: argparse.Namespace) -> int:
    """List packages that depend on the given package."""
    index = _load_index(args, message="Indexing reverse dependencies")
    if index.get(args.package) is None:
        _err.print(f"[red]Package not found:[/] {args.package}")
        _suggest(args.package, index)
        return 1

    tags = _dep_tags(args)
    if _err.is_terminal and not args.json:
        with _err.status("[dim]Reading manifests…[/]", spinner="dots"):
            reverse = index.reverse_dependencies(include_tags=tags)
    else:
        reverse = index.reverse_dependencies(include_tags=tags)

    direct = sorted(reverse.get(args.package, ()))
    if args.transitive:
        seen: set[str] = set()
        frontier = list(direct)
        while frontier:
            name = frontier.pop()
            if name in seen:
                continue
            seen.add(name)
            frontier.extend(reverse.get(name, ()))
        names = sorted(seen)
    else:
        names = direct

    package_filter = _package_filter(args)
    if not package_filter.is_noop:
        report = FilterReport()
        names = package_filter.filter_names(names, index, report)

    if args.json:
        print(json.dumps({"package": args.package, "dependents": names}, indent=2))
        return 0

    if not names:
        _out.print(f"Nothing depends on [bold]{args.package}[/] in this environment.")
        return 0

    scope = "transitively" if args.transitive else "directly"
    _out.print(f"[bold]{len(names)}[/] package(s) depend {scope} on [bold]{args.package}[/]:\n")
    for name in names:
        entry = index.get(name)
        style = _SOURCE_STYLE.get(entry.kind, "default") if entry else "default"
        line = Text("  ")
        line.append(name, style=style)
        if entry and args.verbose:
            line.append(f"  {entry.kind.value}", style="dim")
        _out.print(line)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Report dependency cycles and unresolved dependencies. Non-zero exit on problems."""
    index = _load_index(args)
    if args.packages:
        roots = list(args.packages)
        unknown = [n for n in roots if index.get(n) is None]
        if unknown:
            _err.print("[red]Unknown package(s):[/] " + ", ".join(unknown))
            return 2
    else:
        roots = index.workspace_names()
        roots = _package_filter(args).filter_names(roots, index)
        if not roots:
            _err.print(
                "[yellow]No workspace packages found.[/] Source a workspace, or name packages explicitly."
            )
            return 2

    graph = build_dependency_graph(
        roots,
        include_tags=_dep_tags(args),
        index=index,
        package_filter=_package_filter(args),
    )
    cycles = graph.cycles()
    missing = sorted(graph.missing)
    if args.ignore_system:
        missing = [m for m in missing if "_" in m]

    junit = getattr(args, "junit", None)
    if junit:
        _write_junit(Path(junit), roots, cycles, missing)
        _err.print(f"[dim]JUnit report written to {junit}[/]")

    if args.json:
        print(
            json.dumps(
                {
                    "roots": roots,
                    "packages": len(graph.packages),
                    "cycles": cycles,
                    "unresolved": missing,
                },
                indent=2,
            )
        )
        return 1 if (cycles or missing) else 0

    _out.print(f"Checked [bold]{len(graph.packages)}[/] package(s) from {len(roots)} root(s).\n")
    if cycles:
        _out.print(f"[red]✗ {len(cycles)} dependency cycle(s):[/]")
        for cycle in cycles:
            _out.print("    " + " → ".join(cycle))
        _out.print("")
    else:
        _out.print("[green]✓[/] No dependency cycles.")

    if missing:
        _out.print(f"[yellow]! {len(missing)} unresolved dependency name(s):[/]")
        for name in missing[:40]:
            _out.print(f"    {name}", style="dim")
        if len(missing) > 40:
            _out.print(f"    … and {len(missing) - 40} more", style="dim")
        _out.print(
            "[dim]  Unresolved names are usually rosdep keys or packages that are not built yet.[/]"
        )
    else:
        _out.print("[green]✓[/] Every dependency resolves to a package.")

    return 1 if (cycles or missing) else 0


def _dependency_set(
    package: str,
    args: argparse.Namespace,
    index: PackageIndex,
) -> dict[str, str]:
    """Every package reachable from ``package``, mapped to its version."""
    graph = build_dependency_graph(
        package,
        max_depth=getattr(args, "depth", None),
        include_tags=_dep_tags(args),
        index=index,
        package_filter=_package_filter(args),
    )
    versions = {name: info.version for name, info in graph.packages.items()}
    for name in graph.missing:
        versions[name] = ""
    versions.pop(package, None)
    return versions


def _snapshot(package: str, versions: dict[str, str]) -> dict:
    return {"package": package, "dependencies": versions}


def cmd_diff(args: argparse.Namespace) -> int:
    """Compare two dependency sets and report what moved."""
    index = _load_index(args)

    if args.save:
        if index.get(args.package) is None:
            _err.print(f"[red]Package not found:[/] {args.package}")
            _suggest(args.package, index)
            return 1
        versions = _dependency_set(args.package, args, index)
        Path(args.save).write_text(json.dumps(_snapshot(args.package, versions), indent=2))
        _err.print(f"[dim]Wrote a snapshot of {len(versions)} dependencies to {args.save}[/]")
        return 0

    if args.against:
        try:
            stored = json.loads(Path(args.against).read_text())
            before_name = stored["package"]
            before = dict(stored["dependencies"])
        except (OSError, ValueError, KeyError) as exc:
            _err.print(f"[red]Could not read snapshot {args.against}:[/] {exc}")
            return 2
    elif args.other:
        if index.get(args.other) is None:
            _err.print(f"[red]Package not found:[/] {args.other}")
            _suggest(args.other, index)
            return 1
        before_name = args.other
        before = _dependency_set(args.other, args, index)
    else:
        _err.print(
            "[red]Nothing to compare against.[/] Pass a second package, --against or --save."
        )
        return 2

    if index.get(args.package) is None:
        _err.print(f"[red]Package not found:[/] {args.package}")
        _suggest(args.package, index)
        return 1
    after = _dependency_set(args.package, args, index)

    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(
        name
        for name in set(before) & set(after)
        if before[name] != after[name] and before[name] and after[name]
    )

    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "before": before_name,
                    "after": args.package,
                    "added": added,
                    "removed": removed,
                    "changed": {n: {"from": before[n], "to": after[n]} for n in changed},
                },
                indent=2,
            )
        )
        return 1 if (added or removed or changed) else 0

    _out.print(
        f"Comparing [bold]{before_name}[/] ({len(before)} deps) → "
        f"[bold]{args.package}[/] ({len(after)} deps)\n"
    )
    if not (added or removed or changed):
        _out.print("[green]✓[/] No difference.")
        return 0

    for title, names, style, sign in (
        ("Added", added, "green", "+"),
        ("Removed", removed, "red", "-"),
    ):
        if names:
            _out.print(f"[{style}]{title} ({len(names)})[/]")
            for name in names:
                line = Text(f"  {sign} ", style=style)
                line.append(name)
                version = after.get(name) or before.get(name)
                if version:
                    line.append(f" {version}", style="cyan")
                _out.print(line)
            _out.print("")

    if changed:
        _out.print(f"[yellow]Changed ({len(changed)})[/]")
        for name in changed:
            line = Text("  ~ ", style="yellow")
            line.append(name)
            line.append(f"  {before[name]} → {after[name]}", style="cyan")
            _out.print(line)
    return 1


def _write_junit(path: Path, roots: list[str], cycles: list[list[str]], missing: list[str]) -> None:
    """Emit a JUnit report so CI dashboards can show what `check` found."""
    from xml.etree.ElementTree import Element, ElementTree, SubElement

    suite = Element(
        "testsuite",
        name="rostree check",
        tests=str(2),
        failures=str(bool(cycles) + bool(missing)),
    )
    cycle_case = SubElement(suite, "testcase", classname="rostree", name="no dependency cycles")
    if cycles:
        failure = SubElement(
            cycle_case,
            "failure",
            message=f"{len(cycles)} dependency cycle(s)",
            type="DependencyCycle",
        )
        failure.text = "\n".join(" -> ".join(cycle) for cycle in cycles)

    missing_case = SubElement(
        suite, "testcase", classname="rostree", name="all dependencies resolve"
    )
    if missing:
        failure = SubElement(
            missing_case,
            "failure",
            message=f"{len(missing)} unresolved dependency name(s)",
            type="UnresolvedDependency",
        )
        failure.text = "\n".join(missing)

    suite.set("hostname", "")
    suite.set("package", ",".join(roots[:20]))
    path.parent.mkdir(parents=True, exist_ok=True)
    ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def cmd_tui(args: argparse.Namespace) -> int:
    """Launch the interactive TUI."""
    from rostree.tui.app import DepTreeApp

    app = DepTreeApp(
        root_package=getattr(args, "package", None),
        runtime_only=not getattr(args, "all_deps", False),
    )
    app.run()
    return 0


def _collect_edges(
    node: DependencyNode,
    edges: set[tuple[str, str]],
    visited: set[str] | None = None,
    *,
    include_missing: bool = False,
) -> None:
    """Recursively collect all edges (parent -> child) from a dependency tree."""
    if visited is None:
        visited = set()
    if node.name in visited:
        return
    visited.add(node.name)
    for child in node.children:
        status = _status_of(child)
        if status is NodeStatus.MISSING and not include_missing:
            continue
        if status in (NodeStatus.CYCLE, NodeStatus.PARSE_ERROR):
            continue
        edges.add((node.name, child.name))
        _collect_edges(child, edges, visited, include_missing=include_missing)


def _collect_edges_multi(
    trees: list[DependencyNode],
    root_names: set[str],
) -> tuple[set[tuple[str, str]], set[str]]:
    """Collect edges from multiple trees, tracking which nodes are roots."""
    edges: set[tuple[str, str]] = set()
    all_nodes: set[str] = set(root_names)
    for tree in trees:
        _collect_edges(tree, edges)
        all_nodes.add(tree.name)
    for parent, child in edges:
        all_nodes.add(parent)
        all_nodes.add(child)
    return edges, all_nodes


def _generate_dot(
    roots: list[DependencyNode],
    title: str | None = None,
    highlight_roots: bool = True,
) -> str:
    """Generate DOT (Graphviz) format from dependency trees."""
    return to_dot(GraphView.from_trees(roots, title=title), highlight_roots=highlight_roots)


def _generate_mermaid(
    roots: list[DependencyNode],
    title: str | None = None,
    highlight_roots: bool = True,
) -> str:
    """Generate Mermaid format from dependency trees."""
    return to_mermaid(GraphView.from_trees(roots, title=title), highlight_roots=highlight_roots)


def _get_workspace_packages(workspace_path: Path | None = None) -> list[str]:
    """Get packages from a workspace. If None, use current environment."""
    if workspace_path:
        ws_path = Path(workspace_path).resolve()
        src_path = ws_path / "src" if (ws_path / "src").exists() else ws_path
        if not src_path.exists():
            return []
        from rostree.core.finder import _list_packages_in_src

        return _list_packages_in_src(src_path)
    by_source = list_packages_by_source()
    packages = []
    for label, names in by_source.items():
        # Only include Workspace and Source packages, not System
        if "System" not in label:
            packages.extend(names)
    return packages


def _check_graphviz() -> bool:
    """Check if Graphviz (dot) is available."""
    return shutil.which("dot") is not None


def _check_matplotlib() -> bool:
    """Check if matplotlib and networkx are available."""
    try:
        import matplotlib  # noqa: F401
        import networkx  # noqa: F401

        return True
    except ImportError:
        return False


def _render_with_matplotlib(
    edges: set[tuple[str, str]],
    root_names: set[str],
    output_path: Path,
    format: str,
    title: str | None = None,
) -> bool:
    """Render graph using matplotlib and networkx (pure Python, no system deps)."""
    try:
        import matplotlib.pyplot as plt
        import networkx as nx
    except ImportError:
        print(
            "Error: matplotlib/networkx not installed. Install with:\n"
            "  pip install rostree[viz]\n"
            "  # or: pip install matplotlib networkx",
            file=sys.stderr,
        )
        return False

    try:
        G = nx.DiGraph()
        G.add_edges_from(edges)
        for root in root_names:
            if root not in G:
                G.add_node(root)

        if len(G.nodes()) == 0:
            print("Error: Graph is empty", file=sys.stderr)
            return False

        fig_width = max(12, len(G.nodes()) * 0.5)
        fig_height = max(8, len(G.nodes()) * 0.3)
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))

        try:
            pos = nx.nx_agraph.graphviz_layout(G, prog="dot", args="-Grankdir=LR")
        except Exception:
            try:
                pos = nx.spring_layout(G, k=2, iterations=50, seed=42)
            except Exception:
                pos = nx.shell_layout(G)

        node_colors = ["lightblue" if n in root_names else "lightgray" for n in G.nodes()]
        nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=2000, alpha=0.9, ax=ax)
        nx.draw_networkx_labels(G, pos, font_size=8, font_weight="bold", ax=ax)
        nx.draw_networkx_edges(
            G, pos, edge_color="gray", arrows=True, arrowsize=15, alpha=0.7, ax=ax
        )

        if title:
            ax.set_title(title, fontsize=14, fontweight="bold")

        ax.axis("off")
        plt.tight_layout()
        plt.savefig(output_path, format=format, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return True

    except Exception as e:
        print(f"Error rendering with matplotlib: {e}", file=sys.stderr)
        return False


def _render_dot(dot_content: str, output_path: Path, format: str) -> bool:
    """Render DOT content to an image file using Graphviz."""
    if not _check_graphviz():
        print(
            "Error: Graphviz not found. Install it with:\n"
            "  Ubuntu/Debian: sudo apt install graphviz\n"
            "  macOS: brew install graphviz\n"
            "  Or download from: https://graphviz.org/download/",
            file=sys.stderr,
        )
        return False

    try:
        result = subprocess.run(
            [_resolve_tool("dot"), f"-T{format}", "-o", str(output_path)],
            input=dot_content,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"Graphviz error: {result.stderr}", file=sys.stderr)
            return False
        return True
    except subprocess.TimeoutExpired:
        print("Error: Graphviz timed out (graph may be too large)", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error running Graphviz: {e}", file=sys.stderr)
        return False


def _resolve_tool(name: str) -> str:
    """Absolute path to an external tool, so we never hand a bare name to exec."""
    return shutil.which(name) or name


def _open_file(path: Path) -> bool:
    """Open a file with the system default application."""
    system = platform.system()
    try:
        if system == "Windows":
            # os.startfile is the documented way to do this on Windows and takes
            # no shell, so a path with shell metacharacters cannot be misread.
            os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
        elif system == "Darwin":  # macOS
            subprocess.run([_resolve_tool("open"), str(path)], check=True)
        else:  # Linux and others
            subprocess.run([_resolve_tool("xdg-open"), str(path)], check=True)
        return True
    except Exception as e:
        print(f"Could not open file: {e}", file=sys.stderr)
        return False


def cmd_graph(args: argparse.Namespace) -> int:
    """Generate a dependency graph in DOT or Mermaid format."""
    extra_roots = _extra_roots(args) or []
    workspace = getattr(args, "workspace", None)
    if workspace:
        # -w names a workspace that may not be sourced at all, so make its packages
        # resolvable instead of drawing a graph of names that resolve to nothing.
        ws_path = Path(workspace).expanduser().resolve()
        src = ws_path / "src" if (ws_path / "src").is_dir() else ws_path
        if src.is_dir():
            extra_roots = [*extra_roots, src]
    index = _load_index(args, roots=extra_roots or None)

    packages_to_graph: list[str] = []
    if args.package:
        packages_to_graph = [args.package]
        if index.get(args.package) is None:
            _err.print(f"[red]Package not found:[/] {args.package}")
            _suggest(args.package, index)
            return 1
    elif getattr(args, "workspace", None):
        packages_to_graph = _get_workspace_packages(Path(args.workspace))
        if not packages_to_graph:
            print(f"No packages found in workspace: {args.workspace}", file=sys.stderr)
            return 1
    else:
        packages_to_graph = _get_workspace_packages(None)
        if not packages_to_graph:
            print(
                "No workspace packages found. Specify a package or use --workspace.",
                file=sys.stderr,
            )
            return 1

    if len(packages_to_graph) > GRAPH_MAX_PACKAGES and not args.package:
        print(
            f"Warning: Limiting to first {GRAPH_MAX_PACKAGES} root packages "
            f"(found {len(packages_to_graph)}). Use -d to limit depth.",
            file=sys.stderr,
        )
        packages_to_graph = packages_to_graph[:GRAPH_MAX_PACKAGES]

    if getattr(args, "depth", None) is not None:
        depth = args.depth
    elif args.package:
        depth = None  # Unlimited for a single package
    else:
        depth = GRAPH_DEFAULT_DEPTH  # Limited for workspace-wide

    # One breadth-first pass over the whole DAG, rather than one tree per package.
    if _err.is_terminal:
        with _err.status("[dim]Resolving dependencies…[/]", spinner="dots"):
            graph = build_dependency_graph(
                packages_to_graph,
                max_depth=depth,
                include_tags=_dep_tags(args),
                extra_source_roots=extra_roots,
                index=index,
                package_filter=_package_filter(args),
            )
    else:
        graph = build_dependency_graph(
            packages_to_graph,
            max_depth=depth,
            include_tags=_dep_tags(args),
            extra_source_roots=extra_roots,
            index=index,
            package_filter=_package_filter(args),
        )

    if not graph.edges:
        print("No valid package trees found.", file=sys.stderr)
        return 1

    if getattr(args, "no_title", False):
        title = None
    elif args.package:
        title = f"{args.package} dependencies"
    elif getattr(args, "workspace", None):
        title = f"Workspace: {Path(args.workspace).name}"
    else:
        title = "Workspace dependencies"

    show_missing = not getattr(args, "hide_missing", False)
    view = GraphView.from_graph(graph, title=title, show_missing=show_missing)
    if graph.missing and show_missing:
        _err.print(
            f"[dim]{len(graph.missing)} dependency name(s) did not resolve; "
            "drawn dashed. Use --hide-missing to omit them.[/]"
        )

    output = to_mermaid(view) if getattr(args, "format", "dot") == "mermaid" else to_dot(view)

    render_format = getattr(args, "render", None)
    if render_format:
        if getattr(args, "format", "dot") == "mermaid":
            print(
                "Error: --render only works with DOT format (not mermaid). "
                "Remove -f mermaid or use mermaid.live for rendering.",
                file=sys.stderr,
            )
            return 1

        if getattr(args, "output", None):
            out_path = Path(args.output)
            if out_path.suffix.lower() not in (f".{render_format}", ".dot"):
                out_path = out_path.with_suffix(f".{render_format}")
        else:
            if args.package:
                base_name = args.package.replace("/", "_")
            elif getattr(args, "workspace", None):
                base_name = Path(args.workspace).name
            else:
                base_name = "workspace_deps"
            out_path = Path(f"{base_name}.{render_format}")

        print(
            f"Rendering {len(view.nodes)} nodes / {len(view.edges)} edges to {out_path}...",
            file=sys.stderr,
        )

        rendered = False
        if _check_graphviz():
            rendered = _render_dot(output, out_path, render_format)
        elif _check_matplotlib():
            print("Graphviz not found, using matplotlib...", file=sys.stderr)
            rendered = _render_with_matplotlib(
                view.edges, view.roots, out_path, render_format, title
            )
        else:
            print(
                "Error: No rendering backend available.\n"
                "Install one of:\n"
                "  1. Graphviz (system): sudo apt install graphviz\n"
                "  2. matplotlib (pip): pip install rostree[viz]",
                file=sys.stderr,
            )
            return 1

        if not rendered:
            return 1

        print(f"Graph image saved to: {out_path}", file=sys.stderr)
        if getattr(args, "open", False):
            _open_file(out_path)
        return 0

    if getattr(args, "output", None):
        Path(args.output).write_text(output)
        print(f"Graph written to: {args.output}", file=sys.stderr)
    else:
        print(output)

    return 0


def _add_global_args(parser: argparse.ArgumentParser) -> None:
    """Flags accepted both before and after the subcommand."""
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable coloured output (NO_COLOR is honoured too)",
    )


def _add_source_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-s",
        "--source",
        action="append",
        metavar="PATH",
        help="Additional source directories to scan (can be repeated)",
    )


def _add_runtime_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-r",
        "--runtime",
        action="store_true",
        help="Shorthand for --dep-type runtime (depend, exec_depend)",
    )
    parser.add_argument(
        "--dep-type",
        choices=DEP_TYPE_CHOICES,
        default=None,
        metavar="KIND",
        help="Which dependencies to follow: " + ", ".join(DEP_TYPE_CHOICES) + " (default: all)",
    )


def _add_filter_args(parser: argparse.ArgumentParser, *, short_workspace: bool = True) -> None:
    """Scope flags shared by every command that walks the dependency graph."""
    group = parser.add_argument_group("filtering")
    # `graph` already spends -w on --workspace, so the short form is optional.
    flags = ["-w", "--only-workspace"] if short_workspace else ["--only-workspace"]
    group.add_argument(
        *flags,
        "--workspace-only",
        dest="only_workspace",
        action="store_true",
        help="Ignore packages installed under /opt/ros",
    )
    group.add_argument(
        "--include",
        action="append",
        metavar="GLOB",
        help="Only packages whose name matches GLOB (repeatable, e.g. 'nav2_*')",
    )
    group.add_argument(
        "--exclude",
        action="append",
        metavar="GLOB",
        help="Drop packages whose name matches GLOB (repeatable)",
    )


def _package_filter(args: argparse.Namespace) -> PackageFilter:
    return PackageFilter.from_args(
        include=getattr(args, "include", None),
        exclude=getattr(args, "exclude", None),
        only_workspace=getattr(args, "only_workspace", False),
    )


def _dep_tags(args: argparse.Namespace) -> tuple[str, ...] | None:
    """Dependency tags to traverse, honouring --dep-type and the -r shorthand."""
    dep_type = getattr(args, "dep_type", None)
    if dep_type:
        return tags_for_dep_type(dep_type)
    if getattr(args, "runtime", False):
        return tags_for_dep_type("runtime")
    return None


def _report_filtered(report: FilterReport) -> None:
    """Say what a filter held back, so the output never quietly lies."""
    if report:
        _err.print(f"[dim]{report.summary()}[/]")


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the rostree CLI."""
    parser = argparse.ArgumentParser(
        prog="rostree",
        description="Explore ROS 2 package dependencies from the command line.",
    )
    from rostree import __version__

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_global_args(parser)

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # rostree scan
    scan_parser = subparsers.add_parser(
        "scan",
        help="Scan for ROS 2 workspaces on the host machine",
        description="Discover ROS 2 workspaces by scanning common locations or specified paths.",
    )
    scan_parser.add_argument(
        "paths",
        nargs="*",
        help="Directories to scan (default: common locations like ~/ros*_ws, /opt/ros/*)",
    )
    scan_parser.add_argument(
        "-d", "--depth", type=int, default=4, help="Maximum recursion depth (default: 4)"
    )
    scan_parser.add_argument(
        "--no-home", action="store_true", help="Don't scan home directory locations"
    )
    scan_parser.add_argument(
        "--no-system", action="store_true", help="Don't scan /opt/ros system installs"
    )
    scan_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show packages in each workspace"
    )
    scan_parser.add_argument("--json", action="store_true", help="Output as JSON")
    scan_parser.set_defaults(func=cmd_scan)

    # rostree list
    list_parser = subparsers.add_parser(
        "list",
        help="List known ROS 2 packages",
        description="List packages visible in the current ROS 2 environment.",
    )
    _add_source_arg(list_parser)
    list_parser.add_argument(
        "--by-source", action="store_true", help="Group packages by source (System, Workspace, ...)"
    )
    list_parser.add_argument(
        "-f", "--filter", metavar="TEXT", help="Only show packages whose name contains TEXT"
    )
    list_parser.add_argument("-v", "--verbose", action="store_true", help="Show package paths")
    list_parser.add_argument("--json", action="store_true", help="Output as JSON")
    list_parser.set_defaults(func=cmd_list)

    # rostree tree
    tree_parser = subparsers.add_parser(
        "tree",
        help="Show dependency tree for a package",
        description=(
            "Build and display the dependency tree for a ROS 2 package. "
            "A package that appears more than once is expanded where it first "
            "appears and marked '↩ see above' elsewhere; use --full to expand every "
            "occurrence."
        ),
    )
    tree_parser.add_argument("package", help="Package name to show dependencies for")
    tree_parser.add_argument(
        "-d", "--depth", type=int, default=None, help="Maximum tree depth (default: unlimited)"
    )
    _add_runtime_arg(tree_parser)
    _add_source_arg(tree_parser)
    _add_filter_args(tree_parser)
    tree_parser.add_argument(
        "--full",
        action="store_true",
        help="Expand repeated subtrees instead of collapsing them (can be very large)",
    )
    tree_parser.add_argument(
        "--expand-repeats",
        action="store_true",
        help="List back-references on their own lines instead of summarising them",
    )
    tree_parser.add_argument(
        "--max-nodes",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N nodes (safety valve, mostly useful with --full)",
    )
    tree_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show package descriptions"
    )
    tree_parser.add_argument("--json", action="store_true", help="Output as JSON")
    tree_parser.set_defaults(func=cmd_tree)

    # rostree why
    why_parser = subparsers.add_parser(
        "why",
        help="Explain why a package depends on another",
        description="Show the shortest dependency paths from one package to another.",
    )
    why_parser.add_argument("package", help="Package to start from")
    why_parser.add_argument("dependency", help="Dependency to explain")
    why_parser.add_argument(
        "-d", "--depth", type=int, default=None, help="Maximum search depth (default: unlimited)"
    )
    why_parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=10,
        metavar="N",
        help="Show at most N paths (default: 10)",
    )
    _add_runtime_arg(why_parser)
    _add_source_arg(why_parser)
    _add_filter_args(why_parser)
    why_parser.add_argument("--json", action="store_true", help="Output as JSON")
    why_parser.set_defaults(func=cmd_why)

    # rostree rdeps
    rdeps_parser = subparsers.add_parser(
        "rdeps",
        help="List packages that depend on a package",
        description="Reverse dependency lookup: what would break if this package changed?",
    )
    rdeps_parser.add_argument("package", help="Package to look up")
    rdeps_parser.add_argument(
        "-t", "--transitive", action="store_true", help="Include indirect dependents"
    )
    _add_runtime_arg(rdeps_parser)
    _add_source_arg(rdeps_parser)
    _add_filter_args(rdeps_parser)
    rdeps_parser.add_argument("-v", "--verbose", action="store_true", help="Show package source")
    rdeps_parser.add_argument("--json", action="store_true", help="Output as JSON")
    rdeps_parser.set_defaults(func=cmd_rdeps)

    # rostree check
    check_parser = subparsers.add_parser(
        "check",
        help="Check for dependency cycles and unresolved dependencies",
        description=(
            "Report dependency cycles and dependencies that resolve to nothing. "
            "Exits non-zero when problems are found, so it can gate CI."
        ),
    )
    check_parser.add_argument(
        "packages", nargs="*", help="Packages to check (default: every workspace package)"
    )
    check_parser.add_argument(
        "--junit",
        metavar="FILE",
        help="Also write a JUnit XML report, for CI dashboards",
    )
    check_parser.add_argument(
        "--ignore-system",
        action="store_true",
        help="Ignore unresolved names that look like rosdep keys",
    )
    _add_runtime_arg(check_parser)
    _add_source_arg(check_parser)
    _add_filter_args(check_parser)
    check_parser.add_argument("--json", action="store_true", help="Output as JSON")
    check_parser.set_defaults(func=cmd_check)

    # rostree diff
    diff_parser = subparsers.add_parser(
        "diff",
        help="Compare two packages' dependencies, or a package against a snapshot",
        description=(
            "Show what a package gained, lost or bumped. Compare it against another "
            "package, or against a snapshot taken earlier with --save."
        ),
    )
    diff_parser.add_argument("package", help="Package to inspect")
    diff_parser.add_argument(
        "other", nargs="?", help="Second package to compare against (optional)"
    )
    diff_parser.add_argument(
        "--save", metavar="FILE", help="Write this package's dependency set to FILE and exit"
    )
    diff_parser.add_argument(
        "--against", metavar="FILE", help="Compare against a snapshot written by --save"
    )
    diff_parser.add_argument(
        "-d", "--depth", type=int, default=None, help="Maximum depth (default: unlimited)"
    )
    _add_runtime_arg(diff_parser)
    _add_source_arg(diff_parser)
    _add_filter_args(diff_parser)
    diff_parser.add_argument("--json", action="store_true", help="Output as JSON")
    diff_parser.set_defaults(func=cmd_diff)

    # rostree graph
    graph_parser = subparsers.add_parser(
        "graph",
        help="Generate a dependency graph (DOT/Mermaid format)",
        description=(
            "Generate a visual dependency graph. "
            "Without arguments, graphs all workspace packages. "
            "Specify a package name to graph just that package."
        ),
    )
    graph_parser.add_argument(
        "package", nargs="?", help="Package name to graph (optional; without it, graphs workspace)"
    )
    graph_parser.add_argument(
        "-w", "--workspace", metavar="PATH", help="Scan and graph packages from this workspace path"
    )
    graph_parser.add_argument(
        "-f",
        "--format",
        choices=["dot", "mermaid"],
        default="dot",
        help="Output format: dot (Graphviz) or mermaid (default: dot)",
    )
    graph_parser.add_argument(
        "-o", "--output", metavar="FILE", help="Output file (default: stdout)"
    )
    graph_parser.add_argument(
        "-d",
        "--depth",
        type=int,
        default=None,
        help=(
            f"Maximum tree depth (default: {GRAPH_DEFAULT_DEPTH} for workspace, "
            "unlimited for single package)"
        ),
    )
    _add_runtime_arg(graph_parser)
    _add_source_arg(graph_parser)
    _add_filter_args(graph_parser, short_workspace=False)
    graph_parser.add_argument(
        "--hide-missing",
        action="store_true",
        help="Omit dependencies that do not resolve (they are drawn dashed by default)",
    )
    graph_parser.add_argument("--no-title", action="store_true", help="Don't include a title")
    graph_parser.add_argument(
        "--render",
        choices=["png", "svg", "pdf"],
        metavar="FORMAT",
        help="Render to image (png, svg, pdf). Requires Graphviz installed.",
    )
    graph_parser.add_argument(
        "--open", action="store_true", help="Open the rendered image after creation"
    )
    graph_parser.set_defaults(func=cmd_graph)

    # rostree tui (default if no command)
    tui_parser = subparsers.add_parser(
        "tui",
        help="Launch the interactive terminal UI",
        description="Start the interactive TUI for browsing packages and dependencies.",
    )
    tui_parser.add_argument("package", nargs="?", help="Optional: start with this package's tree")
    tui_parser.add_argument(
        "--all-deps",
        action="store_true",
        help="Follow build and test dependencies too (default: runtime only)",
    )
    tui_parser.set_defaults(func=cmd_tui)

    for subparser in subparsers.choices.values():
        _add_global_args(subparser)

    args = parser.parse_args(argv)
    _configure_console(args)

    # Default to TUI if no command specified
    if args.command is None:
        return cmd_tui(argparse.Namespace(package=None))

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
