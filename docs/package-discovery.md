# Package discovery

rosdep_viz finds ROS 2 packages **only** from environment variables. It does **not** hardcode `/opt/ros/...` or any path. Whatever you have sourced in the current shell is what it sees.

## Install space (where packages are “installed”)

Packages are found under **prefix paths** listed in:

1. **`AMENT_PREFIX_PATH`** — Set by ROS 2 and colcon (e.g. when you `source /opt/ros/<distro>/setup.bash` or `source install/setup.bash`).
2. **`COLCON_PREFIX_PATH`** — Set by colcon when building a workspace.

Each entry is a **prefix** (e.g. `/opt/ros/humble` or a path under a workspace `install/`). For a given package name, the finder looks for:

```
{prefix}/share/{package_name}/package.xml
```

### Default ROS 2 install

When you run:

```bash
source /opt/ros/<distro>/setup.bash
```

that script sets `AMENT_PREFIX_PATH` (and related vars) to `/opt/ros/<distro>`. The finder then sees all packages from that install (e.g. `rclcpp`, `std_msgs`, `action_msgs`) under `/opt/ros/<distro>/share/<pkg>/package.xml`.

### Your workspace

When you run:

```bash
source /path/to/workspace/install/setup.bash
```

colcon adds your workspace’s install prefixes to `AMENT_PREFIX_PATH` and/or `COLCON_PREFIX_PATH`. The finder then also sees every package installed in that workspace the same way: under `.../install/<pkg>/share/<pkg>/package.xml`.

So “search through the sourced workspace” is correct: it searches through **whatever prefixes are currently in those two variables**.

## Source space (unbuilt / source code)

When a package is not in the install space but its source is on disk, the finder can search **source trees**. Source roots are derived in two ways:

### 1. Inferred from install prefixes

For each prefix in `AMENT_PREFIX_PATH` or `COLCON_PREFIX_PATH`, if the prefix looks like it lives under a workspace **install** directory (i.e. its parent directory is named `install`), the finder also considers the workspace **src** directory:

- Prefix example: `/home/you/ros_ws/install/some_pkg`
- Parent: `/home/you/ros_ws/install`
- Inferred source root: `/home/you/ros_ws/src`

So for a workspace you built and sourced, both its **install** and **src** are used: install via the prefix, source via this rule.

### 2. Explicit workspace environment variables

To include **other** workspaces (that you did not necessarily source), you can set:

- **`COLCON_WORKSPACE`** — One path, or several paths separated by `:` (colon).
- **`ROS2_WORKSPACE`** — Same idea.

For each path:

- If `{path}/src` exists, the finder scans `{path}/src`.
- Otherwise it scans `{path}`.

The finder then **walks** that directory tree and looks for any `package.xml` whose `<name>` matches the requested package (or, when listing all packages, collects all `<name>` values).

### Example: other workspace without sourcing

```bash
export COLCON_WORKSPACE=/path/to/other_ws
rosdep_viz
```

The finder will scan `/path/to/other_ws/src` (or `/path/to/other_ws` if `src` does not exist) for package.xml files and include those packages.

## Search order

1. **find_package_path(name)**  
   - Look in each prefix from `AMENT_PREFIX_PATH` and `COLCON_PREFIX_PATH` for `share/{name}/package.xml`.  
   - If not found, search each inferred or explicit source root for a directory containing a package.xml with `<name>{name}</name>`.  
   - Returns the first match (install space is checked before source space).

2. **list_package_paths()**  
   - Collect all packages from install prefixes (each `share/<dir>/package.xml`).  
   - Then walk each source root and add any package name not already in the result (source does not override install).

## Summary

| What you do | What the finder uses |
|-------------|----------------------|
| `source /opt/ros/<distro>/setup.bash` | `AMENT_PREFIX_PATH` → install under `/opt/ros/...` |
| `source /path/to/workspace/install/setup.bash` | Same env; adds that workspace’s install and infers `workspace/src` |
| Set `COLCON_WORKSPACE=/path/to/other_ws` or `ROS2_WORKSPACE` | Scans `other_ws/src` (or the given path) for package.xml files |

Implementation: `src/rosdep_viz/core/finder.py` (`find_package_path`, `list_package_paths`).
