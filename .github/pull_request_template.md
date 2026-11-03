## What and why

<!-- What does this change, and what problem does it solve? Link the issue if there is one. -->

## How it was tested

<!-- For a fix: the test that fails without it. For a CLI change: a test that drives main([...]). -->

## Checklist

- [ ] Tests pass: `pytest`
- [ ] Lint passes: `ruff check src tests examples`, `black --check src tests examples`
- [ ] `CHANGELOG.md` has an entry under `[Unreleased]`
- [ ] Docs updated if user-visible behaviour changed (`mkdocs build --strict` passes)
- [ ] No incompatible change to the CLI or `rostree.api` (or it has a deprecation path)
- [ ] If AI tools helped write this, it says which ones above
