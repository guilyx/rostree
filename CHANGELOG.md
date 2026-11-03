# Changelog

All notable changes to this project are documented in this file, and rostree
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

From 1.1.0 on, each release's entry is written by
[release-please](https://github.com/googleapis/release-please) from the
[Conventional Commits](https://www.conventionalcommits.org/) titles of the pull
requests it contains, and the version bump follows from them — see
[Releases](https://github.com/guilyx/rostree/blob/main/CONTRIBUTING.md#releases).
Entries up to 1.0.0, and the longer notes on 1.1.0 below, were written by hand in
the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## 1.1.0 in detail

release-please writes the summary of 1.1.0 above this section when it cuts the
release. What follows is the same release explained for someone using rostree.

### Added
- The `docs/` folder is now published as a documentation site at
  <https://guilyx.github.io/rostree>, built with MkDocs and Material and deployed
  by a `docs.yml` workflow on every push to `main`. The build runs with
  `--strict` and with anchor validation on, so a dead link or a heading that was
  renamed out from under a `#section` link fails CI instead of shipping. Pull
  requests that touch the docs get the build as a check but do not deploy.
- `docs/changelog.md` embeds this file rather than restating it, so the changelog
  is still written in exactly one place.
- **Documentation for people who want to build on rostree, or learn from it.**
  - *The algorithms* explains the eight algorithms rostree is made of — expand
    once, breadth-first resolution with a depth frontier, all shortest paths,
    reverse dependencies, three-colour cycle detection, layered graph layout and
    REP 149 condition evaluation — each from the question it answers, through
    why the obvious approach fails, to the code and a command that shows it.
  - *Build on rostree* shows the library's layers and four complete programs in
    a new `examples/` folder: an architecture rule for CI that prints the chain
    that breaks it, a ripple report, a dependency lock for code review and a CSV
    export. The test suite runs each one, so the docs cannot drift from the code.
  - *rostree and other tools* says what `colcon graph`, `colcon list`,
    `ros2 pkg`, `rosdep` and `rqt_dep` do, and what rostree adds.
  - *Publication* records the intent to publish rostree as a software paper:
    candidate venues, what the paper would describe, and what has to happen
    first.
- `CITATION.cff` and `codemeta.json`, so GitHub's "Cite this repository" and
  archives such as Zenodo can cite a specific version.
- **Ready for outside contributors**: `CONTRIBUTING.md` (setup, what CI runs,
  where a change goes, the compatibility promise), a Code of Conduct (Contributor
  Covenant 2.1), `SECURITY.md` (private reporting, and what rostree does and does
  not trust), issue forms for bugs, feature requests and *workspace reports* —
  how rostree did on a real workspace — and a pull request template.
- `pyproject.toml` lists the documentation, issue tracker and changelog, so PyPI
  links to them from the next release.

- **rostree is now a library you can build on, not just a CLI.** `why`,
  transitive `rdeps` and `diff` lived inside the CLI, interleaved with printing,
  so another tool could only get at them by shelling out and parsing terminal
  output. They are now plain functions in `rostree.core.analysis`, the CLI calls
  them like anyone else, and `rostree.api` exposes them:
  - `dependency_paths(package, dependency)` — `rostree why`
  - `reverse_dependencies(package, transitive=True)` — `rostree rdeps -t`
  - `dependency_versions(graph)` and `diff_dependencies(before, after)` — the
    pieces of `rostree diff`, returning a `DependencyDiff` that is truthy when
    anything moved
  - `to_dot`, `to_mermaid`, `to_html` and `GraphView`, to render a graph yourself
- **Every API function that walks the graph takes the CLI's scope arguments**:
  `dep_type` (`runtime`, `build`, `test`, `all`), `package_filter` (a
  `PackageFilter`), `report` (a `FilterReport`) and `index`. All additive and
  keyword-only; `runtime_only=True` keeps working. An unknown `dep_type` raises
  `ValueError` rather than quietly following everything.
- `rostree tree --json` includes `hidden_children` on nodes cut off by a depth
  limit or node budget — the "… N more" the text output already showed. Other
  nodes keep their exact shape.
- `rostree diff --save` records the scope it was taken with (`--dep-type`,
  `--depth`, filters), and `--against` warns when the comparison runs under a
  different one, since the difference in scope would otherwise read as drift.
  Snapshots written by 1.0 are still accepted.

### Changed
- **Releases are automated.** Every pull request is squash-merged as one
  Conventional Commit, and release-please keeps a release pull request open that
  bumps the version accordingly — `fix:` a patch, `feat:` a minor version, `!` a
  major one — and writes this changelog. Merging it tags the release, creates the
  GitHub release and publishes to PyPI. A check rejects pull request titles that
  are not Conventional Commits, since the title is what decides the bump.
- Pre-commit runs ruff, black and bandit from the `dev` extra — the versions CI
  pins — instead of its own copies, which had drifted (ruff 0.8 locally, 0.16 in
  CI). It now checks `examples/` too, and accepts the `ci:`, `perf:`, `build:`
  and `revert:` commit types.
- The demo reel was re-shot as a live session rather than a reconstruction.
  A `bash` session runs in a pty, commands are typed into it a character at a
  time, and every byte it writes back is recorded with a timestamp; playback
  feeds that stream to a VT emulator and photographs the screen at 30 fps. The
  typing cadence, the pause while the index is built and the scroll are the ones
  that happened. The TUI is driven with real key presses in the same pty, and the
  graph is Chromium driving the real `graph.html`. It covers `scan`, scope
  filters, `why`, `rdeps`, `check`, `diff`, the TUI and the browser graph, with
  the before/after timings re-measured against 0.2.2 from PyPI on the same
  workspace —
  [`docs/media/README.md`](https://github.com/guilyx/rostree/blob/main/docs/media/README.md)
  records what is a real capture and what is a synthetic workspace. The same
  footage is composed twice: `rostree-demo.mp4` at 1920×1080 and
  `rostree-demo-square.mp4` at 1080×1080, for feeds that give a square post more
  room.

- `build_tree(include_buildtool=True)` raises a `DeprecationWarning`. The
  parameter has never had an effect — `buildtool_depend` entries are not
  traversed — but its docstring said otherwise. It goes in 2.0.
- `rostree rdeps --transitive` no longer lists the package itself when a cycle
  leads back to it.
- The package.xml parse cache keeps one entry per manifest instead of one per
  version of it, so a long TUI session that rescans after edits no longer grows
  without bound.

### Fixed

These came out of a full code review. Each one has a regression test that fails
on 1.0.0.

- **Conditional dependencies are honoured** ([REP 149](https://ros.org/reps/rep-0149.html)).
  `<depend condition="$ROS_VERSION == 1">roscpp</depend>` was collected on a
  ROS 2 machine, where `roscpp` never resolves — so `rostree check` failed CI for
  every package that also supports ROS 1. Conditions are now evaluated the way
  catkin_pkg, colcon and ament do, without ever `eval`-ing manifest text, and a
  condition rostree cannot parse keeps its dependency rather than dropping it.
- **Dependency tags nested inside `<export>` are no longer collected.** Only
  direct children of `<package>` are dependencies.
- **The ROS distro is recognised wherever it is installed.** It used to be
  "anything whose path contains `/opt/ros`", which got both directions wrong:
  `~/opt/ros2_overlay` was treated as the distro (so `--only-workspace` hid your
  own packages), and a distro built from source, installed with RoboStack into a
  conda env, or on Windows was treated as *your workspace* (so `--only-workspace`
  hid nothing and `rostree check` checked the entire distro). A prefix is now the
  distro if it is under `/opt/ros` by path components, or provides
  `ros_environment`. An isolated source build is grouped as one source.
- **The HTML graph no longer calls depth-limited packages "Unresolved".** With
  `--depth`, every package one hop past the limit was drawn dashed, labelled
  unresolved and counted as missing, though it resolved fine. They now show as
  what they are, with a note that they were not expanded; the header counts them
  separately. `DependencyGraph.truncated` records them for library users.
- **`rostree scan` no longer reports any folder with a `src/` as a ROS
  workspace.** It needs a package, or the `COLCON_IGNORE` markers colcon leaves in
  the `build/`, `install/` and `log/` it creates — which a React or Gradle
  project's `build/` never has. It also stops descending into `node_modules`,
  virtualenvs and build output.
- **A package description can no longer break the HTML graph.** The template's
  placeholders were filled by chained `.replace()` calls, each rescanning what the
  last inserted, so a description containing `/*{{SCRIPT}}*/` pasted the whole
  viewer into the middle of the JSON and the page rendered nothing.
- **`graph.js` is a text file again.** Three literal NUL bytes, used as a key
  separator, made git store it as binary — so no change to the viewer's 880 lines
  of JavaScript has ever shown up in a diff. They are now `\u0000` escapes, which
  are identical at runtime, and a test keeps them out.

- **`rostree --no-color <command>` works.** The flag was accepted before the
  subcommand and then silently reset by it — argparse copies a subparser's
  defaults over the values the main parser already set — so only
  `rostree <command> --no-color` ever turned colour off.
- **Every filtering command says what it filtered.** `tree` and `why` printed a
  "hidden by filters" line; `graph`, `check`, `rdeps` and `diff` filtered
  silently, which is exactly what the 0.4.0 notes said would never happen. They
  all report it now, on stderr and as a `"filtered"` list in `--json`.
- **`check --ignore-system` lists what it held back.** It decides a name is a
  rosdep key by the absence of an underscore, which also waves through an unbuilt
  `rclcpp`, `tf2` or `urdf`. A CI gate cannot guess silently, so the held-back
  names are printed and reported under `"ignored"` in `--json`.
- **`why` names the scope it searched.** A miss under `--dep-type build` or
  `test` was reported as "(runtime dependencies only)"; it now names the actual
  dependency type, and the depth limit when one was set.
- **A workspace-wide `graph` uses the right roots.** It ignored `--include` and
  `--exclude` when choosing which packages to start from, dropped any workspace
  whose path contained the word "System", and built a second package index that
  knew nothing of `-s` paths — so `rostree graph -s path/` without a package
  found nothing to graph.
- **TUI: `r` rescans with a tree open,** instead of rebuilding from the index it
  already had, so packages added since startup no longer show as "not found";
  and toggling scope while a tree is still building now rebuilds it, instead of
  leaving the header describing one scope over a tree of the other.
- Graph and snapshot files, and DOT piped to Graphviz, are read and written as
  UTF-8 explicitly rather than in the locale's encoding.

## [1.0.0] - 2026-08-10

The interface has been through three releases of hard changes — trees stopped
being exponential in 0.3.0, scope filters and `diff` arrived in 0.4.0, and the
graph moved into the browser here. It has settled, so this marks it.

**What 1.0 commits to.** The CLI commands and their flags, and the names exported
from `rostree.api`, follow semantic versioning from here: they will not change
incompatibly without a 2.0.

```python
from rostree.api import (
    build_tree, build_graph, get_index, tree_stats, reverse_dependencies,
    list_known_packages, list_known_packages_by_source, get_package_info,
    scan_workspaces,
    DependencyGraph, DependencyNode, NodeStatus,
    PackageEntry, PackageIndex, PackageInfo, SourceKind, WorkspaceInfo,
)
```

Anything under `rostree.core` is internal and may move. `rdeps --workspace-only`
stays as an accepted spelling of `--only-workspace`.

**What it does not commit to.** The exact text and layout rostree prints. Output
is for people; pin `--json` if you are parsing it.

A [launch reel](https://github.com/guilyx/rostree/blob/main/docs/media/rostree-1.0.mp4) goes with the release. Like the
evergreen one it is all real capture — actual command output, the TUI in a pty,
the graph page screen-recorded — and it ends on the same caveat below rather than
on a claim.

**What is still missing**, stated plainly rather than left for you to discover:
the suite has never run against a real ROS 2 installation. Every test uses
generated fixtures, and the `<ws>/install/src` bug fixed in 0.3.0 had shipped in
every release before it precisely because no fixture could catch it. Running
against a `ros:jazzy` container is the top item on the roadmap, and until it is
done, 1.0 means "the interface is settled", not "every layout in the wild is
covered".

### Added

- **`rostree graph -f html`** — an interactive dependency graph in a single
  self-contained file. No CDN, no fonts, no network of any kind, so it works
  attached to a bug report, committed next to a design doc, or opened on a robot
  with no route out.

  It never draws the whole graph at once, because a workspace drawn all at once
  is a hairball nobody reads twice. You are always looking at one package's
  neighbourhood: click to re-centre, hover to light up everything upstream and
  downstream of a package, shift-click to pin a second one and list the shortest
  paths between them — `rostree why`, drawn. `/` searches, `d`/`u`/`b` switch
  between dependencies, dependents and both, `[`/`]` change the depth. Packages
  are coloured by source using the TUI's palette, unresolved names are dashed,
  and the current view lives in the URL so it can be shared by copying the
  address.

  Layout is a layered DAG built in the page — layer assignment, dummy nodes for
  long edges, crossing reduction, then coordinate straightening — rather than a
  force-directed blob, because dependencies have a direction and reading order
  should reflect it.

### Changed

- The demo reel and README were rebuilt around the current feature set: scope
  filters, `diff`, `check --junit` and the HTML graph, with the TUI screens
  recaptured. The before/after timings were re-measured against `rostree` 0.2.2
  installed from PyPI rather than carried over, and
  [`docs/media/README.md`](https://github.com/guilyx/rostree/blob/main/docs/media/README.md) records exactly what in the reel
  is a real capture and what is a synthetic workspace.

## [0.4.0] - 2026-08-08

v0.3.0 made big trees fast. This one makes them *yours*: on a sourced ROS 2
machine most of what rostree can see belongs to the distro, and until now there
was no way to say so.

### Added

- **Scope filters on every command that walks the graph** (`tree`, `graph`, `why`,
  `rdeps`, `check`, `diff`):
  - `-w/--only-workspace` — ignore packages installed under `/opt/ros`
  - `--include GLOB` / `--exclude GLOB` — repeatable shell globs on package names
    (`--include 'nav2_*'`, `--exclude '*_msgs'`); excludes win over includes
  - A filtered-out package is neither shown nor followed, so anything reachable
    only through it disappears with it. Commands report what was hidden rather
    than silently presenting a smaller tree as the whole truth.
- **`--dep-type runtime|build|test|all`** to choose which `package.xml` tags to
  follow. `-r/--runtime` stays as a shorthand for `--dep-type runtime`.
- **`rostree diff`** — what did this package gain, lose or bump?
  - `rostree diff <a> <b>` compares two packages
  - `rostree diff <pkg> --save FILE` snapshots the current dependency set, and
    `--against FILE` compares against it after a rebuild
  - Reports added / removed / version-changed and exits non-zero on any drift
- **`rostree check --junit FILE`** writes a JUnit XML report for CI dashboards.
- `DependencyNode.hidden_children` records how many dependencies a truncated node
  is not showing, so `… N more` never promises more than the tree would print.
- `build_dependency_tree()` and `build_dependency_graph()` accept `package_filter`,
  `report` and (on the tree) `include_tags`.
- Bandit runs in CI and pre-commit and is in the `dev` extra, so
  `bandit -c pyproject.toml -r src tests` reproduces the security scan that gates
  pull requests instead of it existing only in a dashboard. `.codacy.yaml` records
  which rules are switched off for the test suite and why; accepted findings under
  `src/` carry an inline suppression with its reason, and
  [development.md](https://github.com/guilyx/rostree/blob/main/docs/development.md#static-analysis) writes down where those
  comments have to sit, which is less obvious than it sounds.

### Changed

- `rdeps --workspace-only` is now `--only-workspace`; the old spelling still works.
- The JUnit writer moved out of `cli.py` into `core/junit.py`. It is the only code
  in rostree that writes XML and never reads any, and keeping it separate lets that
  argument be made once, at the top of a short file, instead of on every line of a
  1,300-line module.
- The TUI's widget guards no longer catch bare `Exception`. Eleven `try/except
  Exception: pass` blocks around `query_one` became
  `contextlib.suppress(QueryError, ScreenStackError)`, so a bug inside a guarded
  block raises instead of disappearing. The two guards that are deliberately
  broad — best-effort tree expansion and collapse, which a background rebuild can
  interrupt — say so in a comment.

### Security

- `package.xml` is now parsed with [defusedxml](https://pypi.org/project/defusedxml/),
  a new runtime dependency. `core/parser.py` is the only place rostree reads XML it
  did not write, and a manifest is just a file in a workspace: one declaring
  entities could previously make the parser expand them until it ran out of memory.
  Such a manifest is now refused, which reports the package as unreadable instead
  of hanging. A `DOCTYPE` that declares nothing still parses, so this drops no
  package that used to work.

## [0.3.0] - 2026-08-07

Large trees used to take tens of seconds — or never finish. This release makes
them near-instant and reworks the interface around them.

### Performance

- **Dependency trees are linear, not exponential.** A ROS dependency graph is a
  DAG: `rcutils` sits under nearly every branch. Expanding every path separately
  produced tens of thousands of duplicate nodes. Each package is now expanded once,
  where it first appears, and marked `↩ see above` elsewhere — the same convention
  `cargo tree` uses. Measured on a 135-package install space plus a 24-package
  source workspace, resolving `nav2_bringup` with `-r`:

  | depth | before | after |
  |-------|--------|-------|
  | 5 | 4,152 nodes / 1.02 s | 475 nodes / 0.02 s |
  | 6 | 18,273 nodes / 4.44 s | 548 nodes / 0.02 s |
  | 7 | 68,081 nodes / 17.41 s | 552 nodes / 0.02 s |
  | unlimited (the CLI default) | did not finish in 4 minutes | 552 nodes / 0.02 s |

  Pass `--full` to `rostree tree` for the old fully-expanded behaviour.
- **Package discovery happens once.** New `rostree.core.index.PackageIndex` scans
  every install prefix and source tree a single time and resolves names from memory.
  Previously every node of a tree could trigger a fresh recursive `os.walk`.
- **package.xml parsing is memoized** by path, mtime and size.
- **Source scans prune** `build/`, `install/`, `log/`, VCS metadata and directories
  marked `COLCON_IGNORE`/`AMENT_IGNORE`, and stop descending once a manifest is found.
- `rostree graph` resolves the whole DAG in one breadth-first pass instead of
  building a separate full tree per package.

### Added

- **`rostree why <package> <dependency>`** — shortest dependency paths between two
  packages, answering "why is this in my tree at all?".
- **`rostree rdeps <package>`** — reverse dependency lookup, with `--transitive`
  and `--workspace-only`.
- **`rostree check`** — reports dependency cycles and unresolved dependencies and
  exits non-zero, so it can gate CI.
- `rostree list --filter TEXT` to narrow the package list.
- `rostree tree --full`, `--expand-repeats`, `--max-nodes` and `-v` for descriptions.
- `--no-color` on all commands (`NO_COLOR` is honoured too).
- `NodeStatus` enum on `DependencyNode` (`ok`, `repeat`, `cycle`, `missing`,
  `parse_error`, `truncated`) plus `is_error`/`is_placeholder`, replacing string
  markers stuffed into `description`. `to_dict()` now includes `status`.
- Public API: `build_graph()`, `reverse_dependencies()`, `get_index()`, `tree_stats()`.
- TUI: live filter over every package, reverse-dependency view (`v`), dependency
  scope toggle (`t`), and a help screen (`?`).

### Fixed

- **Graphs no longer drop edges to unresolved packages.** Dependencies without a
  manifest are drawn dashed and grey instead of being silently removed, which used
  to leave workspace graphs as a field of unconnected boxes. `--hide-missing`
  restores the old behaviour.
- **`rostree graph -w PATH` now works on a workspace that is not sourced** — the
  workspace's own packages are added to the search path.
- **Unbuilt packages in a sourced workspace are found again.** The source root was
  derived as `<ws>/install/src` instead of `<ws>/src`, so `src`-only packages were
  invisible whenever the workspace was discovered through `AMENT_PREFIX_PATH` or
  `COLCON_PREFIX_PATH`. Both the merged (`<ws>/install`) and isolated
  (`<ws>/install/<pkg>`) colcon layouts are now handled.
- **Packages named `lib*` are no longer discarded.** `libstatistics_collector` and
  `libyaml_vendor` are real ROS 2 packages; only dashed rosdep keys
  (`libboost-dev`, `python3-numpy`) are treated as system dependencies, and those
  are now kept on `PackageInfo.system_dependencies` rather than dropped.
- **The TUI no longer freezes** while a tree is built: resolution runs on a worker
  thread and rows are created only as nodes are expanded.
- The TUI package list is no longer capped at 80 entries per source.
- Text trees use correct box-drawing characters (`└──` for last children, proper
  vertical guides); previously every child was drawn as `├──`.
- An unknown package name is now an error with suggestions and a non-zero exit,
  instead of a one-node tree and exit 0.
- The five duplicated hand-rolled `<name>` XML scrapers were replaced by a single
  `quick_package_name()` helper.
- Worker results in the TUI are routed to the callback that asked for them, rather
  than to whichever handler saw the completion event first.
- **`↩ see above` now always refers to something printed earlier.** Expansion was
  chosen by shortest distance from the root while the tree renders depth-first, so
  a back-reference could point at a subtree printed *below* it. Each package is now
  expanded where the tree first prints it, which also removes a whole breadth-first
  pass from tree building.
- Reverse dependencies were cached without keying on the dependency tag set, so a
  runtime-only lookup and a full lookup returned whichever ran first.
- `rostree why <pkg> <pkg>` reported a dependency path for a package that does not
  exist; the validation loop skipped both arguments when they were equal.
- Global flags such as `--no-color` are accepted after the subcommand too
  (`rostree tree rclcpp --no-color` used to be a usage error).
- TUI: pressing `e` (expand all) or running a search no longer duplicates every
  row of an already-expanded tree.
- TUI: selecting a second package while a tree is still building no longer leaves
  the app pointing at a tree it never rendered.
- TUI: adding a source path while a tree is open now rescans, instead of leaving
  the new packages invisible.
- TUI: `Esc` leaves the dependents view when it was opened from the package list.
- `--open` no longer goes through a shell on Windows: it uses `os.startfile`, so a
  path containing shell metacharacters cannot be misinterpreted. External tools
  (`dot`, `open`, `xdg-open`) are resolved to absolute paths before being executed.

### Changed

- `rostree tree` groups sibling back-references onto one line
  (`↩ 5 already shown above: …`); `--expand-repeats` lists them individually.
- Depth-limited nodes report how many dependencies are hidden (`… 5 more`).
- `rich` is now a direct dependency (it was already installed via `textual`).
- Lint rules are pinned in `pyproject.toml` so a new ruff release cannot change
  what CI enforces.

## [0.2.2] - 2026-02-05

### Added

- **TUI background loading**: Package scanning now starts immediately when app opens (before pressing Enter)
- **Loading indicator**: Shows spinner and status while scanning for packages
- **Ready status**: Welcome screen shows package count when scanning completes (e.g., "✓ 123 packages found")

### Changed

- TUI uses cached packages from background scan for instant navigation
- Refresh action (`r`) now clears cache and rescans in background

## [0.2.1] - 2026-02-05

### Fixed

- **Dynamic versioning**: `rostree --version` now correctly reads version from package metadata instead of hardcoded value
- **TUI banner alignment**: Fixed ASCII art banner with inconsistent character alignment causing visual shifting

### Changed

- Version is now sourced from `importlib.metadata` for single source of truth (pyproject.toml)

## [0.2.0] - 2026-02-05

### Added

- **`rostree graph` command**: Generate dependency graphs in DOT (Graphviz) or Mermaid format
  - **Direct image rendering**: `--render png|svg|pdf` creates image files
  - **Two rendering backends**: Graphviz (system) or matplotlib (pip: `rostree[viz]`)
  - **Auto-open**: `--open` opens the rendered image in default viewer
  - Single package: `rostree graph rclpy --render png`
  - Entire workspace: `rostree graph --render png` or `rostree graph -w /path/to/ws --render svg`
  - Output to file with `-o/--output` or stdout
  - Support for depth limiting with `-d/--depth`
  - Runtime-only dependencies with `-r/--runtime`
  - Formats: `--format dot` (default) or `--format mermaid`
  - Progress output when processing multiple packages
- **TUI improvements**:
  - Full-page welcome screen with centered banner and app description
  - Search functionality (`/` or `f` to search, `n`/`N` to navigate matches)
  - Details panel toggle (`d` to show/hide)
  - Keyboard-only navigation throughout

### Changed

- Welcome screen is now a full view instead of a modal overlay
- Improved package source categorization display

## [0.1.0] - 2026-02-05

### Added

- **Core functionality**:
  - `rostree scan`: Discover ROS 2 workspaces across the system
  - `rostree list`: List known packages (optionally grouped by source)
  - `rostree tree`: Display dependency trees in text or JSON format
  - `rostree tui`: Interactive terminal UI for exploring dependencies
- **Package discovery**:
  - Automatic detection from `AMENT_PREFIX_PATH`, `COLCON_PREFIX_PATH`
  - Support for system installs (`/opt/ros/*`)
  - Workspace detection (src, install, build directories)
  - User-added source paths
- **Dependency parsing**:
  - Parse `package.xml` format 2 and 3
  - Support for depend, exec_depend, build_depend, test_depend
  - Runtime-only mode for faster, smaller trees
  - Cycle detection and handling
- **Interactive TUI**:
  - Browse packages by source category
  - Expand/collapse dependency trees
  - View package details (version, description, path, stats)
  - Keyboard-driven navigation
- **Python API**:
  - `list_known_packages()`, `list_known_packages_by_source()`
  - `get_package_info()`, `build_tree()`
  - `scan_workspaces()`
- **Developer tooling**:
  - Pre-commit hooks (ruff, black)
  - GitHub Actions CI
  - Codecov integration
  - 90%+ test coverage on core modules

### Dependencies

- Python 3.10+
- textual >= 0.47.0

[Unreleased]: https://github.com/guilyx/rostree/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/guilyx/rostree/compare/v0.4.0...v1.0.0
[0.4.0]: https://github.com/guilyx/rostree/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/guilyx/rostree/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/guilyx/rostree/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/guilyx/rostree/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/guilyx/rostree/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/guilyx/rostree/releases/tag/v0.1.0
