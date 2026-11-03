"""The questions rostree answers, as plain functions: why, who depends, what changed."""

from __future__ import annotations

from pathlib import Path

from rostree.core.analysis import (
    DependencyDiff,
    dependency_versions,
    dependents,
    diff_dependencies,
    shortest_paths,
)
from rostree.core.filters import FilterReport, PackageFilter
from rostree.core.index import PackageEntry, PackageIndex, SourceKind
from rostree.core.tree import DependencyGraph
from tests.conftest import write_package


def graph(edges: dict[str, list[str]], *, roots=("a",), missing=()) -> DependencyGraph:
    return DependencyGraph(roots=list(roots), edges=edges, missing=set(missing))


class TestShortestPaths:
    def test_every_route_of_minimal_length(self) -> None:
        # a -> b -> d, a -> c -> d, and a longer a -> b -> c -> d that must not appear
        g = graph({"a": ["b", "c"], "b": ["d", "c"], "c": ["d"], "d": []})
        assert shortest_paths(g, "a", "d") == [["a", "b", "d"], ["a", "c", "d"]]

    def test_limit(self) -> None:
        g = graph({"a": ["b", "c"], "b": ["d"], "c": ["d"], "d": []})
        assert len(shortest_paths(g, "a", "d", limit=1)) == 1

    def test_no_path_is_empty(self) -> None:
        assert shortest_paths(graph({"a": ["b"], "b": []}), "a", "z") == []

    def test_same_package(self) -> None:
        assert shortest_paths(graph({"a": []}), "a", "a") == [["a"]]

    def test_survives_a_cycle(self) -> None:
        g = graph({"a": ["b"], "b": ["a", "c"], "c": []})
        assert shortest_paths(g, "a", "c") == [["a", "b", "c"]]

    def test_reaches_an_unresolved_name(self) -> None:
        g = graph({"a": ["b"], "b": ["eigen"]}, missing={"eigen"})
        assert shortest_paths(g, "a", "eigen") == [["a", "b", "eigen"]]


def index_of(tmp_path: Path, manifests: dict[str, list[str]], kinds=None) -> PackageIndex:
    """A real index over real manifests, so reverse_dependencies parses them."""
    entries = {}
    for name, deps in manifests.items():
        manifest = write_package(tmp_path, name, depends=deps)
        kind = (kinds or {}).get(name, SourceKind.SOURCE)
        entries[name] = PackageEntry(
            name=name, manifest=manifest, kind=kind, origin=tmp_path, label="Source"
        )
    return PackageIndex(entries=entries)


class TestDependents:
    def test_direct_and_transitive(self, tmp_path: Path) -> None:
        idx = index_of(tmp_path, {"msgs": [], "lib": ["msgs"], "app": ["lib"], "tool": ["msgs"]})
        assert dependents(idx, "msgs") == ["lib", "tool"]
        assert dependents(idx, "msgs", transitive=True) == ["app", "lib", "tool"]

    def test_a_cycle_never_lists_the_package_itself(self, tmp_path: Path) -> None:
        idx = index_of(tmp_path, {"a": ["b"], "b": ["a"]})
        assert dependents(idx, "a", transitive=True) == ["b"]

    def test_the_filter_trims_the_answer_not_the_walk(self, tmp_path: Path) -> None:
        """Excluding lib must not hide app, which breaks *through* lib."""
        idx = index_of(tmp_path, {"msgs": [], "lib": ["msgs"], "app": ["lib"]})
        report = FilterReport()
        names = dependents(
            idx,
            "msgs",
            transitive=True,
            package_filter=PackageFilter(exclude=("lib",)),
            report=report,
        )
        assert names == ["app"]
        assert report.excluded == {"lib"}

    def test_respects_dependency_tags(self, tmp_path: Path) -> None:
        idx = index_of(tmp_path, {"msgs": []})
        test_pkg = tmp_path / "tester" / "package.xml"
        test_pkg.parent.mkdir()
        test_pkg.write_text(
            '<package format="3"><name>tester</name><version>1.0.0</version>'
            "<description>x</description><test_depend>msgs</test_depend></package>"
        )
        idx.entries["tester"] = PackageEntry(
            name="tester", manifest=test_pkg, kind=SourceKind.SOURCE, origin=tmp_path, label="S"
        )
        assert dependents(idx, "msgs") == ["tester"]
        assert dependents(idx, "msgs", include_tags=("depend", "exec_depend")) == []


class TestDependencyVersions:
    def test_versions_with_missing_as_empty(self, tmp_path: Path) -> None:
        from rostree.core.parser import PackageInfo

        g = graph({"a": ["b", "eigen"], "b": []}, missing={"eigen"})
        g.packages = {
            "a": PackageInfo("a", "1.0", "", tmp_path, []),
            "b": PackageInfo("b", "2.0", "", tmp_path, []),
        }
        assert dependency_versions(g) == {"a": "1.0", "b": "2.0", "eigen": ""}
        assert dependency_versions(g, exclude=["a"]) == {"b": "2.0", "eigen": ""}


class TestDiffDependencies:
    def test_added_removed_changed(self) -> None:
        diff = diff_dependencies(
            {"keep": "1.0", "gone": "1.0", "bump": "1.0"},
            {"keep": "1.0", "new": "1.0", "bump": "2.0"},
            before_name="snap",
            after_name="pkg",
        )
        assert diff.added == ["new"]
        assert diff.removed == ["gone"]
        assert diff.changed == {"bump": ("1.0", "2.0")}
        assert bool(diff) is True

    def test_now_resolving_is_not_a_version_change(self) -> None:
        """Unknown -> known has nothing to compare against."""
        assert not diff_dependencies({"x": ""}, {"x": "1.0"})

    def test_no_drift_is_falsy(self) -> None:
        assert not diff_dependencies({"a": "1"}, {"a": "1"})

    def test_to_dict_is_the_cli_json_shape(self) -> None:
        diff = DependencyDiff("a", "b", added=["n"], changed={"x": ("1", "2")})
        assert diff.to_dict() == {
            "before": "a",
            "after": "b",
            "added": ["n"],
            "removed": [],
            "changed": {"x": {"from": "1", "to": "2"}},
        }
