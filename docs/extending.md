# Build on rostree

rostree is a library first. The CLI, the TUI and the HTML viewer are all built on
the same public API, so anything `rostree` can tell you on the command line, your
own tool can ask for directly — no parsing of terminal output.

This page shows how the pieces fit, then four complete programs built on them.
The programs live in
[`examples/`](https://github.com/guilyx/rostree/tree/main/examples) and the test
suite runs every one of them against a generated workspace, so the code below is
the code that is known to work.

---

## How the pieces fit

```mermaid
graph LR
    env[(AMENT_PREFIX_PATH,<br/>workspace src/)] --> index[PackageIndex<br/><small>core/index.py</small>]
    index --> parser[parse_package_xml<br/><small>core/parser.py</small>]
    parser --> graph[DependencyGraph<br/><small>build_graph</small>]
    parser --> tree[DependencyNode<br/><small>build_tree</small>]
    graph --> analysis[why · rdeps · diff<br/><small>core/analysis.py</small>]
    graph --> render[DOT · Mermaid · HTML<br/><small>core/graph.py, core/webview.py</small>]
    tree --> cli[CLI and TUI]
    analysis --> cli
    render --> cli
    analysis --> you[your tool]
    render --> you
    graph --> you
```

| Layer | What it gives you | Entry points |
|---|---|---|
| **Index** | Every package visible to the environment, found once, looked up by name in constant time | `get_index()`, `PackageIndex` |
| **Parser** | One `package.xml`, with REP 149 conditions evaluated and the result cached | `get_package_info()`, `PackageInfo` |
| **Graph** | Everything reachable from some roots: edges, versions, what is missing, what was past the depth limit | `build_graph()`, `DependencyGraph` |
| **Tree** | The same, as a printable tree with repeats collapsed | `build_tree()`, `DependencyNode` |
| **Analysis** | The questions: why, who depends on this, what changed | `dependency_paths()`, `reverse_dependencies()`, `diff_dependencies()` |
| **Render** | Text and pictures | `to_dot()`, `to_mermaid()`, `to_html()` |

Everything above is importable from `rostree.api` and covered by semantic
versioning. The [usage guide](usage.md#python-api) lists every function and its
arguments; [How the algorithms work](algorithms.md) explains what each one does
underneath.

Two habits make a tool built on rostree fast and correct:

- **Build the index once and pass it around** (`index=get_index()`). Every
  function accepts one, and each lookup afterwards is a dictionary access instead
  of a filesystem scan.
- **Use the same scope arguments as the CLI** — `dep_type`, `package_filter`,
  `report` — so your tool and `rostree` give the same answer for the same
  question, and so a filter never shrinks a result without your code knowing.

---

## Recipe: an architecture rule for CI

Some dependencies are design mistakes: a sensor driver should not reach into
navigation, a message package should not depend on a node. This checks a rule
across the whole workspace and, when it fails, prints the **shortest chain** that
breaks it — so the failure says where to cut, not just that a rule was broken.

```python title="examples/forbidden_dependencies.py"
--8<-- "examples/forbidden_dependencies.py"
```

```text
$ python examples/forbidden_dependencies.py 'my_robot_driver_*' 'nav2_*'
forbidden: my_robot_driver_cam -> nav2_core
```

---

## Recipe: where does a change ripple furthest?

Rank your packages by how many others depend on them, directly and through any
chain. The top of the list is where a breaking change costs the most.

```python title="examples/ripple_report.py"
--8<-- "examples/ripple_report.py"
```

```text
$ python examples/ripple_report.py 3
package                           direct  transitive
my_robot_msgs                          1           4
my_robot_utils                         2           3
my_robot_driver_cam                    1           1
```

The distro's own packages are never ranked: `workspace_names()` leaves them out,
wherever the distro is installed.

---

## Recipe: make dependency changes visible in review

Commit a lock of a package's dependency set next to the code. A pull request that
adds, drops or bumps a dependency then has to update the lock in the same diff,
where a reviewer sees it.

```python title="examples/drift_gate.py"
--8<-- "examples/drift_gate.py"
```

```text
$ python examples/drift_gate.py my_robot_bringup deps.lock.json
+ my_robot_extra 1.0.0
dependencies of my_robot_bringup changed; rerun with --update if that is intended
```

`rostree diff --save` / `--against` does the same from the command line, and also
records the scope the snapshot was taken under.

---

## Recipe: a format rostree does not ship

`build_graph` returns plain data, so any output format is a loop away. This one
writes CSV; the same shape produces PlantUML, a database import, or the input of
another analysis.

```python title="examples/export_edges.py"
--8<-- "examples/export_edges.py"
```

---

## Adding to rostree itself

New ideas usually start as one of the scripts above. When one is useful enough to
belong in the tool:

- **Analysis** goes in `core/analysis.py` as a pure function — no printing, no
  `sys.exit`, no environment reads — and is exported from `rostree.api`.
- **A CLI command** is then a thin `cmd_*` function in `cli.py` that parses
  arguments, calls the analysis, and formats the result. It should accept the
  shared scope flags (`_add_runtime_arg`, `_add_filter_args`) and report what a
  filter removed.
- **Tests** for the analysis use small generated graphs; for the command, drive
  `main([...])` end to end, so the argument wiring is tested too.

See [Development](development.md) for setup, and the contributing guide in the
repository for how changes are proposed and reviewed.
