"""Shared fixtures for the rostree test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from rostree.core.index import clear_index_cache
from rostree.core.parser import clear_parse_cache

PACKAGE_XML = """<?xml version="1.0"?>
<package format="3">
  <name>{name}</name>
  <version>{version}</version>
  <description>{description}</description>
  <maintainer email="dev@example.com">dev</maintainer>
  <license>Apache-2.0</license>
{deps}
</package>
"""


@pytest.fixture(autouse=True)
def _isolate_caches():
    """rostree caches its package index per process; tests must not share one."""
    clear_index_cache()
    clear_parse_cache()
    yield
    clear_index_cache()
    clear_parse_cache()


def write_package(
    root: Path,
    name: str,
    *,
    version: str = "1.0.0",
    description: str = "A test package",
    depends: list[str] | None = None,
    exec_depends: list[str] | None = None,
) -> Path:
    """Create ``root/<name>/package.xml`` and return the manifest path."""
    lines = [f"  <depend>{d}</depend>" for d in depends or []]
    lines += [f"  <exec_depend>{d}</exec_depend>" for d in exec_depends or []]
    pkg_dir = root / name
    pkg_dir.mkdir(parents=True, exist_ok=True)
    manifest = pkg_dir / "package.xml"
    manifest.write_text(
        PACKAGE_XML.format(
            name=name,
            version=version,
            description=description,
            deps="\n".join(lines),
        )
    )
    return manifest


@pytest.fixture
def make_package(tmp_path: Path):
    """Factory writing packages into a temporary source root."""

    def _make(name: str, **kwargs) -> Path:
        return write_package(tmp_path, name, **kwargs)

    return _make
