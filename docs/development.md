# Development

## Layout

```
rosdep_viz/
├── docs/                 # Documentation (this folder)
├── src/rosdep_viz/       # Main package
│   ├── core/             # finder, parser, tree
│   ├── api.py            # Public API
│   └── tui/              # Textual TUI
├── tests/                # pytest
├── rosdep_viz_webapp/     # Web app (backend + frontend)
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

Dev extras: pytest, pytest-cov, ruff, black.

## Pre-commit

Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/) (e.g. `fix:`, `feat:`, `chore:`). Pre-commit runs ruff and black and enforces that.

```bash
pip install pre-commit
pre-commit install
pre-commit install --hook-type commit-msg
```

- **Ruff** — Lint and fix (src, tests, rosdep_viz_webapp/backend).
- **Black** — Format (line-length 100).
- **conventional-pre-commit** — Commit message prefix check (commit-msg hook).

## CI

- **ci-library.yml** — Python 3.10–3.12, pip install, ruff, black, pytest.
- **ci-backend.yml** — Install library + backend[dev], pytest (backend tests).
- **ci-frontend.yml** — Node 22, npm install, lint, build.
- **publish.yml** — Build and publish to PyPI on release (Trusted Publishing).

No path filters: CI runs on every push/PR to main/master.

## Tests

```bash
pytest tests -v
# From backend: cd rosdep_viz_webapp/backend && pytest tests -v
```

## Docs

- **docs/README.md** — Index of all docs.
- **docs/overview.md** — System overview and data flow.
- **docs/package-discovery.md** — How packages are found (env vars, workspaces).
- **docs/dependency-trees.md** — package.xml parsing, tree building, runtime_only.
- **docs/usage.md** — TUI, API, webapp.
- **docs/development.md** — This file.

Keep the root **README.md** lean; link to these docs for details.
