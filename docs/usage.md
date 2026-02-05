# Usage

## TUI (terminal)

```bash
# List known packages and select one to explore
rosdep_viz

# Open tree for a specific package
rosdep_viz rosbag2_bringup
```

### Flow

1. **Welcome screen** — Banner and short description. Press **Enter** to start, **q** to quit.
2. **Package list** — All packages from the environment (see [Package discovery](package-discovery.md)). Select a package to load its dependency tree.
3. **Tree view** — Dependency tree (runtime-only, max depth 6 by default). Select a node to see details (name, version, description, path, stats).

### Keys

| Key | Action |
|-----|--------|
| **Esc** or **b** | Back to package list (when viewing a tree) |
| **q** | Quit |
| **r** | Refresh (reload current tree or package list) |
| **e** | Expand all tree nodes |
| **c** | Collapse all (root stays expanded) |

A **“← Back to package list”** button appears above the tree when viewing a dependency tree; you can click it or use Esc / b.

### Details panel stats

For the selected node:

- **Direct dependencies** — Number of immediate children.
- **Total descendants** — All nodes below (children + grandchildren + …).
- **Max depth from here** — Number of levels below this node.

### TUI tree limits

- **Runtime-only**: only `depend` and `exec_depend` (no build/test deps), so trees load faster.
- **Max depth**: 6 levels.
- **Max nodes**: 500 (truncation message shown beyond that).

See [Dependency trees](dependency-trees.md) for runtime-only vs full tree.

---

## Python API

```python
from rosdep_viz import list_known_packages, get_package_info, build_tree

# All packages in the environment (name -> path to package.xml)
packages = list_known_packages()  # dict[str, Path]

# Metadata and dependencies for one package (no recursion)
info = get_package_info("rosbag2_bringup")
# info.name, info.version, info.description, info.dependencies

# Full dependency tree
root = build_tree("rosbag2_bringup", max_depth=5)
if root:
    print(root.name, root.version, len(root.children))
    data = root.to_dict()  # JSON-friendly for API/frontend
```

### Options

- **build_tree(name, max_depth=None, include_buildtool=False, runtime_only=False)**  
  - `max_depth`: limit depth (None = unlimited).  
  - `runtime_only=True`: only depend + exec_depend (smaller, faster).

---

## Web app

- **Backend**: FastAPI in `rosdep_viz_webapp/backend`. Endpoints: `GET /api/packages`, `GET /api/tree/{package_name}?max_depth=N`.
- **Frontend**: React + Vite + Tailwind in `rosdep_viz_webapp/frontend`. Load packages, select one, view interactive dependency graph (React Flow).

See `rosdep_viz_webapp/README.md` for run instructions. The backend uses this package for all ROS 2 logic; no extra docs needed here.
