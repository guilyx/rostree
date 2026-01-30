"""Discover ROS 2 package paths from install space and source workspace."""

from __future__ import annotations

import os
from pathlib import Path


def _env_paths(env_var: str) -> list[Path]:
    """Split an environment variable by os.pathsep and return existing Paths."""
    value = os.environ.get(env_var, "")
    if not value:
        return []
    return [Path(p).resolve() for p in value.split(os.pathsep) if p.strip() and Path(p).exists()]


def _find_package_xml_in_prefix(prefix: Path, package_name: str) -> Path | None:
    """Look for share/<package_name>/package.xml under a colcon/ament prefix."""
    candidate = prefix / "share" / package_name / "package.xml"
    if candidate.exists():
        return candidate
    # Some layouts use lib/python3.x/site-packages for ament_python
    return None


def _find_package_xml_in_src(src_root: Path, package_name: str) -> Path | None:
    """Recursively search for a directory containing package.xml with matching <name>."""
    for root, _dirs, files in os.walk(src_root, topdown=True):
        if "package.xml" not in files:
            continue
        pkg_xml = Path(root) / "package.xml"
        try:
            with open(pkg_xml) as f:
                for line in f:
                    if "<name>" in line and f"<name>{package_name}</name>" in line:
                        return pkg_xml
                    # Simple line-based check; parser will validate
                    if "<name>" in line:
                        break
        except OSError:
            continue
    return None


def find_package_path(package_name: str) -> Path | None:
    """
    Find the directory containing package.xml for a ROS 2 package.

    Searches in order:
    1. AMENT_PREFIX_PATH (install space) - share/<package_name>/package.xml
    2. COLCON_PREFIX_PATH (install space) - same
    3. Source workspace: if COLCON_WORKSPACE or common envs point to a workspace,
       scan src for a package with matching name.

    Returns the path to the package.xml file, or None if not found.
    """
    # Install space: AMENT_PREFIX_PATH and COLCON_PREFIX_PATH
    for prefix in _env_paths("AMENT_PREFIX_PATH") + _env_paths("COLCON_PREFIX_PATH"):
        p = _find_package_xml_in_prefix(prefix, package_name)
        if p is not None:
            return p

    # Source space: typical layout is <workspace>/src, we look for workspace root
    workspace_srcs: list[Path] = []
    for env in ("COLCON_PREFIX_PATH", "AMENT_PREFIX_PATH"):
        for prefix in _env_paths(env):
            # install space is <workspace>/install; src is <workspace>/src
            parent = prefix.parent
            if parent.name == "install":
                src = parent / "src"
                if src.exists() and src.is_dir():
                    workspace_srcs.append(src)
    # Also explicit workspace
    for env in ("ROS2_WORKSPACE", "COLCON_WORKSPACE"):
        for raw in os.environ.get(env, "").split(os.pathsep):
            p = Path(raw).resolve()
            if p.exists():
                workspace_srcs.append(p / "src" if (p / "src").exists() else p)

    seen: set[Path] = set()
    for src in workspace_srcs:
        canonical = src.resolve()
        if canonical in seen:
            continue
        seen.add(canonical)
        p = _find_package_xml_in_src(canonical, package_name)
        if p is not None:
            return p

    return None


def list_package_paths() -> dict[str, Path]:
    """
    List all known ROS 2 packages (install + source) and their package.xml paths.

    Returns a dict mapping package name -> path to package.xml.
    """
    result: dict[str, Path] = {}

    # From install space: each prefix/share/<name>/package.xml
    for prefix in _env_paths("AMENT_PREFIX_PATH") + _env_paths("COLCON_PREFIX_PATH"):
        share = prefix / "share"
        if not share.exists():
            continue
        for child in share.iterdir():
            if child.is_dir():
                pkg_xml = child / "package.xml"
                if pkg_xml.exists():
                    result[child.name] = pkg_xml

    # From source: walk src trees and parse <name> from package.xml
    workspace_srcs: list[Path] = []
    for env in ("COLCON_PREFIX_PATH", "AMENT_PREFIX_PATH"):
        for prefix in _env_paths(env):
            parent = prefix.parent
            if parent.name == "install":
                src = parent / "src"
                if src.exists() and src.is_dir():
                    workspace_srcs.append(src)
    for env in ("ROS2_WORKSPACE", "COLCON_WORKSPACE"):
        for raw in os.environ.get(env, "").split(os.pathsep):
            p = Path(raw).resolve()
            if p.exists():
                workspace_srcs.append(p / "src" if (p / "src").exists() else p)

    seen_roots: set[Path] = set()
    for src in workspace_srcs:
        canonical = src.resolve()
        if canonical in seen_roots:
            continue
        seen_roots.add(canonical)
        for root, _dirs, files in os.walk(canonical):
            if "package.xml" not in files:
                continue
            pkg_xml = Path(root) / "package.xml"
            try:
                with open(pkg_xml) as f:
                    for line in f:
                        if "<name>" in line and "</name>" in line:
                            start = line.find("<name>") + 6
                            end = line.find("</name>")
                            name = line[start:end].strip()
                            if name and name not in result:
                                result[name] = pkg_xml
                            break
            except OSError:
                continue

    return result
