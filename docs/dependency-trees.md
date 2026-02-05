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

We do **not** use `buildtool_depend` (e.g. ament_cmake, ament_python) unless you enable that option; they pull in the whole build toolchain and make trees huge.

### Filtering

- Only dependencies that look like ROS package names (e.g. lowercase with underscores) are kept. System-style names (e.g. `python3-*`, `lib*`) are skipped by heuristic.
- You can restrict which tags are used via `include_tags` in `parse_package_xml()` or `runtime_only` in `build_tree()`.

Implementation: `src/rosdep_viz/core/parser.py` (`parse_package_xml`, `DEPENDENCY_TAGS`).

## Runtime-only vs full tree

- **Full tree** (default): uses all dependency tags above. Very large for packages that depend on ament_cmake, rosidl_*, etc., because the whole build/test chain is included.
- **Runtime-only** (`runtime_only=True`): only `depend` and `exec_depend`. Much smaller and faster; suitable for “what does this package need at run time?”

The TUI uses `runtime_only=True` and `max_depth=6` by default so that opening e.g. `action_msgs` stays responsive.

## Tree building

1. **find_package_path(root_package)** — locate package.xml (see [Package discovery](package-discovery.md)).
2. **parse_package_xml(path, include_tags=...)** — get name, version, description, list of dependency names.
3. For each dependency name, recurse (find path → parse → recurse).
4. **Cycle handling**: if a package is already in the current path, it is shown as “(cycle)” and we do not recurse again.
5. **max_depth**: optional limit; nodes beyond that depth are not expanded.
6. Result: a **DependencyNode** (name, version, description, path, children list).

### Node structure

```python
@dataclass
class DependencyNode:
    name: str
    version: str
    description: str
    path: str
    children: list[DependencyNode]
    package_info: PackageInfo | None  # raw parsed info
```

- **to_dict()** — serializes to a JSON-friendly dict (used by the web API).

Implementation: `src/rosdep_viz/core/tree.py` (`build_dependency_tree`, `DependencyNode`).

## API

- **build_tree(root_package, max_depth=None, include_buildtool=False, runtime_only=False)**  
  Returns the root `DependencyNode` or `None` if the package is not found.
- **get_package_info(package_name)**  
  Returns parsed metadata and dependency list for one package (no recursion).

See [Usage](usage.md) for examples.
