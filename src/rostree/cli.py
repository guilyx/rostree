"""Command-line interface for rostree: scan workspaces, list packages, show dependency trees."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from rostree.core.finder import (
    list_package_paths,
    list_packages_by_source,
    scan_for_workspaces,
)
from rostree.core.tree import build_dependency_tree, DependencyNode


def _print_tree_text(node: DependencyNode, indent: int = 0, prefix: str = "") -> None:
    """Print a dependency tree as indented text."""
    marker = "├── " if prefix else ""
    version = f" ({node.version})" if node.version else ""
    desc = (
        f" - {node.description}"
        if node.description and node.description not in ("(not found)", "(cycle)", "(parse error)")
        else ""
    )
    if node.description in ("(not found)", "(cycle)", "(parse error)"):
        desc = f" [{node.description}]"
    print(f"{prefix}{marker}{node.name}{version}{desc}")

    children = node.children
    for i, child in enumerate(children):
        is_last = i == len(children) - 1
        child_prefix = prefix + ("    " if is_last or not prefix else "│   ")
        _print_tree_text(child, indent + 1, child_prefix if prefix else "")


def cmd_scan(args: argparse.Namespace) -> int:
    """Scan for ROS 2 workspaces on the host."""
    roots = [Path(p) for p in args.paths] if args.paths else None
    workspaces = scan_for_workspaces(
        roots=roots,
        max_depth=args.depth,
        include_home=not args.no_home,
        include_opt_ros=not args.no_system,
    )

    if args.json:
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
            if args.verbose and ws.packages:
                for pkg in ws.packages[:20]:
                    print(f"      - {pkg}")
                if len(ws.packages) > 20:
                    print(f"      ... and {len(ws.packages) - 20} more")
            print()
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List known ROS 2 packages."""
    extra_roots = [Path(p) for p in args.source] if args.source else None

    if args.by_source:
        by_source = list_packages_by_source(extra_source_roots=extra_roots)
        if args.json:
            print(json.dumps(by_source, indent=2))
        else:
            if not by_source:
                print("No packages found. Is your ROS 2 environment sourced?")
                return 1
            total = sum(len(pkgs) for pkgs in by_source.values())
            print(f"Found {total} package(s) from {len(by_source)} source(s):\n")
            for source, packages in by_source.items():
                print(f"  {source} ({len(packages)})")
                if args.verbose:
                    for pkg in packages[:50]:
                        print(f"    - {pkg}")
                    if len(packages) > 50:
                        print(f"    ... and {len(packages) - 50} more")
                print()
    else:
        packages = list_package_paths(extra_source_roots=extra_roots)
        if args.json:
            print(json.dumps({name: str(path) for name, path in packages.items()}, indent=2))
        else:
            if not packages:
                print("No packages found. Is your ROS 2 environment sourced?")
                return 1
            print(f"Found {len(packages)} package(s):\n")
            for name in sorted(packages.keys()):
                if args.verbose:
                    print(f"  {name}: {packages[name]}")
                else:
                    print(f"  {name}")
    return 0


