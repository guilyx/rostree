# Usage

## CLI Commands

### `rostree` (default: TUI)

```bash
rostree                      # Launch interactive TUI
rostree tui                  # Same as above
rostree tui rclpy            # Start TUI with a specific package tree
```

### `rostree scan`

Discover ROS 2 workspaces on the host machine.

```bash
rostree scan                 # Scan default locations (~/ros*_ws, /opt/ros/*, etc.)
rostree scan ~/dev --depth 3 # Scan specific directories
rostree scan --no-home       # Skip home directory
rostree scan --no-system     # Skip /opt/ros system installs
rostree scan --json          # Output as JSON
rostree scan -v              # Verbose: show packages in each workspace
```

### `rostree list`

List known ROS 2 packages in the current environment.

```bash
rostree list                 # List all packages
rostree list --by-source     # Group by source (System, Workspace, etc.)
rostree list -f nav2         # Only packages whose name contains "nav2"
rostree list -v              # Show package paths
rostree list --json          # Output as JSON
rostree list -s /extra/src   # Add extra source directories
```

### `rostree tree`

Show the dependency tree for a package.

```bash
rostree tree rclpy           # Full tree (unlimited depth is fine now)
rostree tree rclpy -d 3      # Limit depth to 3 levels
rostree tree rclpy -r        # Runtime-only (depend + exec_depend)
rostree tree rclpy -v        # Include package descriptions
rostree tree rclpy --json    # Output as JSON
rostree tree rclpy -s /src   # Add extra source directories
```

