"""Tests for the cached package index."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

from rostree.core.index import (
    SourceKind,
    build_index,
    clear_index_cache,
    get_index,
    iter_manifests_in_prefix,
    iter_manifests_in_source_tree,
)
from tests.conftest import write_package

EMPTY_ENV = {
    "AMENT_PREFIX_PATH": "",
    "COLCON_PREFIX_PATH": "",
    "ROS2_WORKSPACE": "",
    "COLCON_WORKSPACE": "",
}


def make_prefix(root: Path, name: str = "install", **packages: list[str]) -> Path:
    """Create <root>/<name>/share/<pkg>/package.xml for each named package."""
    share = root / name / "share"
    share.mkdir(parents=True, exist_ok=True)
    for pkg, deps in packages.items():
        write_package(share, pkg, depends=deps)
    return root / name


class TestManifestDiscovery:
    """Tests for the two low-level scanners."""

    def test_prefix_scan_finds_installed_packages(self, tmp_path: Path) -> None:
        prefix = make_prefix(tmp_path, alpha=[], beta=["alpha"])
        names = sorted(m.parent.name for m in iter_manifests_in_prefix(prefix))
        assert names == ["alpha", "beta"]

    def test_prefix_scan_ignores_dirs_without_manifests(self, tmp_path: Path) -> None:
        prefix = make_prefix(tmp_path, alpha=[])
        (prefix / "share" / "not_a_package").mkdir()
        names = [m.parent.name for m in iter_manifests_in_prefix(prefix)]
        assert names == ["alpha"]

    def test_prefix_scan_tolerates_missing_share(self, tmp_path: Path) -> None:
        assert list(iter_manifests_in_prefix(tmp_path / "nope")) == []

    def test_source_scan_prunes_build_artifacts(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        write_package(src, "real_pkg")
        for junk in ("build", "install", "log", ".git"):
            write_package(tmp_path / junk, f"{junk}_pkg")
        # Those live outside src, so also plant one inside a pruned directory.
        write_package(src / "build", "stale_copy")
        names = sorted(m.parent.name for m in iter_manifests_in_source_tree(src))
        assert names == ["real_pkg"]

    def test_source_scan_honours_colcon_ignore(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        write_package(src, "kept")
        write_package(src / "vendor", "skipped")
        (src / "vendor" / "COLCON_IGNORE").write_text("")
        names = sorted(m.parent.name for m in iter_manifests_in_source_tree(src))
        assert names == ["kept"]

    def test_source_scan_does_not_descend_into_a_package(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        write_package(src, "outer")
        write_package(src / "outer", "nested")
        names = [m.parent.name for m in iter_manifests_in_source_tree(src)]
        assert names == ["outer"]


class TestBuildIndex:
    """Tests for index construction and precedence."""

    def test_classifies_system_workspace_and_source(self, tmp_path: Path) -> None:
        system = tmp_path / "opt" / "ros" / "jazzy"
        (system / "share").mkdir(parents=True)
        write_package(system / "share", "rclcpp")
        ws = tmp_path / "ws"
        make_prefix(ws, ament_pkg=[])
        src = ws / "src"
        write_package(src, "unbuilt_pkg")

        env = dict(
            EMPTY_ENV,
            AMENT_PREFIX_PATH=os.pathsep.join([str(system), str(ws / "install")]),
        )
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch("rostree.core.index.is_system_prefix", lambda p: p == system):
                index = build_index()

        assert index.get("rclcpp").kind is SourceKind.SYSTEM
        assert index.get("ament_pkg").kind is SourceKind.WORKSPACE
        assert index.get("unbuilt_pkg").kind is SourceKind.SOURCE
        assert index.workspace_names() == ["ament_pkg", "unbuilt_pkg"]
        assert index.by_kind(SourceKind.SYSTEM) == ["rclcpp"]

    def test_install_space_wins_over_source(self, tmp_path: Path) -> None:
        ws = tmp_path / "ws"
        make_prefix(ws, shared=[])
        write_package(ws / "src", "shared", version="9.9.9")
        env = dict(EMPTY_ENV, AMENT_PREFIX_PATH=str(ws / "install"))
        with mock.patch.dict(os.environ, env, clear=False):
            index = build_index()
        assert index.get("shared").kind is SourceKind.WORKSPACE
        assert "install" in str(index.resolve("shared"))

    def test_first_prefix_wins(self, tmp_path: Path) -> None:
        first = make_prefix(tmp_path / "a", dup=[])
        second = make_prefix(tmp_path / "b", dup=[])
        env = dict(EMPTY_ENV, AMENT_PREFIX_PATH=os.pathsep.join([str(first), str(second)]))
        with mock.patch.dict(os.environ, env, clear=False):
            index = build_index()
        assert index.resolve("dup").is_relative_to(first)

    def test_extra_roots_are_labelled_added(self, tmp_path: Path) -> None:
        extra = tmp_path / "extra"
        write_package(extra, "vendor_pkg")
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            index = build_index(extra_source_roots=[extra])
        entry = index.get("vendor_pkg")
        assert entry.kind is SourceKind.ADDED
        assert entry.label.startswith("Added (")
        assert entry.directory == extra / "vendor_pkg"

    def test_reports_progress(self, tmp_path: Path) -> None:
        prefix = make_prefix(tmp_path, alpha=[])
        seen: list[str] = []
        env = dict(EMPTY_ENV, AMENT_PREFIX_PATH=str(prefix))
        with mock.patch.dict(os.environ, env, clear=False):
            build_index(on_progress=seen.append)
        assert any("Indexing" in message for message in seen)

    def test_unknown_package_resolves_to_none(self, tmp_path: Path) -> None:
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            index = build_index()
        assert index.resolve("no_such_pkg") is None
        assert index.get("no_such_pkg") is None
        assert "no_such_pkg" not in index


class TestReverseDependencies:
    """Tests for the reverse dependency map."""

    def test_maps_dependents(self, tmp_path: Path) -> None:
        prefix = make_prefix(tmp_path, leaf=[], middle=["leaf"], top=["middle", "leaf"])
        env = dict(EMPTY_ENV, AMENT_PREFIX_PATH=str(prefix))
        with mock.patch.dict(os.environ, env, clear=False):
            index = build_index()
        reverse = index.reverse_dependencies()
        assert reverse["leaf"] == {"middle", "top"}
        assert reverse["middle"] == {"top"}
        assert "top" not in reverse

    def test_result_is_cached_and_reports_progress(self, tmp_path: Path) -> None:
        prefix = make_prefix(tmp_path, leaf=[], top=["leaf"])
        env = dict(EMPTY_ENV, AMENT_PREFIX_PATH=str(prefix))
        with mock.patch.dict(os.environ, env, clear=False):
            index = build_index()
        seen: list[tuple[int, int]] = []
        first = index.reverse_dependencies(on_progress=lambda i, n: seen.append((i, n)))
        second = index.reverse_dependencies()
        assert first is second
        assert seen[-1] == (2, 2)


class TestIndexCache:
    """Tests for the process-wide cache."""

    def test_same_environment_returns_the_same_index(self, tmp_path: Path) -> None:
        prefix = make_prefix(tmp_path, alpha=[])
        env = dict(EMPTY_ENV, AMENT_PREFIX_PATH=str(prefix))
        with mock.patch.dict(os.environ, env, clear=False):
            first = get_index()
            second = get_index()
            assert first is second

    def test_refresh_rebuilds(self, tmp_path: Path) -> None:
        prefix = make_prefix(tmp_path, alpha=[])
        env = dict(EMPTY_ENV, AMENT_PREFIX_PATH=str(prefix))
        with mock.patch.dict(os.environ, env, clear=False):
            first = get_index()
            write_package(prefix / "share", "beta")
            assert "beta" not in get_index()
            refreshed = get_index(refresh=True)
            assert refreshed is not first
            assert "beta" in refreshed

    def test_changing_environment_rebuilds(self, tmp_path: Path) -> None:
        one = make_prefix(tmp_path / "one", alpha=[])
        two = make_prefix(tmp_path / "two", beta=[])
        with mock.patch.dict(os.environ, dict(EMPTY_ENV, AMENT_PREFIX_PATH=str(one))):
            assert "alpha" in get_index()
        with mock.patch.dict(os.environ, dict(EMPTY_ENV, AMENT_PREFIX_PATH=str(two))):
            index = get_index()
            assert "beta" in index
            assert "alpha" not in index

    def test_clear_cache_discards_everything(self, tmp_path: Path) -> None:
        prefix = make_prefix(tmp_path, alpha=[])
        env = dict(EMPTY_ENV, AMENT_PREFIX_PATH=str(prefix))
        with mock.patch.dict(os.environ, env, clear=False):
            first = get_index()
            clear_index_cache()
            assert get_index() is not first


class TestReverseDependencyCaching:
    """The cache must not answer one tag set with another's map."""

    def test_runtime_and_full_maps_do_not_share_a_cache_entry(self, tmp_path: Path) -> None:
        share = tmp_path / "install" / "share"
        share.mkdir(parents=True)
        write_package(share, "runtime_dep")
        write_package(share, "build_dep")
        (share / "app").mkdir()
        (share / "app" / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
  <name>app</name>
  <version>1.0.0</version>
  <description>d</description>
  <exec_depend>runtime_dep</exec_depend>
  <build_depend>build_dep</build_depend>
</package>
"""
        )
        env = dict(EMPTY_ENV, AMENT_PREFIX_PATH=str(tmp_path / "install"))
        with mock.patch.dict(os.environ, env, clear=False):
            index = build_index()

        runtime = index.reverse_dependencies(include_tags=("depend", "exec_depend"))
        full = index.reverse_dependencies()
        assert runtime.get("build_dep") is None
        assert full["build_dep"] == {"app"}
        # ...and asking again in the original order still gives the original answer.
        assert index.reverse_dependencies(include_tags=("depend", "exec_depend")) == runtime
