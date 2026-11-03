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
rostree rdeps rclcpp -w           # Skip packages that belong to the ROS distro
rostree rdeps rclcpp --json
```

### `rostree check`

Report dependency cycles and unresolved dependencies. Exits non-zero when it finds
problems, so it can gate CI.

```bash
rostree check                     # Every workspace package
rostree check nav2_bringup        # Specific roots
rostree check --ignore-system     # Don't fail on names that look like rosdep keys
rostree check --junit report.xml  # Also write a JUnit report for CI
rostree check --json
```

In CI:

```yaml
- run: rostree check --only-workspace --junit rostree.xml
```

`--ignore-system` is a guess from the name: an unresolved name with no underscore
(`eigen`, `boost`) is usually a rosdep key rather than a ROS package. But
`rclcpp`, `tf2`, `urdf` and `xacro` have no underscore either, so an unbuilt one
would be waved through too. Whatever the flag holds back is therefore always
listed — on stderr, and under `"ignored"` in `--json` — so a CI log shows what
was not checked.

### `rostree graph`

Generate dependency graphs as an interactive HTML page, or as DOT (Graphviz) or
Mermaid text. DOT can be rendered straight to PNG/SVG/PDF.

**Interactive HTML** — the one to reach for when you are actually trying to
understand something, rather than paste a picture into a document:

```bash
rostree graph nav2_bringup -f html --open   # write nav2_bringup.html and open it
rostree graph -w ~/ros2_ws -f html -o ws.html
rostree graph my_pkg -f html --only-workspace
```

The result is a **single file with nothing external in it** — no CDN, no fonts,
no network at all. Mail it, commit it, or open it on a robot with no route out.

It does not draw the whole graph at once, because a full ROS workspace drawn all
at once is a hairball nobody reads twice. Instead you are always looking at one
package's neighbourhood:

| | |
|---|---|
| **Click** a package | re-centre the graph on it |
| **Hover** | light up everything upstream and downstream of it, dim the rest |
| **Shift-click** | pin a second package and list the shortest paths between the two — `rostree why`, drawn |
| `/` | search; arrows and enter to jump |
| `d` `u` `b` | dependencies · dependents · both |
| `[` `]` | fewer or more hops |
| `f` / `r` / `t` / `?` | fit · back to start · theme · help |

Packages are coloured by where they came from, using the same palette as the
TUI, so `/opt/ros` and your own workspace are distinguishable at a glance, and
unresolved names are drawn dashed. The current view lives in the URL, so a
focused view can be shared by copying the address.

```bash
# Single package - render to image (requires Graphviz)
rostree graph rclpy --render png           # Creates rclpy.png
rostree graph rclpy --render svg --open    # Create SVG and open it
rostree graph rclpy --render pdf -o out.pdf

# Single package - text output
rostree graph rclpy                    # DOT format to stdout
rostree graph rclpy -f mermaid         # Mermaid format
rostree graph rclpy -f html -o d.html  # Interactive, self-contained
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

## Scoping what you look at

Every command that walks the dependency graph (`tree`, `graph`, `why`, `rdeps`,
`check`, `diff`) takes the same scope flags. On a sourced ROS 2 machine most of
what rostree can see belongs to the distro, so these are usually what you want:

```bash
rostree tree my_robot_bringup -w              # ignore the ROS distro's packages
rostree tree my_robot_bringup --include 'nav2_*'
rostree tree my_robot_bringup --exclude '*_msgs' --exclude 'rosidl_*'
rostree graph --only-workspace --render png   # graph just your own packages
```

