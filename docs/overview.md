# Overview

rosdep_viz visualizes ROS 2 package dependencies as a navigable tree. The same core logic is used in three ways:

1. **Library** — Python API: find packages, parse package.xml, build dependency trees.
2. **TUI** — Terminal UI (Textual): browse packages and explore trees in the terminal.
3. **Web app** — FastAPI backend + React frontend: list packages and view trees in the browser.

## Data flow

```
Environment (AMENT_PREFIX_PATH, COLCON_PREFIX_PATH, …)
    ↓
Finder (core/finder.py) — list package paths, find package.xml by name
    ↓
Parser (core/parser.py) — read package.xml: name, version, description, dependencies
    ↓
Tree (core/tree.py) — build DependencyNode tree (recursive, cycle-safe)
    ↓
API (api.py) — list_known_packages(), get_package_info(), build_tree()
    ↓
TUI (tui/app.py) or Web backend (rosdep_viz_webapp/backend) or your script
```

- **Finder** only uses environment variables and optional workspace vars; it does not hardcode `/opt/ros/...`. See [Package discovery](package-discovery.md).
- **Parser** reads only `<depend>`, `<exec_depend>`, `<build_depend>`, etc. from package.xml. See [Dependency trees](dependency-trees.md).
- **Tree** can be built with `runtime_only=True` (depend + exec_depend only) for smaller, faster trees, or with all dependency tags.

## Components

| Component | Purpose |
|-----------|--------|
| `core/finder.py` | Discover package paths from install and source workspaces |
| `core/parser.py` | Parse package.xml for metadata and dependency list |
| `core/tree.py` | Build a `DependencyNode` tree from a root package name |
| `api.py` | Public API used by TUI, web backend, and scripts |
| `tui/app.py` | Textual TUI: welcome screen, tree view, back to package list |

The web app lives in `rosdep_viz_webapp/` (backend + frontend) and depends on this package for all ROS 2 logic.

## Requirements

- Python 3.10+
- A sourced ROS 2 environment so that `AMENT_PREFIX_PATH` and/or `COLCON_PREFIX_PATH` are set (e.g. `source /opt/ros/<distro>/setup.bash` and/or `source install/setup.bash`).

See [Package discovery](package-discovery.md) for how other workspaces are included.
