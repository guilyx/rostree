---
hide:
  - navigation
---

# rostree

Explore your ROS 2 dependency graph — from the command line, in a TUI, or in your
browser.

```bash
pip install rostree
source /opt/ros/<distro>/setup.bash   # and/or your workspace install/setup.bash
rostree                               # interactive TUI
```

![rostree](media/rostree-demo.gif)

## Start here

<div class="grid cards" markdown>

-   **[Usage](usage.md)**

    Every command, the TUI keymap, and the Python API.

-   **[Overview](overview.md)**

    How the pieces fit: library, CLI, TUI, and the data that flows between them.

-   **[Package discovery](package-discovery.md)**

    Where packages come from — `AMENT_PREFIX_PATH`, colcon layouts, source trees.

-   **[Dependency trees](dependency-trees.md)**

    `package.xml` parsing, the package index, and why repeats are collapsed.

-   **[Development](development.md)**

    Layout, pre-commit, CI, static analysis, and the HTML viewer.

-   **[Roadmap](roadmap.md)**

    What shipped, what was dropped and why, and what is next.

</div>

## The idea

A ROS dependency graph is a **DAG, not a tree**. `rcutils` sits under almost every
branch, so expanding each path separately means drawing it thousands of times.
rostree expands each package **once, where it first appears**, and references it
elsewhere as `↩ see above` — the convention `cargo tree` uses for `(*)`.

That one decision is why a workspace-wide tree resolves in a fifth of a second
instead of never finishing, and it is the same reason the
[HTML graph](usage.md#rostree-graph) draws `rclcpp` once with every arrow into it
rather than as a hairball.

## Stability

From 1.0, the CLI commands and their flags and everything exported from
`rostree.api` follow semantic versioning. Anything under `rostree.core` is
internal. The exact text rostree prints is not covered — that output is for
people; parse `--json` instead.

The test suite runs on generated fixtures and has not yet been exercised against
a real ROS 2 installation, which is the top item on the
[roadmap](roadmap.md). If rostree gets your workspace layout wrong, an issue
describing it is the most useful thing you can send.