- `-w` / `--only-workspace` drops the ROS distro's own packages — under `/opt/ros`,
  or wherever a source build or RoboStack env put them (see
  [Package discovery](package-discovery.md#which-prefix-is-the-distro)).
- `--include GLOB` keeps only matching package names; repeat for several globs.
- `--exclude GLOB` drops matching names. Excludes win over includes.
- Patterns are shell globs matched against the package name, and are
  case-sensitive.

A filtered-out package is **neither shown nor followed**, so anything reachable
only through it disappears too — that is what makes `--only-workspace` useful.
Because that hides real edges, every one of these commands says what was held
back: a line on stderr, and a `"filtered"` list in `--json` output.

`rdeps` is the one exception to "not followed", on purpose. It answers *what
breaks if this changes*, so it walks the full reverse graph and filters the
answer afterwards: excluding an intermediate package must not hide the dependents
behind it.

### Which dependencies to follow

```bash
rostree tree rclcpp --dep-type runtime   # depend + exec_depend  (same as -r)
rostree tree rclcpp --dep-type build     # depend + build_depend + build_export_depend
rostree tree rclcpp --dep-type test      # depend + test_depend
rostree tree rclcpp --dep-type all       # everything (the default)
```

### `rostree diff`

What did this package gain, lose or bump?

```bash
# Compare two packages
rostree diff nav2_bringup nav2_route

# Compare a package against its own past
rostree diff my_robot_bringup --save deps.json
#   ...rebuild, update, change a manifest...
rostree diff my_robot_bringup --against deps.json
```

Exits non-zero when anything moved, so it works as a drift check in CI. `--json`
gives `added` / `removed` / `changed` for scripting.


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

Everything the CLI can tell you, a script can ask for directly — the CLI is built
on these same functions. Everything exported from `rostree.api` follows semantic
versioning; anything under `rostree.core` is internal and may move.

```python
from rostree.api import (
    build_graph, build_tree, dependency_paths, dependency_versions,
    diff_dependencies, get_index, reverse_dependencies, tree_stats,
    FilterReport, PackageFilter,
)
```

### Ask the questions the CLI answers

```python
# rostree why: every shortest path from one package to another
dependency_paths("my_robot_bringup", "rcutils")
# [['my_robot_bringup', 'my_robot_control', 'rclcpp', 'statistics_msgs', 'rcutils'], ...]

# rostree rdeps --transitive: what breaks if this changes?
reverse_dependencies("my_robot_msgs", transitive=True)

# rostree diff: snapshot a package's dependency set, compare after a rebuild
before = dependency_versions(build_graph("my_robot_nav"), exclude=["my_robot_nav"])
# ... rebuild ...
after = dependency_versions(build_graph("my_robot_nav"), exclude=["my_robot_nav"])
diff = diff_dependencies(before, after)
if diff:                                   # truthy when anything moved
    print(diff.added, diff.removed, diff.changed)
```

### Build the graph yourself

```python
# The resolved DAG — linear in the number of packages, whatever the shape
graph = build_graph("nav2_bringup", dep_type="runtime")
graph.edges        # {"nav2_bringup": ["nav2_common", ...], ...}
graph.packages     # name -> PackageInfo, for every package that resolved
graph.missing      # names that resolve to no package.xml
graph.truncated    # names past max_depth: exist, but were not walked
graph.cycles()     # [["a", "b", "a"], ...]

# A renderable tree: each package expanded once, repeats marked
root = build_tree("rclpy", max_depth=5)
tree_stats(root)   # {'nodes': 770, 'packages': 164, 'repeats': 543, ...}
root.to_dict()     # the same JSON `rostree tree --json` prints
```

### Scope: the same knobs as the command line

Every function that walks the graph takes the same scope arguments:

```python
report = FilterReport()
graph = build_graph(
    "my_robot_bringup",
    dep_type="build",                                   # runtime | build | test | all
    package_filter=PackageFilter(
        include=("my_robot_*",), exclude=("*_msgs",), only_workspace=True
    ),
    report=report,                                      # what the filter removed
)
print(report.summary())  # "3 package(s) hidden by filters: ..."
```

A filtered-out package is neither returned nor followed. `reverse_dependencies`
is the one exception, as on the command line: it filters the answer, not the
walk, so excluding a package never hides the dependents behind it. An unknown
`dep_type` raises `ValueError` rather than quietly following everything.
`runtime_only=True` is the older spelling of `dep_type="runtime"` and still works.

Pass `index=get_index()` (or one you built) to reuse a single package scan across
many calls; otherwise a process-wide cached index is used.

### Render it

```python
from rostree.api import GraphView, to_dot, to_html, to_mermaid

from pathlib import Path

graph = build_graph("my_robot_bringup")
view = GraphView.from_graph(graph)
Path("deps.dot").write_text(to_dot(view), encoding="utf-8")
Path("deps.mmd").write_text(to_mermaid(view), encoding="utf-8")
# The interactive viewer. Pass the index so packages are coloured by source.
Path("deps.html").write_text(to_html(graph, index=get_index()), encoding="utf-8")
```

Write with an explicit `encoding="utf-8"`: the viewer contains characters such
as `→` that the default codec on Windows cannot encode.

### Discovery

```python
from rostree.api import (
    get_package_info, list_known_packages, list_known_packages_by_source, scan_workspaces,
)

list_known_packages()             # {name: Path to package.xml}
list_known_packages_by_source()   # {"System (/opt/ros/jazzy)": [...], "Source (...)": [...]}
get_package_info("rclpy")         # PackageInfo: name, version, dependencies, ...
scan_workspaces()                 # [WorkspaceInfo(path, has_src, has_install, packages)]

index = get_index()
index.resolve("rclcpp")           # Path to its package.xml, or None
index.get("rclcpp").kind          # SourceKind.SYSTEM
index.workspace_names()           # every package that is not the distro's
```

`scan_workspaces(roots=None, max_depth=4, include_home=True, include_opt_ros=True)`
looks in common locations (`~/*_ws`, `~/dev`, `/opt/ros/*`) unless given `roots`,
and only reports a directory that contains a package or colcon's markers.

### Deprecated

- `build_tree(include_buildtool=...)` has never had an effect —
  `buildtool_depend` entries are build tooling and are not traversed. Passing
  `True` now raises a `DeprecationWarning`; the parameter goes in 2.0.
