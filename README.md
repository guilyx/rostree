```
██████╗  ██████╗ ███████╗████████╗██████╗ ███████╗███████╗
██╔══██╗██╔═══██╗██╔════╝╚══██╔══╝██╔══██╗██╔════╝██╔════╝
██████╔╝██║   ██║███████╗   ██║   ██████╔╝█████╗  █████╗
██╔══██╗██║   ██║╚════██║   ██║   ██╔══██╗██╔══╝  ██╔══╝
██║  ██║╚██████╔╝███████║   ██║   ██║  ██║███████╗███████╗
╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚══════╝
```

[![CI](https://github.com/guilyx/rostree/actions/workflows/ci.yml/badge.svg)](https://github.com/guilyx/rostree/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/guilyx/rostree/graph/badge.svg)](https://codecov.io/gh/guilyx/rostree)
[![PyPI version](https://img.shields.io/pypi/v/rostree.svg)](https://pypi.org/project/rostree/)
[![PyPI downloads](https://img.shields.io/pypi/dm/rostree.svg)](https://pypi.org/project/rostree/)
[![Python versions](https://img.shields.io/pypi/pyversions/rostree.svg)](https://pypi.org/project/rostree/)
[![License](https://img.shields.io/github/license/guilyx/rostree.svg)](https://github.com/guilyx/rostree/blob/main/LICENSE)

Explore ROS 2 package dependencies from the command line (CLI, TUI, library).

**Docs:** [docs/README.md](docs/README.md) — overview, package discovery, dependency trees, usage, development.

## Quick start

```bash
pip install -e .   # or: uv pip install -e .
source /opt/ros/<distro>/setup.bash   # and/or your workspace install/setup.bash
```

### CLI commands

```bash
rostree                      # Launch interactive TUI
rostree scan                 # Scan host for ROS 2 workspaces
rostree scan ~/dev --depth 3 # Scan specific directories
rostree list                 # List known packages
rostree list --by-source     # List packages grouped by source
rostree tree rclpy           # Show dependency tree for a package
rostree tree rclpy --depth 3 # Limit tree depth
rostree tree rclpy --json    # Output as JSON
rostree graph rclpy          # Generate DOT graph for Graphviz
rostree graph -w ~/ros2_ws   # Graph entire workspace
rostree graph rclpy -f mermaid -o deps.md  # Mermaid format
```

### TUI mode

```bash
rostree tui                  # Interactive terminal UI
rostree tui rclpy            # Start TUI with a specific package tree
```

### Python API

```python
from rostree import list_known_packages, get_package_info, build_tree, scan_workspaces

packages = list_known_packages()
root = build_tree("rclpy", max_depth=5, runtime_only=True)
workspaces = scan_workspaces()  # Scan host for ROS 2 workspaces
```

## Links

- [How the system works](docs/overview.md)
- [How packages are found](docs/package-discovery.md) (workspaces, AMENT_PREFIX_PATH, COLCON_WORKSPACE)
- [Dependency trees](docs/dependency-trees.md) (package.xml, runtime_only)
- [Usage](docs/usage.md) (CLI, TUI keys, API)
- [Development](docs/development.md) (layout, pre-commit, CI)
