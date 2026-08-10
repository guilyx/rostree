# rostree Roadmap

Last reviewed at **1.0**. The original roadmap came out of
[the code review](./review.md); this version records what shipped, what was
dropped and why, and what is worth doing next.

---

## Shipped in v0.3.0

**Phase 1 (critical fixes) is done**, plus the headline problem that was not on
the original list.

Dependency tree building was **exponential**: a DAG was expanded once per path, so
a 159-package workspace printed 68,081 lines at depth 7 and never finished at the
CLI's default depth. Each package is now expanded once, where the tree first prints
it (see [dependency-trees.md](dependency-trees.md#repeats-why-trees-stay-small)),
which took an unlimited-depth tree from "never finishes" to 0.02 s.

| Item | Outcome |
|------|---------|
| Graph edges to unresolved packages | Kept, drawn dashed; `--hide-missing` to drop them |
| Package discovery caching | Shipped as a one-pass `PackageIndex`, cached per process and per environment with explicit `refresh=True` — not a TTL cache; a full scan costs milliseconds, so disk persistence was unnecessary |
| `parse_package_xml` caching | Memoized by path, mtime and size |
| O(n²) visited-set copying | Gone with the rewrite |
| Duplicated XML name parsing | Single `quick_package_name()` helper |
| Progress callbacks | `on_progress` on tree, graph and index building |
| `NodeStatus` enum, `is_error` | Shipped |
| DOT / Mermaid generation split out | `core/graph.py` |
| Reverse dependency lookup | `rostree rdeps`, plus the TUI's `v` view |
| `rostree check` for CI | Cycles + unresolved deps, non-zero exit |
| JSON output | `--json` on every command |

Bugs found along the way and fixed: unbuilt `src/` packages were invisible (the
source root was computed as `<ws>/install/src`), `lib*` packages were discarded,
text trees drew every child as `├──`, and `graph -w` did not work on an unsourced
workspace.

### Dropped, with reasons

- **`ros2 pkg xml` fallback** (was 1.2). The index already scans every prefix and
  source root, so it finds everything the fallback could, and shelling out per
  package would be far slower. Unresolved names are now surfaced honestly instead
  of hidden.
- **`ErrorNode` dataclass / discriminated union** (was 2.1). `NodeStatus` covers it.
  A separate type would break the uniform `children` / `walk()` API for callers.
- **Web-based interactive viewer** (was 4.2). Large surface area that duplicates
  what the TUI already does; the repo has been down the webapp road once already.
- **`--profile` flag** (was 4.4). It existed to diagnose the slowness that is now
  gone. If performance regresses, a benchmark test is the better tool.
- **`requirements.txt` generation** (was 3.4). ROS dependencies are rosdep keys and
  ament packages, not pip distributions; the output would be misleading.
- **CSV export** (was 3.4). `--json` piped through `jq` covers this.

---

## Shipped in v0.4.0

The theme was **scoping**. On a sourced ROS 2 machine most of what rostree prints
belongs to the distro, not to you, and there was no way to say so.

4.1 and 4.2 shipped whole; 4.3 shipped except the composite Action. The
configuration file and the `rostree.exceptions` work did not start and moved on
rather than being left here looking like part of a finished release.

### 4.1 Scope and filtering — ✅ shipped
- [x] `--only-workspace` — exclude packages installed under `/opt/ros`
- [x] `--exclude PATTERN` (repeatable) — drop packages by glob
- [x] `--include PATTERN` — restrict to packages matching a glob
- [x] `--dep-type runtime|build|test|all`, keeping `-r` as an alias
- [x] Apply consistently across `tree`, `graph`, `why`, `rdeps` and `check`
- [x] Report what a filter removed, so the tree never silently lies

### 4.2 `rostree diff` — ✅ shipped
- [x] `rostree diff <pkg_a> <pkg_b>` — compare two packages' dependency sets
- [x] `rostree diff --save FILE` / `--against FILE` — capture now, compare after a rebuild
- [x] Report added / removed / version-changed, and exit non-zero on drift

### 4.3 CI integration — ✅ mostly shipped
- [x] `rostree check --junit FILE` for CI dashboards
- [x] Document the pattern in `docs/usage.md`
- [ ] A composite GitHub Action wrapping `rostree check` — carried to v0.5.0

### 4.4 Static analysis, unplanned
Not on the original list. Codacy reported 75 issues against the v0.4.0 branch and
settling them turned up two things worth fixing rather than silencing, so the
work is recorded here:
- [x] `core/parser.py` parses with defusedxml — a manifest declaring entities is
      refused instead of expanding until memory runs out
- [x] The TUI's `query_one` guards narrowed from bare `Exception` to
      `QueryError`/`ScreenStackError`, so bugs inside them stop disappearing
- [x] Bandit in CI, pre-commit and the `dev` extra, so the gate is reproducible
      locally instead of living only in a dashboard

---

## Shipped in v1.0.0

`rostree graph -f html` — the graph in a browser, as one self-contained file.
Not on any earlier list; it came out of asking what a dependency viewer would
have to do for someone to open it twice.

- [x] A layered DAG layout computed in the page, so dependencies read in their
      actual direction instead of settling into a force-directed blob
- [x] Focus-first: click to re-centre, hover to trace, shift-click to pin a
      second package and list the shortest paths between the two
- [x] Search, direction and depth controls, source colouring matching the TUI,
      and the view encoded in the URL so it can be shared
- [x] No CDN, no fonts, no network — it opens from `file://` on a robot
- [x] Demo reel and README rebuilt around the current feature set, with the
      before/after timings re-measured rather than carried over

**1.0 is a statement about the interface, not about coverage.** The CLI flags and
`rostree.api` are now under semver. What has *not* changed is that every test runs
on generated fixtures — which is why 5.1 below is the top item and not a
nice-to-have.

---

## Next: v1.1 — confidence

### 1.1.0 Carried over
- [ ] A composite GitHub Action wrapping `rostree check`
- [ ] Configuration file: `[tool.rostree]` in `pyproject.toml` and `.rostreerc`
      (TOML), defaults for depth, dependency scope and filters, CLI arguments
      always overriding the file
- [ ] `rostree.exceptions` with `PackageNotFoundError`, `ManifestError`, and
      optional logging behind `--debug`

### 1.1.1 Integration tests against real ROS 2 — **the top item**
- [ ] Run the suite in a `ros:jazzy` container in CI
- [ ] Assert against real packages (`rclcpp`, `nav2_bringup`) rather than fixtures
- [ ] Cover both colcon layouts, merged and isolated, on a real install
- [ ] A benchmark test that fails if tree building goes superlinear again

Everything rostree knows about how a ROS 2 workspace is laid out is currently
asserted against workspaces rostree itself generated. The `<ws>/install/src` bug
shipped in every release up to 0.3.0 for exactly that reason, and nothing in the
suite would catch the next one of its kind. Shipping 1.0 raises the cost of that
gap rather than lowering it.

### 1.1.2 SBOM export
- [ ] CycloneDX output for a package or a whole workspace
- [ ] Include unresolved rosdep keys as external references

### 1.1.3 Split the CLI module
- [x] `core/junit.py` — carved out in v0.4.0 because the security scanners needed
      one place to be told the JUnit writer only ever *writes* XML
- [ ] `cli.py` is still ~1,470 lines; split the rest into `cli/commands/*.py`
- [ ] Keep `rostree.cli` re-exporting the current names — a lot of tests and
      downstream code import from it

Deliberately late: mostly churn with no user-visible benefit, so it should follow
the features rather than block them. The one piece done so far was pulled out for
a concrete reason, which is the bar the rest should meet too.

### 1.1.4 Distribution
- [ ] Publish to the ROS 2 package index
- [ ] conda-forge package

---

## Quick wins

- [ ] `--quiet` to suppress the summary line
- [ ] Shell completion (`argcomplete`) for package names
- [ ] Colour-blind-safe palette option

---

## Contributing

See [development.md](./development.md) for setup.

When picking up a roadmap item:
1. Create an issue referencing this roadmap
2. Create a feature branch
3. Add tests for new functionality
4. Update documentation and `CHANGELOG.md`
5. Submit a PR referencing the issue

---

## Feedback

This roadmap is a living document. Open an issue to suggest features,
reprioritize, or report blockers.