def cmd_tree(args: argparse.Namespace) -> int:
    """Show dependency tree for a package."""
    extra_roots = [Path(p) for p in args.source] if args.source else None

    tree = build_dependency_tree(
        args.package,
        max_depth=args.depth,
        runtime_only=args.runtime,
        extra_source_roots=extra_roots,
    )

    if tree is None:
        print(f"Package not found: {args.package}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(tree.to_dict(), indent=2))
    else:
        _print_tree_text(tree)
    return 0


def cmd_tui(args: argparse.Namespace) -> int:
    """Launch the interactive TUI."""
    from rostree.tui.app import DepTreeApp

    app = DepTreeApp(root_package=args.package if hasattr(args, "package") else None)
    app.run()
    return 0


def _collect_edges(
    node: DependencyNode,
    edges: set[tuple[str, str]],
    visited: set[str] | None = None,
) -> None:
    """Recursively collect all edges (parent -> child) from a dependency tree."""
    if visited is None:
        visited = set()
    if node.name in visited:
        return
    visited.add(node.name)
    for child in node.children:
        # Skip special markers
        if child.description in ("(cycle)", "(not found)", "(parse error)"):
            continue
        edges.add((node.name, child.name))
        _collect_edges(child, edges, visited)


def _collect_edges_multi(
    trees: list[DependencyNode],
    root_names: set[str],
) -> tuple[set[tuple[str, str]], set[str]]:
    """Collect edges from multiple trees, tracking which nodes are roots."""
    edges: set[tuple[str, str]] = set()
    all_nodes: set[str] = set()
    for tree in trees:
        _collect_edges(tree, edges)
        all_nodes.add(tree.name)
        # Also collect all node names from edges
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
    root_names = {r.name for r in roots}
    edges: set[tuple[str, str]] = set()
    for root in roots:
        _collect_edges(root, edges)

    lines = [
        "digraph dependencies {",
        "    rankdir=LR;",
        '    node [shape=box, style=rounded, fontname="sans-serif"];',
    ]
    if title:
        lines.insert(1, f'    label="{title}";')
        lines.insert(2, "    labelloc=t;")

    # Highlight root nodes
    if highlight_roots:
        for name in sorted(root_names):
            lines.append(f'    "{name}" [style="rounded,filled", fillcolor=lightblue];')

    for parent, child in sorted(edges):
        lines.append(f'    "{parent}" -> "{child}";')

    lines.append("}")
    return "\n".join(lines)


def _generate_mermaid(
    roots: list[DependencyNode],
    title: str | None = None,
    highlight_roots: bool = True,
) -> str:
    """Generate Mermaid format from dependency trees."""
    root_names = {r.name for r in roots}
    edges: set[tuple[str, str]] = set()
    for root in roots:
        _collect_edges(root, edges)

    lines = ["graph LR"]
    if title:
        lines[0] = f"---\ntitle: {title}\n---\ngraph LR"

    # Style root nodes
    if highlight_roots:
        for name in sorted(root_names):
            lines.append(f"    {_mermaid_id(name)}[{name}]")
            lines.append(f"    style {_mermaid_id(name)} fill:#lightblue")

    for parent, child in sorted(edges):
        lines.append(f"    {_mermaid_id(parent)} --> {_mermaid_id(child)}")

    return "\n".join(lines)


def _mermaid_id(name: str) -> str:
    """Convert a package name to a valid Mermaid node ID."""
    # Replace characters that are problematic in Mermaid
    return name.replace("-", "_").replace(".", "_")


def _get_workspace_packages(workspace_path: Path | None = None) -> list[str]:
    """Get packages from a workspace. If None, use current environment."""
    if workspace_path:
        # Scan the specified workspace
        ws_path = Path(workspace_path).resolve()
        src_path = ws_path / "src" if (ws_path / "src").exists() else ws_path
        if not src_path.exists():
            return []
        from rostree.core.finder import _list_packages_in_src

        return _list_packages_in_src(src_path)
    else:
        # Use packages from current environment's workspace (not system)
        by_source = list_packages_by_source()
        packages = []
        for label, names in by_source.items():
            # Only include Workspace and Source packages, not System
            if "System" not in label:
                packages.extend(names)
        return packages


# Default depth limit for graph to prevent hangs
GRAPH_DEFAULT_DEPTH = 4
GRAPH_MAX_PACKAGES = 50


def _check_graphviz() -> bool:
    """Check if Graphviz (dot) is available."""
    return shutil.which("dot") is not None


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
            ["dot", f"-T{format}", "-o", str(output_path)],
            input=dot_content,
            capture_output=True,
            text=True,
            timeout=60,
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


def _open_file(path: Path) -> bool:
    """Open a file with the system default application."""
    import platform

    system = platform.system()
    try:
        if system == "Darwin":  # macOS
            subprocess.run(["open", str(path)], check=True)
        elif system == "Windows":
            subprocess.run(["start", "", str(path)], shell=True, check=True)
        else:  # Linux and others
            subprocess.run(["xdg-open", str(path)], check=True)
        return True
    except Exception as e:
        print(f"Could not open file: {e}", file=sys.stderr)
        return False


def cmd_graph(args: argparse.Namespace) -> int:
    """Generate a dependency graph in DOT or Mermaid format."""
    extra_roots = [Path(p) for p in args.source] if args.source else None

    # Determine packages to graph
    packages_to_graph: list[str] = []

    if args.package:
        packages_to_graph = [args.package]
    elif args.workspace:
        # Scan specified workspace
        packages_to_graph = _get_workspace_packages(Path(args.workspace))
        if not packages_to_graph:
            print(f"No packages found in workspace: {args.workspace}", file=sys.stderr)
            return 1
    else:
        # Use current environment's non-system packages
        packages_to_graph = _get_workspace_packages(None)
        if not packages_to_graph:
            print(
                "No workspace packages found. Specify a package or use --workspace.",
                file=sys.stderr,
            )
            return 1

    # Limit packages for performance
    if len(packages_to_graph) > GRAPH_MAX_PACKAGES and not args.package:
        print(
            f"Warning: Limiting to first {GRAPH_MAX_PACKAGES} packages "
            f"(found {len(packages_to_graph)}). Use -d to limit depth.",
            file=sys.stderr,
        )
        packages_to_graph = packages_to_graph[:GRAPH_MAX_PACKAGES]

    # Use default depth for workspace graphs (prevent hangs), unlimited for single package
    if args.depth is not None:
        depth = args.depth
    elif args.package:
        depth = None  # Unlimited for single package
    else:
        depth = GRAPH_DEFAULT_DEPTH  # Limited for workspace-wide

    # Build trees for all packages
    trees: list[DependencyNode] = []
    for i, pkg in enumerate(packages_to_graph):
        if len(packages_to_graph) > 1:
            print(f"Processing {pkg} ({i + 1}/{len(packages_to_graph)})...", file=sys.stderr)
        tree = build_dependency_tree(
            pkg,
            max_depth=depth,
            runtime_only=args.runtime,
            extra_source_roots=extra_roots,
        )
        if tree is not None:
            trees.append(tree)

    if not trees:
        print("No valid package trees found.", file=sys.stderr)
        return 1

    # Generate title
    if args.no_title:
        title = None
    elif args.package:
        title = f"{args.package} dependencies"
    elif args.workspace:
        title = f"Workspace: {Path(args.workspace).name}"
    else:
        title = "Workspace dependencies"

    if args.format == "mermaid":
        output = _generate_mermaid(trees, title=title)
    else:  # dot
        output = _generate_dot(trees, title=title)

    # Handle rendering to image
    render_format = getattr(args, "render", None)
    if render_format:
        if args.format == "mermaid":
            print(
                "Error: --render only works with DOT format (not mermaid). "
                "Remove -f mermaid or use mermaid.live for rendering.",
                file=sys.stderr,
            )
            return 1

        # Determine output path
        if args.output:
            # If output specified, use it with proper extension
            out_path = Path(args.output)
            if out_path.suffix.lower() not in (f".{render_format}", ".dot"):
                out_path = out_path.with_suffix(f".{render_format}")
        else:
            # Default filename based on package or workspace
            if args.package:
                base_name = args.package.replace("/", "_")
            elif args.workspace:
                base_name = Path(args.workspace).name
            else:
                base_name = "workspace_deps"
            out_path = Path(f"{base_name}.{render_format}")

        print(f"Rendering graph to {out_path}...", file=sys.stderr)
        if not _render_dot(output, out_path, render_format):
            return 1

        print(f"Graph image saved to: {out_path}", file=sys.stderr)

        # Open the file if requested
        if getattr(args, "open", False):
            _open_file(out_path)

        return 0

    # Just output text (DOT or Mermaid)
    if args.output:
        Path(args.output).write_text(output)
        print(f"Graph written to: {args.output}", file=sys.stderr)
    else:
        print(output)

    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the rostree CLI."""
    parser = argparse.ArgumentParser(
        prog="rostree",
        description="Explore ROS 2 package dependencies from the command line.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")

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
        "-d",
        "--depth",
        type=int,
        default=4,
        help="Maximum recursion depth (default: 4)",
    )
    scan_parser.add_argument(
        "--no-home",
        action="store_true",
        help="Don't scan home directory locations",
    )
    scan_parser.add_argument(
        "--no-system",
        action="store_true",
        help="Don't scan /opt/ros system installs",
    )
    scan_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show packages in each workspace",
    )
    scan_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    scan_parser.set_defaults(func=cmd_scan)

    # rostree list
    list_parser = subparsers.add_parser(
        "list",
        help="List known ROS 2 packages",
        description="List packages visible in the current ROS 2 environment.",
    )
    list_parser.add_argument(
        "-s",
        "--source",
        action="append",
        metavar="PATH",
        help="Additional source directories to scan (can be repeated)",
    )
    list_parser.add_argument(
        "--by-source",
        action="store_true",
        help="Group packages by source (System, Workspace, etc.)",
    )
    list_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show package paths",
    )
    list_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    list_parser.set_defaults(func=cmd_list)

    # rostree tree
    tree_parser = subparsers.add_parser(
        "tree",
        help="Show dependency tree for a package",
        description="Build and display the dependency tree for a ROS 2 package.",
    )
    tree_parser.add_argument(
        "package",
        help="Package name to show dependencies for",
    )
    tree_parser.add_argument(
        "-d",
        "--depth",
        type=int,
        default=None,
        help="Maximum tree depth (default: unlimited)",
    )
    tree_parser.add_argument(
        "-r",
        "--runtime",
        action="store_true",
        help="Show only runtime dependencies (depend, exec_depend)",
    )
    tree_parser.add_argument(
        "-s",
        "--source",
        action="append",
        metavar="PATH",
        help="Additional source directories to scan (can be repeated)",
    )
    tree_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    tree_parser.set_defaults(func=cmd_tree)

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
        "package",
        nargs="?",
        help="Package name to graph (optional; without it, graphs workspace)",
    )
    graph_parser.add_argument(
        "-w",
        "--workspace",
        metavar="PATH",
        help="Scan and graph packages from this workspace path",
    )
    graph_parser.add_argument(
        "-f",
        "--format",
        choices=["dot", "mermaid"],
        default="dot",
        help="Output format: dot (Graphviz) or mermaid (default: dot)",
    )
    graph_parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="Output file (default: stdout)",
    )
    graph_parser.add_argument(
        "-d",
        "--depth",
        type=int,
        default=None,
        help=f"Maximum tree depth (default: {GRAPH_DEFAULT_DEPTH} for workspace, unlimited for single package)",
    )
    graph_parser.add_argument(
        "-r",
        "--runtime",
        action="store_true",
        help="Show only runtime dependencies (depend, exec_depend)",
    )
    graph_parser.add_argument(
        "-s",
        "--source",
        action="append",
        metavar="PATH",
        help="Additional source directories to scan (can be repeated)",
    )
    graph_parser.add_argument(
        "--no-title",
        action="store_true",
        help="Don't include a title in the graph",
    )
    graph_parser.add_argument(
        "--render",
        choices=["png", "svg", "pdf"],
        metavar="FORMAT",
        help="Render to image (png, svg, pdf). Requires Graphviz installed.",
    )
    graph_parser.add_argument(
        "--open",
        action="store_true",
        help="Open the rendered image after creation (use with --render)",
    )
    graph_parser.set_defaults(func=cmd_graph)

    # rostree tui (default if no command)
    tui_parser = subparsers.add_parser(
        "tui",
        help="Launch the interactive terminal UI",
        description="Start the interactive TUI for browsing packages and dependencies.",
    )
    tui_parser.add_argument(
        "package",
        nargs="?",
        help="Optional: start with this package's tree",
    )
    tui_parser.set_defaults(func=cmd_tui)

    args = parser.parse_args(argv)

    # Default to TUI if no command specified
    if args.command is None:
        return cmd_tui(argparse.Namespace(package=None))

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
