"""Decide, cut and describe a release from the pull requests merged since the last one.

    python scripts/release/release.py plan  CHANGES.jsonl [--part auto|patch|minor|major]
    python scripts/release/release.py apply CHANGES.jsonl [--part ...] [--date YYYY-MM-DD]
    python scripts/release/release.py notes VERSION

``plan`` prints the part of the version to bump, or nothing when nothing merged since
the last release calls for one. ``apply`` bumps the version everywhere it is written,
turns ``## [Unreleased]`` in CHANGELOG.md into the new version's entry, and prints the
new version. ``notes`` prints a version's CHANGELOG entry, for the GitHub release.

The release workflow (``.github/workflows/publish.yml``) writes CHANGES.jsonl: one JSON
object per commit on main since the last ``v*`` tag, with the pull request it came
from when there is one::

    {"sha": "...", "subject": "...", "body": "...", "pr": {"number": 22, "title": "..."}}

The pull request's title wins over the commit subject, so the title that the PR title
check approved is the one that decides the release, whatever the merge method.

The bump follows Conventional Commits: a breaking change (``feat!:``, ``fix(cli)!:``,
or a ``BREAKING CHANGE:`` footer) is major, ``feat`` minor, ``fix``, ``perf``,
``revert`` and ``deps`` patch; ``docs``, ``refactor``, ``test``, ``build``, ``ci``,
``chore`` and ``style`` do not release on their own.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_URL = "https://github.com/guilyx/rostree"
PARTS = ("major", "minor", "patch")

# What a type releases on its own. Anything else, including a title that is not a
# Conventional Commit at all, releases nothing.
_PATCH_TYPES = {"fix", "perf", "revert", "deps"}
_SECTIONS = (
    ("feat", "Features"),
    ("fix", "Bug fixes"),
    ("perf", "Performance"),
    ("revert", "Reverts"),
    ("deps", "Dependencies"),
)

_TITLE = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)\s]+)\))?(?P<bang>!)?: (?P<desc>\S.*)$")
_PR_SUFFIX = re.compile(r"\s+\(#\d+\)$")
_BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE: ", re.M)
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass
class Change:
    """One pull request (or a commit pushed without one) since the last release."""

    type: str | None
    scope: str | None
    description: str
    breaking: bool
    pr: int | None
    sha: str

    @property
    def link(self) -> str:
        if self.pr is not None:
            return f"[#{self.pr}]({REPO_URL}/pull/{self.pr})"
        return f"[{self.sha[:7]}]({REPO_URL}/commit/{self.sha})"

    def line(self) -> str:
        scope = f"**{self.scope}:** " if self.scope else ""
        return f"- {scope}{self.description} ({self.link})"


def parse_changes(records: list[dict]) -> list[Change]:
    """One ``Change`` per pull request, in the order given (newest first from git log).

    Commits of the same pull request (a merge commit and the commits it brought in)
    collapse into one; a ``BREAKING CHANGE:`` footer on any of them marks it breaking.
    Release commits are skipped.
    """
    changes: list[Change] = []
    by_pr: dict[int, Change] = {}
    for record in records:
        subject = record.get("subject", "")
        if subject.startswith("chore(release):"):
            continue
        pr = record.get("pr") or None
        footer = bool(_BREAKING_FOOTER.search(record.get("body", "")))
        if pr is not None and pr["number"] in by_pr:
            by_pr[pr["number"]].breaking |= footer
            continue
        title = pr["title"] if pr is not None else subject
        match = _TITLE.match(title.strip())
        if match:
            change = Change(
                type=match["type"],
                scope=match["scope"],
                description=_PR_SUFFIX.sub("", match["desc"].strip()),
                breaking=bool(match["bang"]) or footer,
                pr=pr["number"] if pr is not None else None,
                sha=record["sha"],
            )
        else:
            change = Change(None, None, title.strip(), footer, pr and pr["number"], record["sha"])
        changes.append(change)
        if change.pr is not None:
            by_pr[change.pr] = change
    return changes


def plan(changes: list[Change]) -> str | None:
    """The part of the version these changes bump, or None if they release nothing."""
    if any(c.breaking for c in changes):
        return "major"
    if any(c.type == "feat" for c in changes):
        return "minor"
    if any(c.type in _PATCH_TYPES for c in changes):
        return "patch"
    return None


def bumped(version: str, part: str) -> str:
    """``version`` with ``part`` incremented and the parts after it reset."""
    major, minor, patch = (int(x) for x in version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def changelog_entry(changes: list[Change], notes: str) -> str:
    """The body of a release's CHANGELOG entry.

    Notes written by hand under ``[Unreleased]`` are the entry, followed by the pull
    requests that released it. Without notes, the entry is generated from the titles.
    """
    releasing = [c for c in changes if c.breaking or c.type == "feat" or c.type in _PATCH_TYPES]
    if notes:
        lines = [c.line() for c in releasing]
        return notes + ("\n\n### Pull requests\n\n" + "\n".join(lines) if lines else "")
    blocks = []
    breaking = [c for c in releasing if c.breaking]
    if breaking:
        blocks.append("### Breaking changes\n\n" + "\n".join(c.line() for c in breaking))
    for type_, heading in _SECTIONS:
        lines = [c.line() for c in releasing if c.type == type_ and not c.breaking]
        if lines:
            blocks.append(f"### {heading}\n\n" + "\n".join(lines))
    return "\n\n".join(blocks) or "No changes that affect users."


def _sub(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text("utf-8")
    new, n = re.subn(pattern, replacement, text, count=1, flags=re.M)
    if n == 0:
        raise SystemExit(f"{path}: nothing matched {pattern!r}")
    path.write_text(new, "utf-8")


def current_version(root: Path) -> str:
    match = re.search(
        r'^version = "(\d+\.\d+\.\d+)"', (root / "pyproject.toml").read_text("utf-8"), re.M
    )
    if not match:
        raise SystemExit("pyproject.toml: no version")
    return match.group(1)


def write_changelog(path: Path, old: str, new: str, date: str, changes: list[Change]) -> None:
    """Move ``[Unreleased]`` into ``[new] - date`` and leave an empty one above it."""
    text = path.read_text("utf-8")
    head = "## [Unreleased]\n"
    start = text.index(head) + len(head)
    end = text.index("\n## [", start)
    entry = changelog_entry(changes, text[start:end].strip())
    text = text[:start] + f"\n## [{new}] - {date}\n\n{entry}\n" + text[end:]
    unreleased = f"[Unreleased]: {REPO_URL}/compare/v{old}...HEAD\n"
    if unreleased not in text:
        raise SystemExit(f"{path}: no {unreleased.strip()!r} link")
    text = text.replace(
        unreleased,
        f"[Unreleased]: {REPO_URL}/compare/v{new}...HEAD\n"
        f"[{new}]: {REPO_URL}/compare/v{old}...v{new}\n",
    )
    path.write_text(text, "utf-8")


def apply(root: Path, changes: list[Change], part: str, date: str) -> str:
    """Bump every file that carries the version; return the new version."""
    old = current_version(root)
    new = bumped(old, part)
    v_old = re.escape(old)
    write_changelog(root / "CHANGELOG.md", old, new, date, changes)
    _sub(root / "pyproject.toml", rf'^version = "{v_old}"', f'version = "{new}"')
    _sub(root / "CITATION.cff", rf"^version: {v_old}$", f"version: {new}")
    _sub(root / "CITATION.cff", r'^date-released: "[0-9-]+"$', f'date-released: "{date}"')
    _sub(root / "codemeta.json", rf'^  "version": "{v_old}",$', f'  "version": "{new}",')
    return new


def notes(root: Path, version: str) -> str:
    """The CHANGELOG entry of ``version``, without its heading."""
    text = (root / "CHANGELOG.md").read_text("utf-8")
    match = re.search(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|^\[Unreleased\]:)", text, re.M | re.S
    )
    if not match:
        raise SystemExit(f"CHANGELOG.md: no entry for {version}")
    return match.group(1).strip() + "\n"


def _load(path: Path) -> list[Change]:
    lines = path.read_text("utf-8").splitlines()
    return parse_changes([json.loads(line) for line in lines if line.strip()])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "apply"):
        p = sub.add_parser(name)
        p.add_argument("changes", type=Path)
        p.add_argument("--part", choices=("auto", *PARTS), default="auto")
        if name == "apply":
            p.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    n = sub.add_parser("notes")
    n.add_argument("version")
    args = parser.parse_args(argv)

    if args.command == "notes":
        if not _VERSION.match(args.version):
            raise SystemExit(f"not a version: {args.version}")
        sys.stdout.write(notes(args.root, args.version))
        return 0

    changes = _load(args.changes)
    part = plan(changes) if args.part == "auto" else args.part
    if args.command == "plan":
        print(part or "")
        return 0
    if part is None:
        raise SystemExit("nothing merged since the last release calls for one")
    print(apply(args.root, changes, part, args.date))
    return 0


if __name__ == "__main__":
    sys.exit(main())
