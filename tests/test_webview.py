"""Tests for the self-contained interactive HTML graph."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from unittest import mock

from rostree.core.tree import build_dependency_graph
from rostree.core.webview import graph_payload, to_html
from tests.conftest import write_package

EMPTY_ENV = {
    "AMENT_PREFIX_PATH": "",
    "COLCON_PREFIX_PATH": "",
    "ROS2_WORKSPACE": "",
    "COLCON_WORKSPACE": "",
}


def stack(root: Path) -> None:
    """app -> [core, util]; core -> util; util -> a name that never resolves."""
    write_package(root, "util", version="1.0.0", depends=["missing_key"])
    write_package(root, "core", version="2.0.0", depends=["util"])
    write_package(root, "app", version="3.0.0", depends=["core", "util"])


def graph_for(root: Path, name: str = "app", **kwargs):
    with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
        return build_dependency_graph([name], extra_source_roots=[root], **kwargs)


class TestPayload:
    """The JSON the viewer is handed."""

    def test_every_package_becomes_a_node(self, tmp_path: Path) -> None:
        stack(tmp_path)
        payload = graph_payload(graph_for(tmp_path))
        assert set(payload["nodes"]) == {"app", "core", "util", "missing_key"}

    def test_edges_live_on_the_node_that_declares_them(self, tmp_path: Path) -> None:
        stack(tmp_path)
        nodes = graph_payload(graph_for(tmp_path))["nodes"]
        assert nodes["app"]["deps"] == ["core", "util"]
        assert nodes["util"]["deps"] == ["missing_key"]

    def test_unresolved_names_are_marked_missing(self, tmp_path: Path) -> None:
        stack(tmp_path)
        nodes = graph_payload(graph_for(tmp_path))["nodes"]
        assert nodes["missing_key"]["kind"] == "missing"
        assert nodes["app"]["kind"] != "missing"

    def test_hiding_missing_drops_both_node_and_edge(self, tmp_path: Path) -> None:
        stack(tmp_path)
        nodes = graph_payload(graph_for(tmp_path), show_missing=False)["nodes"]
        assert "missing_key" not in nodes
        assert nodes["util"]["deps"] == []

    def test_metadata_is_carried_through(self, tmp_path: Path) -> None:
        stack(tmp_path)
        node = graph_payload(graph_for(tmp_path))["nodes"]["app"]
        assert node["version"] == "3.0.0"
        assert "app" in node["path"]

    def test_rosdep_keys_are_kept_separately(self, tmp_path: Path) -> None:
        write_package(tmp_path, "app", depends=["python3-numpy", "libboost-dev"])
        node = graph_payload(graph_for(tmp_path))["nodes"]["app"]
        assert set(node["rosdep"]) == {"python3-numpy", "libboost-dev"}
        assert node["deps"] == []

    def test_stats_describe_what_is_drawn(self, tmp_path: Path) -> None:
        stack(tmp_path)
        stats = graph_payload(graph_for(tmp_path))["stats"]
        assert stats["packages"] == 4
        assert stats["edges"] == 4  # app->core, app->util, core->util, util->missing
        assert stats["missing"] == 1

    def test_cycles_are_reported(self, tmp_path: Path) -> None:
        write_package(tmp_path, "a", depends=["b"])
        write_package(tmp_path, "b", depends=["a"])
        payload = graph_payload(graph_for(tmp_path, "a"))
        assert payload["stats"]["cycles"] >= 1

    def test_payload_is_json_serialisable(self, tmp_path: Path) -> None:
        stack(tmp_path)
        json.dumps(graph_payload(graph_for(tmp_path)))  # must not raise


class TestDocument:
    """The generated file itself."""

    def test_is_one_self_contained_document(self, tmp_path: Path) -> None:
        stack(tmp_path)
        html = to_html(graph_for(tmp_path))
        assert html.startswith("<!doctype html>")
        # The whole point is that it works offline: nothing may be fetched.
        assert not re.search(r'src\s*=\s*["\']https?://', html)
        assert not re.search(r'href\s*=\s*["\']https?://', html)
        assert "<style>" in html and "<script>" in html

    def test_no_placeholder_survives(self, tmp_path: Path) -> None:
        stack(tmp_path)
        html = to_html(graph_for(tmp_path), title="t")
        for token in ("{{TITLE}}", "{{STYLE}}", "{{DATA}}", "{{SCRIPT}}"):
            assert token not in html

    def test_embedded_data_parses_back(self, tmp_path: Path) -> None:
        stack(tmp_path)
        html = to_html(graph_for(tmp_path))
        blob = re.search(
            r'<script id="graph-data" type="application/json">(.*?)</script>', html, re.S
        )
        assert blob is not None
        payload = json.loads(blob.group(1).replace("<\\/", "</"))
        assert payload["nodes"]["app"]["deps"] == ["core", "util"]

    def test_a_closing_script_tag_in_the_data_cannot_break_out(self, tmp_path: Path) -> None:
        """A package description is arbitrary text and must not end the block."""
        pkg = tmp_path / "app"
        pkg.mkdir()
        pkg.joinpath("package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
  <name>app</name>
  <version>1.0.0</version>
  <description>ends a block: &lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;</description>
</package>
"""
        )
        html = to_html(graph_for(tmp_path))
        body = html.split('<script id="graph-data" type="application/json">')[1]
        data, _, rest = body.partition("</script>")
        assert "alert(1)" in data  # the payload kept it...
        assert "alert(1)" not in rest  # ...and it never escaped into markup
        json.loads(data.replace("<\\/", "</"))

    def test_title_is_escaped(self, tmp_path: Path) -> None:
        stack(tmp_path)
        html = to_html(graph_for(tmp_path), title='<img src=x onerror="hack()">')
        assert "<title>&lt;img" in html
        assert "<title><img" not in html


class TestGraphCommand:
    """`rostree graph -f html`."""

    def _args(self, tmp_path: Path, **overrides):
        import argparse

        base = dict(
            package="app",
            workspace=None,
            format="html",
            output=None,
            depth=None,
            runtime=False,
            dep_type=None,
            source=[str(tmp_path)],
            include=None,
            exclude=None,
            only_workspace=False,
            hide_missing=False,
            no_title=False,
            render=None,
            open=False,
            json=False,
        )
        base.update(overrides)
        return argparse.Namespace(**base)

    def test_writes_a_file_next_to_the_package_name(self, tmp_path: Path, monkeypatch) -> None:
        from rostree.cli import cmd_graph

        stack(tmp_path)
        monkeypatch.chdir(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            assert cmd_graph(self._args(tmp_path)) == 0
        assert (tmp_path / "app.html").is_file()

    def test_output_gets_an_html_suffix(self, tmp_path: Path) -> None:
        from rostree.cli import cmd_graph

        stack(tmp_path)
        target = tmp_path / "out" / "graph.txt"
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            assert cmd_graph(self._args(tmp_path, output=str(target))) == 0
        assert (tmp_path / "out" / "graph.html").is_file()

    def test_render_and_html_together_is_a_usage_error(self, tmp_path: Path) -> None:
        from rostree.cli import cmd_graph

        stack(tmp_path)
        with mock.patch.dict(os.environ, EMPTY_ENV, clear=False):
            assert cmd_graph(self._args(tmp_path, render="png")) == 2
