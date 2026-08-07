# Dependency trees

## package.xml parsing

The parser reads **only** package.xml files. It does not use rosdep or any external database.

### Dependency tags

From package.xml we collect dependencies from these tags (when not using runtime-only mode):

| Tag | Meaning |
|-----|--------|
| `depend` | Needed at build and run time |
| `exec_depend` | Needed at run time only |
| `build_depend` | Needed at build time only |
| `build_export_depend` | Needed by downstream when building against this package |
| `test_depend` | Needed for tests |

We do **not** traverse `buildtool_depend` (e.g. ament_cmake, ament_python); they pull
in the whole build toolchain and make trees huge without saying much about the package.

### ROS packages vs rosdep keys

A `<depend>` entry can name either a ROS package or a rosdep key for a system
package. ROS 2 package names are restricted to lowercase letters, digits and
underscores, so anything containing a dash (`libboost-dev`, `python3-numpy`,
`ros-humble-rclcpp`) is a rosdep key. Those are kept separately on
`PackageInfo.system_dependencies` rather than discarded.

A `lib` prefix means nothing on its own: `libstatistics_collector`,
`libyaml_vendor` and `libcurl_vendor` are genuine ROS 2 packages. Whether a name
is really a package is decided by the package index — if a `package.xml` is found,
it is a package — not by guessing from the name.

Implementation: `src/rostree/core/parser.py`.

## Package index

Resolving a name used to mean walking the filesystem again for every node in a
tree, so a deep tree spent most of its time in `os.walk`. `rostree.core.index`
scans each install prefix and source tree **once** and answers lookups from memory:

```python
from rostree.api import get_index

index = get_index()          # cached per process, per environment
index.resolve("rclcpp")      # -> Path to package.xml, or None
index.by_label()             # -> {"System (/opt/ros/jazzy)": [...], ...}
index.reverse_dependencies() # -> {"rcutils": {"rclcpp", "rcl", ...}, ...}
```

Install prefixes win over source trees, and earlier prefixes win over later ones —
the same order the ROS 2 environment itself resolves packages. Source scans skip
`build/`, `install/`, `log/`, VCS metadata and anything marked `COLCON_IGNORE` or
`AMENT_IGNORE`, and stop descending once a manifest is found.

Parsed manifests are memoized by path, modification time and size, so the same
`package.xml` is never parsed twice within a run.

## Repeats: why trees stay small

A ROS dependency graph is a **DAG, not a tree**. `rcutils` sits underneath almost
every branch of `rclcpp`, so expanding every distinct path separately is
exponential: a 198-package install space produced 57,193 nodes at depth 7, and
never finished at unlimited depth.

rostree walks the graph breadth-first first, records the shallowest depth at which
each package appears, then materialises the tree so that **each package is
expanded exactly once — where it first appears**. Every later occurrence becomes a
one-line reference:

```
bringup 1.3.0
├── nav2_core 1.3.0
│   ├── rclcpp 28.1.5
│   │   └── rcutils 6.7.2
│   └── ↩ 3 already shown above: tf2, geometry_msgs, nav_msgs
└── rclcpp 28.1.5  ↩ see above
```

This is the same convention `cargo tree` uses with `(*)`. It makes the output
proportional to the graph (nodes + edges) instead of to its path count, which is
what makes unlimited-depth trees instant. Nothing is hidden: every edge is still
shown, once.

Pass `collapse_repeats=False` (`--full` on the CLI) for a fully expanded tree, and
`--max-nodes N` to bound it.

## Node structure

```python
@dataclass
class DependencyNode:
    name: str
    version: str
    description: str
    path: str
    children: list[DependencyNode]
    package_info: PackageInfo | None   # raw parsed info
    status: NodeStatus                 # why this node looks the way it does
```

`NodeStatus` replaces the old practice of writing markers such as `"(not found)"`
into `description`:

| Status | Meaning |
|--------|---------|
| `ok` | A resolved, fully expanded package |
| `repeat` | Already expanded elsewhere in this tree; children omitted |
| `cycle` | Depends, directly or transitively, on one of its own ancestors |
| `missing` | No package.xml on the search path (rosdep key, or not built yet) |
| `parse_error` | Manifest found but unreadable |
| `truncated` | Cut off by `max_depth`; the real subtree continues below |

`node.is_error` and `node.is_placeholder` cover the common checks, and `to_dict()`
includes `status` for JSON consumers.

## Graphs

For anything that does not need tree shape — image graphs, metrics, cycle checks —
use the graph builder directly. It is a single breadth-first pass, linear in the
number of reachable packages:

```python
from rostree.api import build_graph

graph = build_graph("nav2_bringup", runtime_only=True)
graph.packages      # name -> PackageInfo, one entry per package
graph.edges         # name -> list of direct dependencies
graph.missing       # dependency names that resolved to nothing
graph.depths        # name -> shortest distance from a root
graph.cycles()      # [["a", "b", "c", "a"], ...]
graph.edge_pairs()  # {("parent", "child"), ...}
```

Unresolved dependencies stay in the graph. `rostree graph` draws them dashed and
grey rather than deleting the edge — dropping them is what used to turn a
workspace graph into a field of unconnected boxes.

## Runtime-only vs full tree

- **Full tree** (default): all dependency tags above. Larger, because build and
  test chains are included.
- **Runtime-only** (`runtime_only=True`, `-r` on the CLI): only `depend` and
  `exec_depend` — "what does this package need at run time?"

The TUI follows runtime dependencies by default; press `t` to switch.

## API

- **`build_tree(root_package, max_depth=None, runtime_only=False, collapse_repeats=True, extra_source_roots=None)`**
  Returns the root `DependencyNode`, or `None` if the package is not found.
- **`build_graph(root_packages, max_depth=None, runtime_only=False)`**
  Returns a `DependencyGraph` for one or more roots.
- **`tree_stats(node)`** — node count, distinct packages, depth, repeats, cycles, unresolved.
- **`reverse_dependencies(package)`** — packages that depend on this one.
- **`get_package_info(package_name)`** — parsed metadata for one package, no recursion.

See [Usage](usage.md) for examples.
