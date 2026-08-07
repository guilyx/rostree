# Overview

rostree visualizes ROS 2 package dependencies as a navigable tree. The same core logic is used in three ways:

1. **Library** — Python API: find packages, parse package.xml, build dependency trees and graphs.
2. **CLI** — `rostree tree/why/rdeps/check/graph/list/scan`.
3. **TUI** — Terminal UI (Textual): browse packages and explore trees interactively.

## Data flow

```
Environment (AMENT_PREFIX_PATH, COLCON_PREFIX_PATH, …)
    ↓
Index (core/index.py) — scan every prefix and source tree ONCE; resolve names from memory
    ↓
Parser (core/parser.py) — read package.xml: name, version, description, dependencies (memoized)
    ↓
Tree (core/tree.py) — breadth-first DAG resolution, then a tree with repeats collapsed
    ↓
Graph (core/graph.py) — DOT / Mermaid text from a resolved graph
    ↓
API (api.py) — list_known_packages(), get_package_info(), build_tree(), build_graph()
    ↓
CLI (cli.py) or TUI (tui/app.py) or your script
```

- **Index** is the reason large trees are fast: package discovery happens once per
  run rather than once per node. It is cached per process and per environment; pass
  `refresh=True` after rebuilding packages.
- **Finder** only uses environment variables and optional workspace vars; it does not hardcode `/opt/ros/...`. See [Package discovery](package-discovery.md).
- **Parser** reads only `<depend>`, `<exec_depend>`, `<build_depend>`, etc. from package.xml. See [Dependency trees](dependency-trees.md).
- **Tree** expands each package once, where it first appears, so output is
  proportional to the graph rather than to its (exponentially many) paths.

## Components

| Component | Purpose |
|-----------|--------|
| `core/index.py` | One-pass, cached index of every visible package; reverse dependencies |
| `core/finder.py` | Workspace scanning, plus name lookups on top of the index |
| `core/parser.py` | Parse package.xml for metadata and dependency list |
| `core/tree.py` | Build a `DependencyGraph` and a `DependencyNode` tree |
| `core/graph.py` | Render a resolved graph as DOT or Mermaid |
| `api.py` | Public API used by the CLI, the TUI and scripts |
| `cli.py` | Argument parsing, terminal rendering, image rendering backends |
| `tui/app.py` | Textual TUI: package list, tree view, reverse view, help |

## Requirements

- Python 3.10+
- A sourced ROS 2 environment so that `AMENT_PREFIX_PATH` and/or `COLCON_PREFIX_PATH` are set (e.g. `source /opt/ros/<distro>/setup.bash` and/or `source install/setup.bash`).

See [Package discovery](package-discovery.md) for how other workspaces are included.
