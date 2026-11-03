"""The release script, run against copies of the real files it edits."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FILES = ["pyproject.toml", "CITATION.cff", "codemeta.json", "CHANGELOG.md"]

_spec = importlib.util.spec_from_file_location(
    "release", ROOT / "scripts" / "release" / "release.py"
)
release = importlib.util.module_from_spec(_spec)
sys.modules["release"] = release  # dataclasses look their module up by name
_spec.loader.exec_module(release)


def record(subject: str, pr: int | None = None, title: str | None = None, body: str = ""):
    sha = f"{abs(hash((subject, pr))):040x}"[:40]
    return {
        "sha": sha,
        "subject": subject,
        "body": body,
        "pr": {"number": pr, "title": title or subject} if pr else None,
    }


def changes(*records):
    return release.parse_changes(list(records))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for name in FILES:
        shutil.copy(ROOT / name, tmp_path / name)
    return tmp_path


def write_changes(path: Path, *records) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


class TestPlan:
    @pytest.mark.parametrize(
        "titles, expected",
        [
            (["docs: explain the algorithms", "ci: lint examples"], None),
            (["chore: tidy"], None),
            (["fix(cli): honour --no-color"], "patch"),
            (["perf: cache manifests"], "patch"),
            (["revert: undo the cache"], "patch"),
            (["deps: bump textual"], "patch"),
            (["docs: x", "fix: y", "feat(api): z"], "minor"),
            (["feat!: drop include_buildtool"], "major"),
            (["fix(core)!: stop following buildtool deps", "feat: z"], "major"),
            (["Update README"], None),
            (["feature: not a conventional type"], None),
        ],
    )
    def test_highest_bump_among_the_titles_wins(self, titles, expected) -> None:
        recs = [record(t, pr=i + 1) for i, t in enumerate(titles)]
        assert release.plan(changes(*recs)) == expected

    def test_a_breaking_change_footer_is_major(self) -> None:
        rec = record("fix: tidy", pr=3, body="Details.\n\nBREAKING CHANGE: --foo is gone")
        assert release.plan(changes(rec)) == "major"

    def test_the_pull_request_title_wins_over_the_commit_subject(self) -> None:
        # A single-commit PR squash-merged with its commit message, not its title.
        rec = record("wip", pr=7, title="feat(tui): search everything")
        [change] = changes(rec)
        assert (change.type, change.scope, change.description) == (
            "feat",
            "tui",
            "search everything",
        )
        assert release.plan([change]) == "minor"

    def test_commits_of_one_pull_request_count_once(self) -> None:
        # A merge commit and the commits it brought in all map to the same PR.
        merged = [
            record("Merge pull request #9 from x/y", pr=9, title="fix: a"),
            record("first try", pr=9, title="fix: a"),
            record("second try", pr=9, title="fix: a", body="BREAKING CHANGE: b"),
        ]
        result = changes(*merged)
        assert len(result) == 1
        assert result[0].breaking

    def test_squash_suffix_and_release_commits(self) -> None:
        result = changes(
            record("chore(release): v1.1.0"),
            record("fix(core): honour conditions (#20)"),
        )
        assert [c.description for c in result] == ["honour conditions"]
        assert result[0].link.startswith("[")


class TestBumped:
    def test_parts(self) -> None:
        assert release.bumped("1.2.3", "patch") == "1.2.4"
        assert release.bumped("1.2.3", "minor") == "1.3.0"
        assert release.bumped("1.2.3", "major") == "2.0.0"


class TestTheRealFiles:
    def test_every_file_carries_the_same_version(self) -> None:
        version = release.current_version(ROOT)
        assert re.search(
            rf"^version: {re.escape(version)}$", (ROOT / "CITATION.cff").read_text(), re.M
        )
        assert json.loads((ROOT / "codemeta.json").read_text())["version"] == version
        assert (
            f"[Unreleased]: {release.REPO_URL}/compare/v{version}...HEAD"
            in (ROOT / "CHANGELOG.md").read_text()
        )

    def test_changelog_has_an_unreleased_section(self) -> None:
        assert "\n## [Unreleased]\n" in (ROOT / "CHANGELOG.md").read_text()


class TestApply:
    def test_bumps_every_file_and_keeps_hand_written_notes(self, repo: Path) -> None:
        old = release.current_version(repo)
        unreleased = (repo / "CHANGELOG.md").read_text().split("## [Unreleased]\n", 1)[1]
        hand_written = unreleased.split("\n## [", 1)[0].strip()
        new = release.apply(
            repo,
            changes(
                record("docs: guide", pr=23),
                record("feat(api): make rostree a library", pr=22),
                record("fix(cli): honour --no-color", pr=21),
            ),
            "minor",
            "2030-01-02",
        )
        assert new == release.bumped(old, "minor")

        assert release.current_version(repo) == new
        cff = (repo / "CITATION.cff").read_text()
        assert f"\nversion: {new}\n" in cff and '\ndate-released: "2030-01-02"\n' in cff
        assert json.loads((repo / "codemeta.json").read_text())["version"] == new

        log = (repo / "CHANGELOG.md").read_text()
        assert f"## [Unreleased]\n\n## [{new}] - 2030-01-02\n\n" in log
        entry = release.notes(repo, new)
        if hand_written:
            assert entry.startswith(hand_written[:200])
            assert "### Pull requests" in entry
        assert f"- **api:** make rostree a library ([#22]({release.REPO_URL}/pull/22))" in entry
        assert "- **cli:** honour --no-color" in entry
        assert "guide" not in entry.split("### Pull requests")[-1]  # docs: does not release
        assert f"[Unreleased]: {release.REPO_URL}/compare/v{new}...HEAD\n" in log
        assert f"[{new}]: {release.REPO_URL}/compare/v{old}...v{new}\n" in log
        # The previous release's entry is untouched and still found on its own.
        assert release.notes(repo, "1.0.0").strip()
        assert "make rostree a library" not in release.notes(repo, "1.0.0")

    def test_generates_the_entry_when_nothing_was_written(self, repo: Path) -> None:
        log = repo / "CHANGELOG.md"
        text = log.read_text()
        start = text.index("## [Unreleased]\n") + len("## [Unreleased]\n")
        log.write_text(text[:start] + text[text.index("\n## [", start) :])
        new = release.apply(
            repo,
            changes(
                record("feat!: drop include_buildtool", pr=30),
                record("feat(tui): search", pr=31),
                record("fix: crash", pr=32),
                record("perf: faster", pr=33),
            ),
            "major",
            "2030-01-02",
        )
        entry = release.notes(repo, new)
        assert entry.index("### Breaking changes") < entry.index("### Features")
        assert entry.index("### Features") < entry.index("### Bug fixes")
        assert entry.index("### Bug fixes") < entry.index("### Performance")
        assert "drop include_buildtool" in entry.split("### Features")[0]
        assert "### Pull requests" not in entry


class TestCommandLine:
    def test_plan_then_apply(self, repo: Path, tmp_path: Path, capsys) -> None:
        jsonl = write_changes(
            tmp_path / "changes.jsonl",
            record("fix(core): honour conditions (#20)", pr=20),
            record("docs: guide", pr=23),
        )
        assert release.main(["--root", str(repo), "plan", str(jsonl)]) == 0
        assert capsys.readouterr().out == "patch\n"

        old = release.current_version(repo)
        argv = ["--root", str(repo), "apply", str(jsonl), "--date", "2030-01-02"]
        assert release.main(argv) == 0
        assert capsys.readouterr().out == release.bumped(old, "patch") + "\n"

    def test_nothing_to_release(self, repo: Path, tmp_path: Path, capsys) -> None:
        jsonl = write_changes(tmp_path / "changes.jsonl", record("docs: guide", pr=23))
        assert release.main(["--root", str(repo), "plan", str(jsonl)]) == 0
        assert capsys.readouterr().out == "\n"
        before = (repo / "pyproject.toml").read_text()
        with pytest.raises(SystemExit, match="nothing merged"):
            release.main(["--root", str(repo), "apply", str(jsonl)])
        assert (repo / "pyproject.toml").read_text() == before

    def test_a_forced_part_overrides_the_titles(self, repo: Path, tmp_path: Path, capsys) -> None:
        jsonl = write_changes(tmp_path / "changes.jsonl", record("docs: guide", pr=23))
        assert release.main(["--root", str(repo), "plan", str(jsonl), "--part", "patch"]) == 0
        assert capsys.readouterr().out == "patch\n"

    def test_notes_rejects_a_non_version(self, repo: Path) -> None:
        with pytest.raises(SystemExit, match="not a version"):
            release.main(["--root", str(repo), "notes", "1.0.0) || rm"])
