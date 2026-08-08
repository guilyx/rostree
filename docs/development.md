# Development

## Layout

```
rostree/
├── docs/                 # Documentation (this folder)
├── src/rostree/          # Main package
│   ├── core/
│   │   ├── index.py      # One-pass cached package index
│   │   ├── finder.py     # Workspace scanning + name lookups
│   │   ├── parser.py     # package.xml parsing (memoized)
│   │   ├── tree.py       # DependencyGraph + DependencyNode
│   │   └── graph.py      # DOT / Mermaid generation
│   ├── api.py            # Public API
│   ├── cli.py            # Command line interface
│   └── tui/              # Textual TUI
├── tests/                # pytest (incl. TUI pilot tests)
├── pyproject.toml
├── .pre-commit-config.yaml
└── .github/workflows/    # CI and publish
```

## Install (dev)

```bash
# From repo root
pip install -e ".[dev]"
# or: uv pip install -e ".[dev]"
```

Dev extras: pytest, pytest-cov, ruff, black, bandit.

## Pre-commit

Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/) (e.g. `fix:`, `feat:`, `chore:`). Pre-commit runs ruff and black and enforces that.

```bash
pip install pre-commit
pre-commit install
pre-commit install --hook-type commit-msg
```

- **Ruff** — Lint and fix (src, tests). The enabled rule set is pinned in
  `[tool.ruff.lint]` and the version is pinned in the `dev` extra, so a new ruff
  release cannot silently change what CI enforces.
- **Black** — Format (line-length 100).
- **conventional-pre-commit** — Commit message prefix check (commit-msg hook).

## Static analysis

```bash
bandit -c pyproject.toml -r src tests
```

Pull requests are also scanned by [Codacy](https://www.codacy.com/), which runs
**two** tools whose findings look alike but are suppressed differently:

| Tool | Suppressed by | Reported as |
|------|---------------|-------------|
| Bandit | `# nosec B123` | Low / Medium / High |
| Semgrep | `# nosemgrep` | Critical |

A `# nosec` does nothing to a Semgrep finding, and vice versa, so the few lines
that trip both carry both. Bandit reads everything after `nosec` as a list of
rule IDs, which is why the annotations end `# nosemgrep  # nosec B123` and the
reasoning sits on the line above rather than trailing it.

Bandit also runs in `ci.yml` and pre-commit, so a finding lands next to the lint
failures instead of only in a dashboard:

```bash
bandit -c pyproject.toml -r src tests
```

`.codacy.yaml` and `[tool.bandit]` are kept in step with each other; changing one
without the other is how the two disagree.

Two rules are switched off for `tests/` only:

- **B101 (`assert` used)** — every pytest assertion trips it. The rule exists
  because `python -O` strips asserts, which is not how a test suite runs. There
  are no asserts under `src/`.
- **The XML rules** — `tests/test_cli_commands.py` reads back a JUnit report that
  the same test wrote to a `tmp_path` moments earlier.

Everything under `src/` is still scanned, and the accepted findings there carry
their reason next to them, so a *new* finding on one of those lines still has to
be looked at rather than inheriting a blanket exemption. There are two:

- **`cli.py`'s `xml.etree` import** — `_write_junit` writes a report and never
  reads one. `defusedxml`, the replacement both tools recommend, exports no
  `Element`/`SubElement`/`ElementTree`, so there is nothing to switch to on the
  writing side. The one place rostree *does* parse XML, `core/parser.py`, uses
  defusedxml.
- **The `subprocess` calls** — fixed argv, absolute path from `shutil.which`, no
  shell anywhere.

Bandit logs a `nosec encountered, but no failed test` warning for a couple of
them — it attributes multi-line statements to the wrong line — which is noise,
not a stale suppression.

## CI

- **ci.yml** — lint (ruff, black, bandit) plus pytest with coverage on Python 3.10–3.12.
- **publish.yml** — Build and publish to PyPI on release (Trusted Publishing).

CI runs on every push/PR to main/master.

## Tests

```bash
pytest tests -v
```

TUI behaviour is covered by `tests/test_tui_app.py`, which drives the real app
through Textual's pilot harness (key presses, background workers, lazy expansion)
rather than testing helpers in isolation. `tests/conftest.py` clears the package
index and parse caches between tests — they are process-wide by design, so tests
must not share them.

## Docs

- **docs/README.md** — Index of all docs.
- **docs/overview.md** — System overview and data flow.
- **docs/package-discovery.md** — How packages are found (env vars, workspaces).
- **docs/dependency-trees.md** — parsing, the package index, repeat collapsing, graphs.
- **docs/usage.md** — CLI, TUI keys, Python API.
- **docs/development.md** — This file.

Keep the root **README.md** lean; link to these docs for details.
