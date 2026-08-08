# rostree Roadmap

Last reviewed after **v0.3.0** shipped. The original roadmap came out of
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

## v0.4.0 — make it pleasant on a real workspace *(in progress)*

The theme is **scoping**. On a sourced ROS 2 machine most of what rostree prints
belongs to the distro, not to you, and there is currently no way to say so.

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

### 4.3 CI integration — *partly shipped*
- [x] `rostree check --junit FILE` for CI dashboards
- [ ] A composite GitHub Action wrapping `rostree check`
- [x] Document the pattern in `docs/usage.md`

### 4.4 Configuration file
- [ ] `[tool.rostree]` in `pyproject.toml` and `.rostreerc` (TOML)
- [ ] Defaults for depth, dependency scope and filters
- [ ] CLI arguments always override the file

### 4.5 Errors and diagnostics
- [ ] `rostree.exceptions` with `PackageNotFoundError`, `ManifestError`
- [ ] Optional logging behind `--debug`

---

## Later: v0.5.0 — confidence

### 5.1 Integration tests against real ROS 2
- [ ] Run the suite in a `ros:jazzy` container in CI
- [ ] Assert against real packages (`rclcpp`, `nav2_bringup`) rather than fixtures
- [ ] A benchmark test that fails if tree building goes superlinear again

The highest-confidence item on the list: the `<ws>/install/src` bug lived in the
code for every release so far, and no fixture-based test could have caught it.

### 5.2 SBOM export
- [ ] CycloneDX output for a package or a whole workspace
- [ ] Include unresolved rosdep keys as external references

### 5.3 Split the CLI module
- [ ] `cli.py` is ~1,200 lines; split into `cli/commands/*.py`
- [ ] Keep `rostree.cli` re-exporting the current names — a lot of tests and
      downstream code import from it

Deliberately last: pure churn with no user-visible benefit, so it should follow
the features rather than block them.

### 5.4 Distribution
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
