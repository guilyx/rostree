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

![rostree demo](docs/media/rostree-demo.gif)

*[Full demo reel](docs/media/rostree-demo.mp4) · [how the demo was made](docs/media/README.md)*

**Docs:** [docs/README.md](docs/README.md) — overview, package discovery, dependency trees, usage, development.

## Quick start

```bash
pip install rostree
source /opt/ros/<distro>/setup.bash   # and/or your workspace install/setup.bash
rostree                               # interactive TUI
```

## Why it is fast

A ROS dependency graph is a **DAG, not a tree**: `rcutils` sits under almost every
branch. Expanding each path separately is exponential — a 159-package workspace
printed 68,081 lines at depth 7, and never finished without a depth limit.

rostree expands each package **once, where it first appears**, and references it
elsewhere (`↩ see above`), the way `cargo tree` does with `(*)`. Package discovery
happens once per run instead of once per node, and manifests are parsed once.

| `rostree tree nav2_bringup -r` | 0.2.2 | 0.3.0 |
|--------------------------------|-------|-------|
| depth 6 | 18,273 lines / 4.4 s | 548 lines / 0.02 s |
| depth 7 | 68,081 lines / 17.4 s | 552 lines / 0.02 s |
| no depth limit (the default) | did not finish in 4 min | 552 lines / 0.02 s |

Nothing is hidden: every edge is still shown, once. `--full` restores the fully
expanded tree if you want it.

### CLI commands

```bash
rostree                      # Launch interactive TUI
rostree scan                 # Scan host for ROS 2 workspaces
rostree list --by-source     # List packages grouped by source
rostree list -f nav2         # Filter the package list

rostree tree rclcpp          # Dependency tree
rostree tree rclcpp -r -d 3  # Runtime deps only, 3 levels
rostree tree rclcpp --json   # Machine-readable

rostree why nav2_bringup rcutils   # How did this get into my tree?
rostree rdeps rclcpp               # What depends on this package?
rostree check                      # Cycles + unresolved deps (non-zero exit for CI)

rostree graph rclcpp --render png       # PNG via Graphviz
rostree graph rclcpp --render svg --open
rostree graph -w ~/ros2_ws --render png # Whole workspace
rostree graph rclcpp -f mermaid         # Mermaid text
```

### TUI

```bash
rostree tui                  # Interactive terminal UI
rostree tui rclcpp           # Start on a package's tree
```

`/` filters every package as you type, `Enter` opens a tree, `v` flips to
"what depends on this", `t` switches between runtime and all dependencies, and
`?` shows the full keymap. Scanning and tree building run off the UI thread, and
rows are created as you expand them, so nothing blocks.

<p align="center">
  <img src="docs/media/tui-tree.png" alt="rostree TUI showing a dependency tree" width="820">
</p>

### Python API

```python
from rostree import list_known_packages, get_package_info, build_tree, scan_workspaces
from rostree.api import build_graph, reverse_dependencies, tree_stats

packages = list_known_packages()
root = build_tree("rclcpp", runtime_only=True)
print(tree_stats(root))                  # nodes, packages, depth, repeats, missing

graph = build_graph("nav2_bringup")      # the resolved DAG, linear to build
print(graph.cycles(), sorted(graph.missing))

print(reverse_dependencies("rclcpp"))    # who depends on it
```

## Links

- [How the system works](docs/overview.md)
- [How packages are found](docs/package-discovery.md) (workspaces, AMENT_PREFIX_PATH, COLCON_WORKSPACE)
- [Dependency trees](docs/dependency-trees.md) (package.xml, the package index, repeat collapsing)
- [Usage](docs/usage.md) (CLI, TUI keys, API)
- [Development](docs/development.md) (layout, pre-commit, CI)
- [Changelog](CHANGELOG.md)
