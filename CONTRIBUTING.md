# Contributing to rostree

Thanks for looking. rostree is meant to be built on and learned from, so
contributions of every size are welcome: a bug report from a workspace layout we
have never seen, a sentence in the docs that was hard to follow, a new analysis,
or a tool of your own that uses the library.

## The most useful thing you can send

**A report from a real workspace.** Every test runs on generated fixtures, and
the bugs that have shipped so far were layouts nobody generated. If rostree gets
your workspace wrong — or right, on something large — open a
[workspace report](https://github.com/guilyx/rostree/issues/new?template=workspace_report.yml).
It also feeds the evaluation for the [paper we intend to publish](docs/publication.md).

## Asking and reporting

- **Bugs** — [open a bug report](https://github.com/guilyx/rostree/issues/new?template=bug_report.yml).
  `rostree --version`, your ROS distro and how the workspace is built (colcon
  merged or isolated install, symlink install, source only) usually decide it.
- **Ideas** — [open a feature request](https://github.com/guilyx/rostree/issues/new?template=feature_request.yml).
  Start from the question you are trying to answer about your graph; the
  command shape can come later.
- **Security issues** — not in a public issue. See [SECURITY.md](SECURITY.md).

## Setting up

```bash
git clone https://github.com/guilyx/rostree && cd rostree
pip install -e ".[dev,docs]" pre-commit
pre-commit install && pre-commit install --hook-type commit-msg
```

You do not need ROS installed. The tests generate the workspaces they need.

## Before you open a pull request

These are what CI runs:

```bash
pytest                                     # the whole suite, ~10 s
ruff check src tests examples
black --check src tests examples
bandit -c pyproject.toml -r src tests examples
mkdocs build --strict                      # if you touched docs/, README or examples/
```

Pre-commit runs ruff, black and bandit on each commit, with the same versions CI
pins in the `dev` extra.

## What a good pull request looks like

- **One change.** A fix, a feature or a refactor, not all three. Small pull
  requests get reviewed sooner.
- **A test that fails without it.** For a bug, the test reproduces the bug. For
  a CLI change, drive `rostree.cli.main([...])` end to end so the argument wiring
  is tested too (see `tests/test_cli_behaviour.py`).
- **A CHANGELOG entry** under `[Unreleased]`, written for someone using rostree,
  not for someone reading the diff.
- **Docs**, if behaviour a user can see changed.
- **[Conventional Commits](https://www.conventionalcommits.org/)** for commit
  messages and the pull request title: `fix:`, `feat:`, `docs:`, `refactor:`,
  `test:`, `chore:`, `ci:`, `perf:`. The pre-commit hook checks it.

## Where things go

[Build on rostree](docs/extending.md#adding-to-rostree-itself) has the detail.
In short:

| Change | Goes in |
|---|---|
| A question about the graph (`why`, `rdeps`, `diff`…) | `src/rostree/core/analysis.py` — a pure function: no printing, no `sys.exit`, no environment reads — exported from `rostree.api` |
| A CLI command or flag | `src/rostree/cli.py`, as a thin `cmd_*` that calls the analysis |
| How packages are found | `src/rostree/core/index.py`, `core/finder.py` |
| Reading `package.xml` | `src/rostree/core/parser.py`, `core/conditions.py` |
| The browser graph | `src/rostree/web/` and `core/webview.py` — no network access, ever |
| A tool built on the library | `examples/`, with a test in `tests/test_examples.py` |

## Compatibility

From 1.0, the CLI commands and flags and everything exported from `rostree.api`
follow semantic versioning. A pull request that changes either incompatibly needs
a deprecation path first: keep the old behaviour, warn, and remove it in the next
major version. Anything under `rostree.core` is internal and can change.

## AI-assisted contributions

Welcome, on the same terms as the rest: you understand every line, it is tested,
and the pull request says which tools you used. Much of rostree itself was
written with an AI coding agent, and its pull requests say so.

## Conduct

Everyone taking part is expected to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).
