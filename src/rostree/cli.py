"""Command-line interface for rostree: scan workspaces, list packages, show dependency trees."""

from __future__ import annotations

import argparse
import json
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
