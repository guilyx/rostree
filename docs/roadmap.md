# rostree Roadmap

Based on the [code review](./review.md), this roadmap prioritizes fixes and features to make rostree production-ready.

---

## Phase 1: Critical Fixes (v0.3.0) — shipped

**Goal:** Make the graph visualization actually work for real workspaces, and make
large trees usable.

Delivered in v0.3.0. The headline change was not on this list: dependency tree
building was **exponential** because a DAG was expanded once per path. Each package
is now expanded once, where it first appears (see
[dependency-trees.md](dependency-trees.md#repeats-why-trees-stay-small)), which took
an unlimited-depth tree from "never finishes" to 0.03 s.

Caching was implemented as a one-pass `PackageIndex` (`core/index.py`) rather than a
per-call cache with a TTL: discovery happens once per run, and the index is cached
per process and per environment with an explicit `refresh=True`. Disk persistence
was not needed once a full scan cost milliseconds.

### 1.1 Fix Graph Edge Collection
- [x] Add option to include edges to "(not found)" packages
- [x] Add `--show-missing` flag to graph command
- [x] Style missing packages differently (dashed lines, gray nodes)
- [x] Default behavior: show edges to missing packages in workspace graphs

### 1.2 Implement ros2 pkg Fallback Properly

Not done, and no longer clearly worth doing: with the index scanning every prefix
and source root, the packages `ros2 pkg xml` could find are already found, and
shelling out per package would be far slower. Unresolved names are now surfaced
honestly (`✗ not found`, dashed graph nodes, `rostree check`) instead of hidden.

- [ ] Add `parse_package_xml_string()` to parser.py
- [ ] Add `_try_ros2_pkg_xml()` helper to tree.py
- [ ] Add `_try_ros2_pkg_prefix()` helper to tree.py
- [ ] Integrate fallback into `build_dependency_tree()`
- [ ] Add tests with mocked subprocess calls
- [ ] Document fallback behavior

### 1.3 Add Package Discovery Caching
- [x] Create `PackageCache` class with TTL — shipped as `PackageIndex`, cached per
  process and per environment with explicit `refresh=True` instead of a TTL
- [x] Cache `find_package_path()` results
- [x] Cache `parse_package_xml()` results
- [ ] Add `--no-cache` flag for fresh scans
- [ ] Persist cache to disk (optional)

### 1.4 Fix Performance Issues
- [x] Fix O(n²) visited set copying in `build_dependency_tree()`
- [x] Deduplicate XML name parsing into single helper
- [x] Add progress callback for long operations

---

## Phase 2: Code Quality (v0.4.0)

**Goal:** Make the codebase maintainable and testable.

### 2.1 Refactor Status Markers
- [x] Create `NodeStatus` enum
- [ ] Create `ErrorNode` dataclass (or use discriminated union)
- [x] Update all status string checks to use enum
- [x] Add `is_error` property to `DependencyNode`

### 2.2 Split CLI Module
- [ ] Extract `cli/commands/scan.py`
- [ ] Extract `cli/commands/list.py`
- [ ] Extract `cli/commands/tree.py`
- [ ] Extract `cli/commands/graph.py`
- [x] Extract `graph/dot.py` — as `core/graph.py::to_dot`
- [x] Extract `graph/mermaid.py` — as `core/graph.py::to_mermaid`
- [ ] Extract `graph/render.py` — image rendering is I/O and stayed in `cli.py`
- [ ] Keep `cli/__init__.py` as entry point

### 2.3 Improve Error Handling
- [ ] Add `rostree.exceptions` module
- [ ] Create specific exception types (PackageNotFoundError, ParseError, etc.)
- [ ] Add optional logging (debug level by default)
- [ ] Add `--verbose` flag for detailed error output

### 2.4 Dependency Injection for Finder
- [ ] Create `DiscoveryConfig` dataclass
- [ ] Add `from_environment()` factory method
- [ ] Refactor finder functions to accept config
- [ ] Simplify test mocking

---

## Phase 3: New Features (v0.5.0)

**Goal:** Add commonly requested features.

### 3.1 Reverse Dependency Lookup
- [x] Add `rostree rdeps <package>` command
- [x] Build reverse dependency index
- [x] Show "what depends on X" tree
- [x] Add to TUI as separate view

### 3.2 Filtering Options
- [ ] Add `--filter-type` (runtime/build/test/all)
- [ ] Add `--filter-prefix` (e.g., `nav2_*`)
- [ ] Add `--exclude` for specific packages
- [ ] Add `--only-workspace` to exclude system packages

### 3.3 Configuration File Support
- [ ] Support `.rostreerc` (TOML format)
- [ ] Support `[tool.rostree]` in `pyproject.toml`
- [ ] Configuration options: default depth, filters, cache settings
- [ ] CLI args override config file

### 3.4 Export Formats
- [x] Add `--format json` for structured output
- [ ] Add `--format csv` for spreadsheet import
- [ ] Add SBOM export (CycloneDX format)
- [ ] Add requirements.txt generation

---

## Phase 4: Advanced Features (v0.6.0)

**Goal:** Power user features and integrations.

### 4.1 Dependency Diff
- [ ] Add `rostree diff <pkg1> <pkg2>` command
- [ ] Compare package.xml versions
- [ ] Highlight added/removed/changed dependencies
- [ ] Support comparing workspace snapshots

### 4.2 Interactive Graph
- [ ] Add web-based interactive viewer
- [ ] Click to expand/collapse subtrees
- [ ] Search and highlight in graph
- [ ] Export filtered views

### 4.3 CI/CD Integration
- [x] Add `rostree check` command for CI
- [x] Detect circular dependencies
- [x] Detect missing dependencies
- [ ] Output JUnit XML for test frameworks
- [ ] GitHub Action for automated checks

### 4.4 Performance Monitoring
- [ ] Add `--profile` flag
- [ ] Report filesystem operations count
- [ ] Report cache hit/miss ratio
- [ ] Suggest optimizations

---

## Phase 5: Ecosystem (v1.0.0)

**Goal:** Production-ready with comprehensive documentation.

### 5.1 Documentation Overhaul
- [x] Add video tutorials — a promo/demo cast lives in `docs/media/`
- [ ] Add architecture documentation
- [ ] Add API reference with examples
- [ ] Add troubleshooting guide
- [ ] Add contribution guidelines

### 5.2 Integration Tests
- [ ] Add tests against real ROS 2 packages
- [ ] Add performance benchmarks
- [ ] Add memory usage tests
- [ ] Set up CI with ROS 2 Docker images

### 5.3 Plugin System
- [ ] Define plugin interface
- [ ] Allow custom output formatters
- [ ] Allow custom package finders
- [ ] Document plugin development

### 5.4 Distribution
- [ ] Publish to ROS 2 package index
- [ ] Create Debian package
- [ ] Create conda-forge package
- [ ] Add to rosdep database

---

## Version Milestones

| Version | Target | Key Deliverables |
|---------|--------|------------------|
| 0.3.0 | ✅ shipped | Linear tree building, package index, graphs keep missing edges, `why`/`rdeps`/`check` |
| 0.4.0 | Q2 2026 | Refactored codebase, better errors |
| 0.5.0 | Q2 2026 | Reverse deps, filtering, config files |
| 0.6.0 | Q3 2026 | Diff, interactive graph, CI integration |
| 1.0.0 | Q4 2026 | Production-ready, documented, distributed |

---

## Quick Wins (Can Be Done Anytime)

These are low-effort improvements that can be merged opportunistically:

- [x] Add `NodeStatus` enum (1 hour)
- [x] Deduplicate XML name parsing (2 hours)
- [x] Fix visited set copying (30 minutes)
- [x] Add type hints to TUI helpers (1 hour)
- [ ] Add docstrings to test methods (2 hours)
- [ ] Add `--quiet` flag to suppress progress output (30 minutes)
- [x] Allow TUI limits to be overridden via env vars — obsolete: the 80-per-source
  and 500-node caps were removed rather than made configurable

---

## Contributing

See [development.md](./development.md) for setup instructions.

When picking up a roadmap item:
1. Create an issue referencing this roadmap
2. Assign yourself
3. Create a feature branch
4. Add tests for new functionality
5. Update documentation
6. Submit PR referencing the issue

---

## Feedback

This roadmap is a living document. Open an issue to:
- Suggest new features
- Reprioritize existing items
- Report blockers or dependencies
