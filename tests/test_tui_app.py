"""Interactive tests for the TUI, driven through Textual's pilot harness."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest import mock

from textual.widgets import Static, Tree

from rostree.tui.app import DepTreeApp
from tests.conftest import write_package


def _env(*, ament: Path | None = None) -> dict[str, str]:
    return {
        "AMENT_PREFIX_PATH": str(ament) if ament else "",
        "COLCON_PREFIX_PATH": "",
        "ROS2_WORKSPACE": "",
        "COLCON_WORKSPACE": "",
    }


def build_install_space(root: Path) -> Path:
    """
    A small install space shaped like the real thing.

    robot_app -> middleware -> shared_utils -> rcutils_like -> logging_backend
    robot_app -> shared_utils   (so shared_utils is reached twice)
    """
    share = root / "install" / "share"
    share.mkdir(parents=True)
    write_package(share, "logging_backend", description="Leaf utility package")
    write_package(share, "rcutils_like", description="C utilities", depends=["logging_backend"])
    write_package(share, "shared_utils", description="Low level helpers", depends=["rcutils_like"])
    write_package(share, "middleware", depends=["shared_utils"])
    write_package(share, "robot_app", depends=["middleware", "shared_utils"])
    return root / "install"


async def _settle(app, pilot, predicate, *, tries: int = 200) -> None:
    """Pump the event loop until a condition holds (or give up)."""
    for _ in range(tries):
        if predicate():
            return
        await pilot.pause()
    await pilot.pause()


async def _start(app, pilot) -> None:
    """Dismiss the welcome screen and wait for the background scan to land."""
    await pilot.press("enter")
    for _ in range(200):
        if app._packages_cache is not None and not app._building:
            break
        await pilot.pause()
    await pilot.pause()


def _tree(app) -> Tree:
    return app.query_one("#dep_tree", Tree)


def _labels(node) -> list[str]:
    """Plain text of each child row (Textual renders markup away)."""
    return [str(child.label) for child in node.children]


async def _apply_filter(app, pilot, text: str) -> None:
    """Type into the filter box and wait for the debounced redraw."""
    await pilot.press("slash")
    await pilot.pause()
    for ch in text:
        await pilot.press(ch)
    await asyncio.sleep(app.FILTER_DEBOUNCE * 3)
    await pilot.pause()


class TestPackageList:
    """The package list: scanning, filtering, opening a package."""

    def test_lists_packages_after_background_scan(self, tmp_path: Path) -> None:
        prefix = build_install_space(tmp_path)

        async def scenario() -> None:
            with mock.patch.dict(os.environ, _env(ament=prefix), clear=False):
                app = DepTreeApp()
                async with app.run_test(size=(120, 40)) as pilot:
                    await _start(app, pilot)
                    assert app._packages_cache is not None
                    names = [n for names in app._packages_cache.values() for n in names]
                    assert set(names) == {
                        "robot_app",
                        "middleware",
                        "shared_utils",
                        "rcutils_like",
                        "logging_backend",
                    }
                    assert "5" in app.status_text

        asyncio.run(scenario())

    def test_filter_narrows_the_list(self, tmp_path: Path) -> None:
        prefix = build_install_space(tmp_path)

        async def scenario() -> None:
            with mock.patch.dict(os.environ, _env(ament=prefix), clear=False):
                app = DepTreeApp()
                async with app.run_test(size=(120, 40)) as pilot:
                    await _start(app, pilot)
                    await _apply_filter(app, pilot, "middle")
                    assert app._filter == "middle"
                    section = _tree(app).root.children[0]
                    assert _labels(section) == ["middleware"]  # names only in the package list

        asyncio.run(scenario())

    def test_escape_clears_the_filter(self, tmp_path: Path) -> None:
        prefix = build_install_space(tmp_path)

        async def scenario() -> None:
            with mock.patch.dict(os.environ, _env(ament=prefix), clear=False):
                app = DepTreeApp()
                async with app.run_test(size=(120, 40)) as pilot:
                    await _start(app, pilot)
                    await _apply_filter(app, pilot, "middle")
                    await pilot.press("escape")  # leave the input
                    await pilot.pause()
                    await pilot.press("escape")  # clear the filter
                    await asyncio.sleep(app.FILTER_DEBOUNCE * 3)
                    await pilot.pause()
                    assert app._filter == ""

        asyncio.run(scenario())


class TestDependencyTree:
    """Opening, expanding and navigating a dependency tree."""

    def test_opening_a_package_builds_its_tree_in_the_background(self, tmp_path: Path) -> None:
        prefix = build_install_space(tmp_path)

        async def scenario() -> None:
            with mock.patch.dict(os.environ, _env(ament=prefix), clear=False):
                app = DepTreeApp(root_package="robot_app")
                async with app.run_test(size=(120, 40)) as pilot:
                    await _start(app, pilot)
                    await _settle(app, pilot, lambda: app._root_node is not None)
                    assert app._root_node is not None
                    assert app._root_node.name == "robot_app"
                    # The build never blocks the UI thread.
                    assert app._building is False
                    labels = _labels(_tree(app).root)
                    assert any("middleware" in label for label in labels)

        asyncio.run(scenario())

    def test_children_are_materialised_only_when_expanded(self, tmp_path: Path) -> None:
        prefix = build_install_space(tmp_path)

        async def scenario() -> None:
            with mock.patch.dict(os.environ, _env(ament=prefix), clear=False):
                app = DepTreeApp(root_package="robot_app")
                async with app.run_test(size=(120, 40)) as pilot:
                    await _start(app, pilot)
                    await _settle(app, pilot, lambda: app._root_node is not None)
                    root = _tree(app).root
                    shared = next(c for c in root.children if "shared_utils" in str(c.label))
                    rcutils = next(c for c in shared.children if "rcutils_like" in str(c.label))
                    # rcutils_like sits past the initial two levels of expansion, so
                    # its own row exists but its children have not been built yet.
                    assert list(rcutils.children) == []
                    assert getattr(rcutils, "_rostree_filled", False) is False
                    rcutils.expand()
                    await pilot.pause()
                    assert _labels(rcutils) == ["logging_backend v1.0.0"]
                    assert rcutils._rostree_filled is True

        asyncio.run(scenario())

    def test_repeated_packages_are_marked_not_re_expanded(self, tmp_path: Path) -> None:
        prefix = build_install_space(tmp_path)

        async def scenario() -> None:
            with mock.patch.dict(os.environ, _env(ament=prefix), clear=False):
                app = DepTreeApp(root_package="robot_app")
                async with app.run_test(size=(120, 40)) as pilot:
                    await _start(app, pilot)
                    await _settle(app, pilot, lambda: app._root_node is not None)
                    root = _tree(app).root
                    middleware = next(c for c in root.children if "middleware" in str(c.label))
                    # shared_utils is expanded once, at its shallowest position
                    # (directly under robot_app); under middleware it is a reference.
                    direct = next(c for c in root.children if "shared_utils" in str(c.label))
                    nested = next(c for c in middleware.children if "shared_utils" in str(c.label))
                    assert "shown above" not in str(direct.label)
                    assert "shown above" in str(nested.label)

        asyncio.run(scenario())

    def test_escape_returns_to_the_package_list(self, tmp_path: Path) -> None:
        prefix = build_install_space(tmp_path)

        async def scenario() -> None:
            with mock.patch.dict(os.environ, _env(ament=prefix), clear=False):
                app = DepTreeApp(root_package="robot_app")
                async with app.run_test(size=(120, 40)) as pilot:
                    await _start(app, pilot)
                    await _settle(app, pilot, lambda: app._root_node is not None)
                    await pilot.press("escape")
                    await pilot.pause()
                    assert app._root_package is None
                    assert "Packages by source" in str(_tree(app).root.label)

        asyncio.run(scenario())


class TestExtraViews:
    """Reverse dependencies, details panel, scope toggle and help."""

    def test_reverse_view_lists_dependents(self, tmp_path: Path) -> None:
        prefix = build_install_space(tmp_path)

        async def scenario() -> None:
            with mock.patch.dict(os.environ, _env(ament=prefix), clear=False):
                app = DepTreeApp(root_package="shared_utils")
                async with app.run_test(size=(120, 40)) as pilot:
                    await _start(app, pilot)
                    await _settle(app, pilot, lambda: app._root_node is not None)
                    await pilot.press("v")
                    await _settle(app, pilot, lambda: "depending on" in str(_tree(app).root.label))
                    labels = _labels(_tree(app).root)
                    assert any("middleware" in label for label in labels)
                    assert any("robot_app" in label for label in labels)

        asyncio.run(scenario())

    def test_details_panel_toggles(self, tmp_path: Path) -> None:
        prefix = build_install_space(tmp_path)

        async def scenario() -> None:
            with mock.patch.dict(os.environ, _env(ament=prefix), clear=False):
                app = DepTreeApp()
                async with app.run_test(size=(120, 40)) as pilot:
                    await _start(app, pilot)
                    details = app.query_one("#details", Static)
                    assert not details.has_class("hidden")
                    await pilot.press("d")
                    await pilot.pause()
                    assert details.has_class("hidden")
                    await pilot.press("d")
                    await pilot.pause()
                    assert not details.has_class("hidden")

        asyncio.run(scenario())

    def test_scope_toggle_switches_dependency_kinds(self, tmp_path: Path) -> None:
        prefix = build_install_space(tmp_path)

        async def scenario() -> None:
            with mock.patch.dict(os.environ, _env(ament=prefix), clear=False):
                app = DepTreeApp()
                async with app.run_test(size=(120, 40)) as pilot:
                    await _start(app, pilot)
                    assert app._runtime_only is True
                    await pilot.press("t")
                    await pilot.pause()
                    assert app._runtime_only is False

        asyncio.run(scenario())

    def test_help_screen_opens_and_closes(self, tmp_path: Path) -> None:
        prefix = build_install_space(tmp_path)

        async def scenario() -> None:
            with mock.patch.dict(os.environ, _env(ament=prefix), clear=False):
                app = DepTreeApp()
                async with app.run_test(size=(120, 40)) as pilot:
                    await _start(app, pilot)
                    await pilot.press("question_mark")
                    await pilot.pause()
                    assert app.screen_stack[-1].__class__.__name__ == "HelpScreen"
                    await pilot.press("escape")
                    await pilot.pause()
                    assert app.screen_stack[-1].__class__.__name__ != "HelpScreen"

        asyncio.run(scenario())

    def test_empty_environment_is_explained(self, tmp_path: Path) -> None:
        async def scenario() -> None:
            with mock.patch.dict(os.environ, _env(), clear=False):
                app = DepTreeApp()
                async with app.run_test(size=(120, 40)) as pilot:
                    await _start(app, pilot)
                    assert "No ROS 2 packages found" in app.details_text

        asyncio.run(scenario())
