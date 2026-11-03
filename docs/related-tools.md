# rostree and other tools

rostree is not the first tool to look at ROS package dependencies, and it does
not replace the ones you already use. This page says what each is for, so you can
pick the right one — and so it is clear what rostree adds rather than duplicates.

## What already exists

**`colcon graph`** — part of colcon, the ROS 2 build tool. In its
[documentation's](https://colcon.readthedocs.io/en/released/reference/verb/graph.html)
words it "generates a visual representation of the package dependency graph":
by default a topologically ordered list that uses ASCII art to show direct and
transitive dependencies, or DOT with `--dot`, ready for Graphviz. It describes
the packages colcon has discovered to build.

**`colcon list --packages-up-to` / `--packages-above`** —
[package selection arguments](https://colcon.readthedocs.io/en/released/reference/package-selection-arguments.html)
for building: "the packages with the passed names as well as their recursive
dependencies", or "as well as packages which recursively depend on them". They
answer *which packages should this build include*.

**`ros2 pkg`** — `ros2 pkg list`, `ros2 pkg prefix` and `ros2 pkg xml` list the
installed packages, say where one lives, and print its manifest. Lookups, one
package at a time.

**`rosdep`** — resolves the rosdep keys in a manifest (`eigen`, `python3-numpy`)
to operating-system packages and installs them. It is about system dependencies,
not about the graph of ROS packages.

**`rqt_dep`** — in ROS 1, a GUI plugin that drew the package dependency graph.

## What rostree adds

colcon's tools are built around **building**: which packages to build, and in
what order. rostree is built around **understanding** a dependency graph you
already have, and keeping an eye on it.

- **Everything the environment can see**, not only what is being built — your
  workspace and the distro under it, wherever the distro is installed — with
  each package labelled by where it came from.
- **Questions, not just pictures.** Why does this package depend on that one —
  every shortest chain (`why`)? What breaks if I change this, by name, through
  any chain (`rdeps --transitive`)? What did this package gain, lose or bump since
  the last snapshot (`diff`)?
- **Readable at workspace scale.** A ROS graph is a DAG, so printing it as a tree
  repeats shared subtrees thousands of times. rostree prints each package once
  and refers back to it — see [How the algorithms work](algorithms.md).
- **A CI gate.** `rostree check` fails on dependency cycles and on names that
  resolve to no package, with JUnit output; `diff` fails on drift.
- **An interactive graph you can send.** `graph -f html` writes one self-contained
  file — no CDN, no network — that shows one package's neighbourhood at a time
  instead of the whole workspace at once.
- **A library.** Everything above is a function in `rostree.api`. See
  [Build on rostree](extending.md).

## When to use which

| You want to… | Use |
|---|---|
| choose which packages a build includes | `colcon build --packages-up-to …` |
| see the build order of the workspace you are building | `colcon graph` |
| install the system packages a workspace needs | `rosdep install` |
| find where one installed package lives | `ros2 pkg prefix` |
| know why one package pulls in another | `rostree why` |
| know what breaks if you change a package | `rostree rdeps -t` |
| fail CI on cycles, unresolved names or dependency drift | `rostree check`, `rostree diff` |
| explore a workspace's dependencies interactively | `rostree` (TUI) or `rostree graph -f html` |

If you know of a tool that belongs on this page, or something here is out of
date, please open an issue.
