# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/guilyx/rostree/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/guilyx/rostree/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/guilyx/rostree/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/guilyx/rostree/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/guilyx/rostree/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/guilyx/rostree/releases/tag/v0.1.0
