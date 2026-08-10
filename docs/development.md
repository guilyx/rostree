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
│   │   ├── graph.py      # DOT / Mermaid generation
│   │   ├── junit.py      # JUnit report for `rostree check --junit`
│   │   └── webview.py    # Interactive HTML graph (inlines web/)
│   ├── api.py            # Public API
│   ├── cli.py            # Command line interface
│   ├── web/              # graph.html/.css/.js — the viewer, shipped as data
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

Pull requests are scanned by [Codacy](https://www.codacy.com/), which runs
**two** tools whose findings look alike but are suppressed differently:

| Tool | Suppressed by | Reported as |
|------|---------------|-------------|
| Bandit | `# nosec B123` | Low / Medium / High |
| Semgrep | `# nosemgrep` | Critical |

A `# nosec` does nothing to a Semgrep finding, and vice versa, so the few lines
that trip both carry both. Three things about placement, each of which cost a
CI round to learn:

1. Bandit reads everything after `nosec` as a list of rule IDs, so the reasoning
   goes on the line above, not trailing it, and `nosec` comes last.
2. Both comments must sit on the line the tool *reports*. Adding them can push a
   line past 100 characters, at which point black splits the call and strands the
   comment on the closing paren — where it silences nothing. Put it on the
   `subprocess.run(` line and let the arguments wrap.
3. Semgrep does not accept a trailing `# nosemgrep` on an `import`; it has to go
   on the line before.

`.codacy.yaml` carries a fourth: an `engines.semgrep.exclude_paths` block is not
honoured at all, though the identical `engines.bandit` one is. Semgrep is
therefore only ever silenced in the source.

Bandit also runs in `ci.yml` and pre-commit, so a finding lands next to the lint
failures instead of only in a dashboard:

```bash
bandit -c pyproject.toml -r src tests
```

`.codacy.yaml` and `[tool.bandit]` are kept in step with each other; changing one
without the other is how the two disagree.

One rule is switched off for `tests/` only, **B101 (`assert` used)** — every
pytest assertion trips it. The rule exists because `python -O` strips asserts,
which is not how a test suite runs. There are no asserts under `src/`.

`tests/test_cli_commands.py` reads a JUnit report back to check it, and uses
defusedxml to do it — not because a file the test wrote three lines earlier is a
threat, but because it costs nothing: defusedxml is already a runtime dependency
for `core/parser.py`.

Everything under `src/` is still scanned, and the accepted findings there carry
their reason next to them, so a *new* finding on one of those lines still has to
be looked at rather than inheriting a blanket exemption. There are two:

- **The `subprocess` calls in `cli.py`** — fixed argv, absolute path from
  `shutil.which`, no shell anywhere.
- **`core/junit.py`** — the only module that writes XML, and it never reads any.
  `defusedxml`, the replacement both tools recommend, exports no
  `Element`/`SubElement`/`ElementTree`, so there is nothing to switch to on the
  writing side and nothing to defend against either: the only untrusted values
  are package names, which ElementTree escapes. Keeping it in its own small
  module means that argument is made once, at the top of a file you can read in
  a minute, rather than buried in a 1,300-line CLI.

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

## The HTML graph viewer

`src/rostree/web/` holds real `.html`, `.css` and `.js` files rather than Python
strings, so they can be edited and diffed like the front-end code they are.
`core/webview.py` inlines all three into one document at generation time.

There is no build step and no dependency, on purpose: the output has to work
from a `file://` URL with no network, which rules out a CDN, and vendoring a
layout library to avoid one would be a worse trade than the ~200 lines of
layered-DAG layout in `graph.js`.

To work on it, generate a page and open it:

```bash
rostree graph nav2_bringup -f html -o /tmp/g.html && xdg-open /tmp/g.html
```

Two things that are easy to get wrong and have already bitten:

- **Do not call `setPointerCapture` on the canvas.** Chromium retargets the
  compatibility mouse events to the capturing element, so every `click` arrives
  on the `<svg>` and no node is ever clickable. Pan by listening on `window`.
- **`[hidden]` needs `display: none !important`**, because several of the things
  it is applied to set an explicit `display` further down the stylesheet.

`tests/test_webview.py` covers the payload and the document — that it is
self-contained, that no placeholder survives, and that a `</script>` in a
package description cannot break out of the data block. Behaviour inside the
page is not unit-tested; check it in a browser.

## Docs

- **docs/README.md** — Index of all docs.
- **docs/overview.md** — System overview and data flow.
- **docs/package-discovery.md** — How packages are found (env vars, workspaces).
- **docs/dependency-trees.md** — parsing, the package index, repeat collapsing, graphs.
- **docs/usage.md** — CLI, TUI keys, Python API.
- **docs/development.md** — This file.

Keep the root **README.md** lean; link to these docs for details.
