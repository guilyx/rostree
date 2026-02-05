# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/guilyx/rostree/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/guilyx/rostree/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/guilyx/rostree/releases/tag/v0.1.0
