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
rostree list -v              # Show package paths
rostree list --json          # Output as JSON
rostree list -s /extra/src   # Add extra source directories
```

### `rostree tree`

Show dependency tree for a package.

```bash
rostree tree rclpy           # Show full dependency tree
rostree tree rclpy -d 3      # Limit depth to 3 levels
rostree tree rclpy -r        # Runtime-only (depend + exec_depend)
rostree tree rclpy --json    # Output as JSON
rostree tree rclpy -s /src   # Add extra source directories
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
```

**Install Graphviz for `--render`:**

```bash
# Ubuntu/Debian
sudo apt install graphviz

# macOS
brew install graphviz

# Or download from https://graphviz.org/download/
```

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

### Flow

1. **Welcome screen** — Banner and description. Press **Enter** to start, **q** to quit.
2. **Package list** — Packages grouped by source (System, Workspace, etc.). Select a package to load its tree.
3. **Tree view** — Dependency tree with details panel. Navigate with arrow keys.

### Keys

| Key | Action |
|-----|--------|
| **Enter** | Select/expand |
| **Esc** or **b** | Back to package list |
| **/** or **f** | Search for packages |
| **n** / **N** | Next/previous search match |
| **d** | Toggle details panel |
| **e** | Expand all tree nodes |
| **c** | Collapse all |
| **a** | Add extra source path |
| **r** | Refresh |
| **q** | Quit |

### Details Panel

For the selected node:

- **Direct dependencies** — Immediate children count
- **Total descendants** — All nodes below
- **Max depth** — Levels below this node

### TUI Limits

- **Runtime-only**: Only `depend` and `exec_depend` (faster)
- **Max depth**: 6 levels
- **Max nodes**: 500 (truncated beyond)

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

### Options

- **build_tree(name, max_depth=None, runtime_only=False, extra_source_roots=None)**
  - `max_depth`: Limit recursion depth
  - `runtime_only=True`: Only depend + exec_depend (faster, smaller)
  - `extra_source_roots`: Additional paths to scan for packages

- **scan_workspaces(roots=None, max_depth=4, include_home=True, include_opt_ros=True)**
  - `roots`: Directories to scan (default: common locations)
  - `include_home`: Scan ~/ros*_ws, ~/dev, etc.
  - `include_opt_ros`: Include /opt/ros/* system installs