A package that appears in several branches is expanded where it first appears;
elsewhere it is summarised as `↩ 5 already shown above: …`. That is what keeps a
full-depth tree instant instead of exponential — see
[Dependency trees](dependency-trees.md#repeats-why-trees-stay-small).

```bash
rostree tree rclpy --expand-repeats   # One line per back-reference
rostree tree rclpy --full             # Re-expand every occurrence (can be huge)
rostree tree rclpy --full --max-nodes 5000
```

The tree goes to stdout and the summary line to stderr, so `rostree tree rclpy > deps.txt`
captures just the tree.

### `rostree why`

Explain how one package ends up depending on another.

```bash
rostree why nav2_bringup rcutils       # Shortest paths between the two
rostree why nav2_bringup rcutils -r    # Runtime dependencies only
rostree why nav2_bringup rcutils -n 3  # At most 3 paths
rostree why nav2_bringup rcutils --json
```

Exits non-zero when there is no dependency path at all.

### `rostree rdeps`

Reverse lookup: what would be affected if this package changed?

```bash
rostree rdeps rclcpp              # Direct dependents
rostree rdeps rclcpp -t           # Include indirect dependents
rostree rdeps rclcpp -w           # Skip packages installed under /opt/ros
rostree rdeps rclcpp --json
```

### `rostree check`

Report dependency cycles and unresolved dependencies. Exits non-zero when it finds
problems, so it can gate CI.

```bash
rostree check                     # Every workspace package
rostree check nav2_bringup        # Specific roots
rostree check --ignore-system     # Ignore names that look like rosdep keys
rostree check --json
```

### `rostree graph`

Generate dependency graphs in DOT (Graphviz) or Mermaid format. Can render directly to PNG/SVG/PDF.

```bash
# Single package - render to image (requires Graphviz)
rostree graph rclpy --render png           # Creates rclpy.png
rostree graph rclpy --render svg --open    # Create SVG and open it
rostree graph rclpy --render pdf -o out.pdf

# Single package - text output
rostree graph rclpy                    # DOT format to stdout
rostree graph rclpy -f mermaid         # Mermaid format
rostree graph rclpy -o deps.dot        # Write DOT to file
rostree graph rclpy -d 3               # Limit depth

# Entire workspace (current environment)
rostree graph --render png             # Graph all non-system packages
rostree graph -d 2 --render svg        # Limit depth for performance

# Specific workspace
rostree graph -w ~/ros2_ws --render png    # Scan and graph workspace
rostree graph -w ~/ros2_ws -f mermaid      # Mermaid format (text only)

# Options
rostree graph rclpy -r                 # Runtime-only dependencies
rostree graph rclpy --no-title         # No title in graph
rostree graph rclpy --hide-missing     # Omit unresolved dependencies
```

Dependencies that do not resolve to a `package.xml` (rosdep keys, packages that
are not built yet) are drawn **dashed and grey** rather than dropped. Dropping
them is what used to leave workspace graphs as a set of unconnected boxes. Pass
`--hide-missing` if you only want edges between packages you actually have.

`-w/--workspace` also puts that workspace on the search path, so it works on a
workspace you have not sourced.

**Install a rendering backend for `--render`:**

Option 1: **Graphviz** (best quality, system package)
```bash
# Ubuntu/Debian
sudo apt install graphviz

# macOS
brew install graphviz
```

Option 2: **matplotlib** (pure pip, no system deps)
```bash
pip install rostree[viz]
# or: pip install matplotlib networkx
```

If both are available, Graphviz is preferred for better layout quality.

**Manual rendering (alternative):**

```bash
# DOT → PNG
rostree graph rclpy -o deps.dot
dot -Tpng deps.dot -o deps.png

# Mermaid → view online
rostree graph rclpy -f mermaid | pbcopy  # Copy to clipboard
# Paste at https://mermaid.live
```

---

## TUI (Terminal UI)

```bash
rostree                  # Launch the TUI
rostree tui nav2_bringup # Open straight into a package's tree
rostree tui --all-deps   # Follow build and test dependencies too
```

### Flow

1. **Welcome screen** — the package scan starts immediately in the background and
   reports its count when done. Press **Enter** to continue, **q** to quit.
2. **Package list** — every package, grouped by source. Press **/** and type to
   filter across all of them. **Enter** opens a package.
3. **Tree view** — the dependency tree, with a details panel on the right.

### Keys

| Key | Action |
|-----|--------|
| **?** | Keyboard reference |
| **/** or **f** | Filter the package list (or search an open tree) |
| **Enter** | Open the selected package / re-root the tree on it |
| **Esc** or **b** | Leave the filter, then go back to the package list |
| **↑ ↓** | Move |
| **n** / **N** | Next / previous search match |
| **d** | Show or hide the details panel |
| **v** | Reverse view: what depends on this package |
| **t** | Toggle runtime-only vs all dependencies |
| **e** / **c** | Expand all / collapse all |
| **a** | Add an extra source path |
| **r** | Rescan packages |
| **q** | Quit |

### Responsiveness

- Scanning and tree building both run on **worker threads**, so the UI never blocks.
- Tree rows are created **as you expand them**, so opening a package with thousands
  of transitive dependencies is instant.
- The package list is **not** truncated; use the filter to narrow it.

### Details panel

For the selected node: version, description, direct dependency count, total
descendants, depth below this node, which source it came from, and its
`package.xml` path.

---

## Python API

```python
from rostree import (
    list_known_packages,
    list_known_packages_by_source,
    get_package_info,
    build_tree,
    scan_workspaces,
)
from rostree.api import build_graph, get_index, reverse_dependencies, tree_stats

# List all packages
packages = list_known_packages()  # dict[str, Path]

# Group by source
by_source = list_known_packages_by_source()  # dict[str, list[str]]

# Package metadata
info = get_package_info("rclpy")
print(info.name, info.version, info.dependencies)

# Build dependency tree
root = build_tree("rclpy", max_depth=5, runtime_only=True)
print(root.name, len(root.children))
data = root.to_dict()  # JSON-friendly

# Scan for workspaces
workspaces = scan_workspaces()  # list[WorkspaceInfo]
for ws in workspaces:
    print(ws.path, ws.packages)
```

```python
# Statistics about a built tree
stats = tree_stats(root)
# {'nodes': 770, 'packages': 164, 'missing': 5, 'repeats': 543, 'cycles': 0, 'depth': 6}

# The resolved DAG, without materialising a tree
graph = build_graph("nav2_bringup", runtime_only=True)
print(len(graph.packages), len(graph.edge_pairs()), graph.cycles())

# Who depends on this package?
print(reverse_dependencies("rclcpp"))

# The package index itself
index = get_index()
print(index.resolve("rclcpp"), len(index), index.by_label().keys())
```

### Options

- **build_tree(name, max_depth=None, runtime_only=False, collapse_repeats=True, extra_source_roots=None)**
  - `max_depth`: Limit recursion depth
  - `runtime_only=True`: Only depend + exec_depend (faster, smaller)
  - `collapse_repeats=False`: Expand every occurrence of a package instead of
    referencing the first one. Exponential on real graphs — bound it with
    `max_depth`.
  - `extra_source_roots`: Additional paths to scan for packages

- **build_graph(root_packages, max_depth=None, runtime_only=False)**
  - Accepts one name or a list; returns a `DependencyGraph` with `edges`,
    `packages`, `missing`, `depths` and `cycles()`

- **scan_workspaces(roots=None, max_depth=4, include_home=True, include_opt_ros=True)**
  - `roots`: Directories to scan (default: common locations)
  - `include_home`: Scan ~/ros*_ws, ~/dev, etc.
  - `include_opt_ros`: Include /opt/ros/* system installs
