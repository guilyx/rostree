# Publication

We intend to publish rostree as a peer-reviewed **software paper**.

The aim is the same as the project's: a framework other people can build on, and
a clear explanation of the algorithms behind dependency analysis in ROS 2 — why a
ROS dependency graph has to be treated as a graph rather than a tree, and how to
answer questions about it (why, who depends on this, what changed) in time linear
in its size. A paper puts that explanation through review and gives researchers
who use rostree something to cite.

This page records the plan in the open, including what is not ready yet.

## Candidate venues

As of November 2026:

| Venue | Format | Fit | Status |
|---|---|---|---|
| [Frontiers — *Robotics Software Engineering Vol. 2*](https://www.frontiersin.org/research-topics/76869/robotics-software-engineering-vol-2) | Journal article, *Technology and Code* type | Scope names ROS, software architecture, testing and CI; linked to the RoSE workshop | Open; manuscripts due **18 December 2026**. Publishing fee applies |
| [RoSE](https://conf.researchr.org/home/icse-2025/rose-2025) — International Workshop on Robotics Software Engineering | Workshop paper; past editions had a short tool-paper track | Software engineering for robotics — exactly this | 2026 edition held with ICRA (Vienna, June); 2027 not yet announced |
| [JOSS](https://joss.theoj.org/) — Journal of Open Source Software | Short paper, open review on GitHub | Requires an "obvious research application"; rejects minor utilities | Possible, but the research use would have to be argued |
| [ROSCon](https://roscon.ros.org/) | Talk, not a paper | The ROS community itself | 2026 calls closed; 2027 to come |

## What the paper would describe

- **The problem**, measured: printing a ROS dependency DAG as a tree grows
  exponentially with shared dependencies — 60,981 lines for one package of a
  146-package workspace, against 253 when each package is expanded once.
- **The algorithms**, as [How the algorithms work](algorithms.md) explains them:
  expand-once tree building, breadth-first graph resolution with an explicit
  depth frontier, all-shortest-paths for `why`, reverse dependencies that filter
  the answer rather than the walk, three-colour cycle detection, layered DAG
  layout in the browser, and REP 149 condition evaluation without `eval`.
- **The design**: a library first, with the CLI, TUI and HTML viewer as clients
  of the same API; an interactive graph that works with no network; filters that
  always say what they removed.

## What has to happen first

A paper makes claims, and some of rostree's cannot be backed yet.

- [x] Public repository and issue tracker
- [ ] **One licence.** The `LICENSE` file is BSD 3-Clause, with copyright held by
      "The rosdep_viz authors" (the project's first name); `pyproject.toml`, and
      so PyPI, say MIT. Both are permissive, but a paper — and anyone who
      redistributes rostree — needs them to agree. The citation files leave the
      licence out until they do.
- [x] Automated tests and CI, with coverage reported on every pull request
- [x] Documentation site, including a public API covered by semantic versioning
- [x] Tagged releases on PyPI, and a changelog
- [x] Citation metadata: `CITATION.cff` and `codemeta.json` in the repository
- [ ] **Tests against a real ROS 2 installation.** Every test runs on generated
      workspaces today. Running the suite in a `ros:jazzy` container is the top
      item on the [roadmap](roadmap.md), and a paper should not go out before it.
- [ ] **Evaluation on real, public workspaces** — timings and output sizes on
      large open-source ROS 2 code bases, rather than the synthetic workspace the
      current measurements use.
- [ ] **An archived release with a DOI** (for example through Zenodo), so the
      paper cites an exact, permanent version.

## Use of AI tools

Much of rostree's code, tests and documentation from version 0.3.0 on was written
with Claude Code, Anthropic's AI coding agent, working through pull requests on
this repository. Those pull requests say so in their descriptions. The commits on
the main branch do not reliably record it — most were squash-merged without the
co-author line — so the pull requests, not the commit log, are the record.

The code review in `docs/review.md` that preceded 0.3.0 was also AI-generated, as
the commit that added it says.

Any submission will disclose this in the form the venue asks for.

## How to cite rostree

Until there is a paper, cite the software itself. GitHub's **Cite this
repository** button (on the repository's front page) reads `CITATION.cff` and
produces APA and BibTeX. Please include the version you used.

## How you can help

The most useful contribution to the paper is **evidence**: run rostree on a
workspace you work on and tell us what it got right or wrong — an issue
describing your workspace layout is enough. Reports from real code bases are
exactly what the evaluation needs, and the kind of thing no generated fixture can
stand in for.
