# rostree Roadmap

Based on the [code review](./review.md), this roadmap prioritizes fixes and features to make rostree production-ready.

---

## Phase 1: Critical Fixes (v0.3.0)

**Goal:** Make the graph visualization actually work for real workspaces.

### 1.1 Fix Graph Edge Collection
- [ ] Add option to include edges to "(not found)" packages
- [ ] Add `--show-missing` flag to graph command
- [ ] Style missing packages differently (dashed lines, gray nodes)
- [ ] Default behavior: show edges to missing packages in workspace graphs

### 1.2 Implement ros2 pkg Fallback Properly
- [ ] Add `parse_package_xml_string()` to parser.py
- [ ] Add `_try_ros2_pkg_xml()` helper to tree.py
- [ ] Add `_try_ros2_pkg_prefix()` helper to tree.py
- [ ] Integrate fallback into `build_dependency_tree()`
- [ ] Add tests with mocked subprocess calls
- [ ] Document fallback behavior

### 1.3 Add Package Discovery Caching
- [ ] Create `PackageCache` class with TTL
- [ ] Cache `find_package_path()` results
- [ ] Cache `parse_package_xml()` results
- [ ] Add `--no-cache` flag for fresh scans
- [ ] Persist cache to disk (optional)

### 1.4 Fix Performance Issues
- [ ] Fix O(n²) visited set copying in `build_dependency_tree()`
- [ ] Deduplicate XML name parsing into single helper
- [ ] Add progress callback for long operations

---

## Phase 2: Code Quality (v0.4.0)

**Goal:** Make the codebase maintainable and testable.

### 2.1 Refactor Status Markers
- [ ] Create `NodeStatus` enum
- [ ] Create `ErrorNode` dataclass (or use discriminated union)
- [ ] Update all status string checks to use enum
- [ ] Add `is_error` property to `DependencyNode`

### 2.2 Split CLI Module
- [ ] Extract `cli/commands/scan.py`
- [ ] Extract `cli/commands/list.py`
- [ ] Extract `cli/commands/tree.py`
- [ ] Extract `cli/commands/graph.py`
- [ ] Extract `graph/dot.py`
- [ ] Extract `graph/mermaid.py`
- [ ] Extract `graph/render.py`
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
- [ ] Add `rostree rdeps <package>` command
- [ ] Build reverse dependency index
- [ ] Show "what depends on X" tree
- [ ] Add to TUI as separate view

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
- [ ] Add `--format json` for structured output
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
- [ ] Add `rostree check` command for CI
- [ ] Detect circular dependencies
- [ ] Detect missing dependencies
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
- [ ] Add architecture documentation
- [ ] Add API reference with examples
- [ ] Add troubleshooting guide
- [ ] Add contribution guidelines
- [ ] Add video tutorials

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
| 0.3.0 | Q1 2026 | Working graph visualization, ros2 fallback |
| 0.4.0 | Q2 2026 | Refactored codebase, better errors |
| 0.5.0 | Q2 2026 | Reverse deps, filtering, config files |
| 0.6.0 | Q3 2026 | Diff, interactive graph, CI integration |
| 1.0.0 | Q4 2026 | Production-ready, documented, distributed |

---

## Quick Wins (Can Be Done Anytime)

These are low-effort improvements that can be merged opportunistically:

- [ ] Add `NodeStatus` enum (1 hour)
- [ ] Deduplicate XML name parsing (2 hours)
- [ ] Fix visited set copying (30 minutes)
- [ ] Add type hints to TUI helpers (1 hour)
- [ ] Add docstrings to test methods (2 hours)
- [ ] Add `--quiet` flag to suppress progress output (30 minutes)
- [ ] Allow TUI limits to be overridden via env vars (1 hour)

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
