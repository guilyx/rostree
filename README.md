# rosdep_viz

Visualize ROS 2 package dependencies as a navigable tree. Use it as a **library** from Python, from the **TUI** in the terminal, or from the **web app** (FastAPI + React).

## Features

- **Library**: Find packages (install + source), parse `package.xml`, build dependency trees.
- **TUI**: Terminal UI (Textual) to browse known packages and explore dependency trees (expand/collapse, select node for details).
- **API**: Same logic exposed via `rosdep_viz.api` for scripts and the web backend.

## Installation (uv)

From the `rosdep_viz` directory:

```bash
uv pip install -e .
# or with dev deps: uv pip install -e ".[dev]"
```

Or from the workspace root:

```bash
uv pip install -e src/rosdep_viz
```

Requires a ROS 2 environment (e.g. `source /opt/ros/<distro>/setup.bash` and/or your workspace `install/setup.bash`) so that `AMENT_PREFIX_PATH` / `COLCON_PREFIX_PATH` are set.

## Usage

### TUI

```bash
# List known packages and select one to explore
rosdep_viz

# Open tree for a specific package
rosdep_viz rosbag2_bringup
```

Keys: `q` quit, `r` refresh, `e` expand all, `c` collapse all. Select a node to see details.

### Python API

```python
from rosdep_viz import list_known_packages, get_package_info, build_tree

# All packages in the environment
packages = list_known_packages()  # dict[str, Path]

# Metadata and dependencies for one package
info = get_package_info("rosbag2_bringup")

# Full dependency tree
root = build_tree("rosbag2_bringup", max_depth=5)
if root:
    print(root.name, root.version, len(root.children))
    # Serialize for JSON/API
    data = root.to_dict()
```

## Development

Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/) (e.g. `fix:`, `feat:`, `chore:`). Pre-commit runs ruff and black and enforces this.

```bash
pip install pre-commit   # or: uv pip install pre-commit
pre-commit install
pre-commit install --hook-type commit-msg
```

## Layout

- `src/rosdep_viz/`: main package
  - `core/`: finder (package paths), parser (package.xml), tree builder
  - `api.py`: public API
  - `tui/`: Textual TUI
- `tests/`: pytest

## Web app

See **`rosdep_viz_webapp/`** for the FastAPI backend and React (Vite, Tailwind, Node 22) frontend that consume this package. The backend uses `rosdep_viz` to list packages and serve dependency trees; the frontend visualizes them with an interactive graph (React Flow).
