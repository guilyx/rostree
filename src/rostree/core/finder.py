"""Discover ROS 2 package paths from install space and source workspace."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WorkspaceInfo:
    """Information about a discovered ROS 2 workspace."""

    path: Path
    has_src: bool = False
    has_install: bool = False
    has_build: bool = False
    packages: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True if this looks like a valid ROS 2 workspace."""
        return self.has_src or self.has_install

    def to_dict(self) -> dict:
        """Serialize to dict for JSON output."""
        return {
            "path": str(self.path),
            "has_src": self.has_src,
            "has_install": self.has_install,
            "has_build": self.has_build,
            "packages": self.packages,
            "is_valid": self.is_valid,
        }


def scan_for_workspaces(
    roots: list[Path] | None = None,
    *,
    max_depth: int = 4,
    include_home: bool = True,
    include_opt_ros: bool = True,
) -> list[WorkspaceInfo]:
    """
    Scan the host machine for ROS 2 workspaces.

    Args:
        roots: Directories to start scanning from. Defaults to common locations.
        max_depth: How deep to recurse when looking for workspaces.
        include_home: If True and roots is None, include ~/ros*, ~/catkin_ws, etc.
        include_opt_ros: If True and roots is None, include /opt/ros/* distros.

    Returns:
        List of WorkspaceInfo for each discovered workspace.
    """
    if roots is None:
        roots = []
        home = Path.home()
        if include_home:
            # Common workspace locations in home
            for pattern in ("ros*_ws", "ros2_ws", "catkin_ws", "colcon_ws", "*_ws"):
                roots.extend(home.glob(pattern))
            # Also check common dev directories
            for subdir in ("dev", "src", "projects", "workspace", "workspaces", "sas"):
                candidate = home / subdir
                if candidate.exists() and candidate.is_dir():
                    roots.append(candidate)
        if include_opt_ros:
            opt_ros = Path("/opt/ros")
            if opt_ros.exists():
                for distro in opt_ros.iterdir():
                    if distro.is_dir():
                        roots.append(distro)

    workspaces: list[WorkspaceInfo] = []
    seen: set[Path] = set()

    def _is_workspace(p: Path) -> WorkspaceInfo | None:
        """Check if path is a ROS 2 workspace root."""
        resolved = p.resolve()
        if resolved in seen:
            return None
        has_src = (p / "src").exists() and (p / "src").is_dir()
        has_install = (p / "install").exists() and (p / "install").is_dir()
        has_build = (p / "build").exists() and (p / "build").is_dir()
        # For /opt/ros distros, check share dir
        has_share = (p / "share").exists() and (p / "share").is_dir()
        if has_src or has_install or has_share:
            seen.add(resolved)
            info = WorkspaceInfo(
                path=resolved,
                has_src=has_src,
                has_install=has_install or has_share,
                has_build=has_build,
            )
            # Discover packages
            if has_src:
                info.packages = _list_packages_in_src(p / "src")
            elif has_install:
                info.packages = _list_packages_in_install(p / "install")
            elif has_share:
                info.packages = _list_packages_in_install(p)
            return info
        return None

    def _scan_dir(p: Path, depth: int) -> None:
        if depth > max_depth:
            return
        if not p.exists() or not p.is_dir():
            return
        try:
            ws = _is_workspace(p)
            if ws is not None:
                workspaces.append(ws)
                return  # Don't recurse into a workspace
            for child in p.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    _scan_dir(child, depth + 1)
        except PermissionError:
            pass

    for root in roots:
        root_path = Path(root).resolve()
        if root_path.exists():
            # Check if root itself is a workspace
            ws = _is_workspace(root_path)
            if ws is not None:
                workspaces.append(ws)
            else:
                _scan_dir(root_path, 0)

    return workspaces


def _list_packages_in_src(src: Path) -> list[str]:
    """List package names from a src directory."""
    packages = []
    for root, _dirs, files in os.walk(src):
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
                        if name:
                            packages.append(name)
                        break
        except OSError:
            continue
    return sorted(set(packages))


def _list_packages_in_install(install: Path) -> list[str]:
    """List package names from an install or share directory."""
    packages = []
    share = install / "share" if (install / "share").exists() else install
    if not share.exists():
        return packages
    try:
        for child in share.iterdir():
            if child.is_dir() and (child / "package.xml").exists():
                packages.append(child.name)
    except PermissionError:
        pass
    return sorted(packages)


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


def _gather_workspace_src_roots(extra_source_roots: list[Path] | None = None) -> list[Path]:
    """Collect workspace src roots from env and optional extra roots. Deduplicated."""
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
    if extra_source_roots:
        for p in extra_source_roots:
            r = Path(p).resolve()
            if r.exists() and r.is_dir():
                workspace_srcs.append(r)
    seen: set[Path] = set()
    out: list[Path] = []
    for src in workspace_srcs:
        canonical = src.resolve()
        if canonical in seen:
            continue
        seen.add(canonical)
        out.append(canonical)
    return out


def find_package_path(
    package_name: str,
    *,
    extra_source_roots: list[Path] | None = None,
) -> Path | None:
    """
    Find the directory containing package.xml for a ROS 2 package.

    Searches in order:
    1. AMENT_PREFIX_PATH (install space) - share/<package_name>/package.xml
    2. COLCON_PREFIX_PATH (install space) - same
    3. Source workspace: if COLCON_WORKSPACE or common envs point to a workspace,
       scan src for a package with matching name.
    4. Any paths in extra_source_roots (user-added source directories).

    Returns the path to the package.xml file, or None if not found.
    """
    # Install space: AMENT_PREFIX_PATH and COLCON_PREFIX_PATH
    for prefix in _env_paths("AMENT_PREFIX_PATH") + _env_paths("COLCON_PREFIX_PATH"):
        p = _find_package_xml_in_prefix(prefix, package_name)
        if p is not None:
            return p

    workspace_srcs = _gather_workspace_src_roots(extra_source_roots=extra_source_roots)
    for src in workspace_srcs:
        p = _find_package_xml_in_src(src, package_name)
        if p is not None:
            return p

    return None


def list_package_paths(
    *,
    extra_source_roots: list[Path] | None = None,
) -> dict[str, Path]:
    """
    List all known ROS 2 packages (install + source) and their package.xml paths.

    extra_source_roots: optional list of directories to scan for package.xml (e.g. user-added).

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

    workspace_srcs = _gather_workspace_src_roots(extra_source_roots=extra_source_roots)
    for src in workspace_srcs:
        for root, _dirs, files in os.walk(src):
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


def _is_system_prefix(prefix: Path) -> bool:
    """True if prefix is under /opt/ros (ROS distro install)."""
    try:
        prefix_str = str(prefix.resolve())
        return "/opt/ros" in prefix_str
    except Exception:
        return False


def _workspace_root_from_prefix(prefix: Path) -> Path | None:
    """If prefix is under an install dir, return workspace root (parent of install)."""
    try:
        p = prefix.resolve()
        if p.name == "install" or (p.parent.name == "install"):
            root = p.parent if p.name == "install" else p.parent.parent
            return root
        return p
    except Exception:
        return None


def list_packages_by_source(
    *,
    extra_source_roots: list[Path] | None = None,
) -> dict[str, list[str]]:
    """
    List packages grouped by source (System, Workspace, Other, Source, Added).

    Lets you distinguish:
    - System: /opt/ros/... (ROS distro)
    - Workspace: first non-system install (your workspace)
    - Other: other install prefixes (third-party workspaces)
    - Source: unbuilt packages from workspace src trees
    - Added: packages from extra_source_roots (user-added paths)

    Returns dict mapping source_label -> sorted list of package names.
    """
    by_source: dict[str, list[str]] = {}
    seen: set[str] = set()
    prefixes = _env_paths("AMENT_PREFIX_PATH") + _env_paths("COLCON_PREFIX_PATH")
    workspace_root_used: Path | None = None  # first non-system workspace = "Workspace"

    for prefix in prefixes:
        share = prefix / "share"
        if not share.exists():
            continue
        if _is_system_prefix(prefix):
            label = f"System ({prefix})"
        else:
            root = _workspace_root_from_prefix(prefix)
            root_resolved = root.resolve() if root else prefix.resolve()
            root_str = str(root_resolved)
            if workspace_root_used is None:
                workspace_root_used = root_resolved
                label = f"Workspace ({root_str})"
            elif root_resolved == workspace_root_used:
                label = f"Workspace ({root_str})"
            else:
                label = f"Other ({root_str})"
        if label not in by_source:
            by_source[label] = []
        for child in share.iterdir():
            if child.is_dir() and (child / "package.xml").exists():
                if child.name not in seen:
                    seen.add(child.name)
                    by_source[label].append(child.name)
        if by_source[label]:
            by_source[label] = sorted(by_source[label])

    # Source space: workspace src trees (from env)
    workspace_srcs: list[tuple[Path, str]] = []
    for env in ("COLCON_PREFIX_PATH", "AMENT_PREFIX_PATH"):
        for prefix in _env_paths(env):
            parent = prefix.parent
            if parent.name == "install":
                src = parent / "src"
                if src.exists() and src.is_dir():
                    root_str = str(parent.parent)
                    workspace_srcs.append((src, f"Source ({root_str}/src)"))
    for env in ("ROS2_WORKSPACE", "COLCON_WORKSPACE"):
        for raw in os.environ.get(env, "").split(os.pathsep):
            p = Path(raw).resolve()
            if p.exists():
                src = p / "src" if (p / "src").exists() else p
                workspace_srcs.append((src.resolve(), f"Source ({src})"))

    seen_src: set[Path] = set()
    for src, label in workspace_srcs:
        if src in seen_src:
            continue
        seen_src.add(src)
        if label not in by_source:
            by_source[label] = []
        for root, _dirs, files in os.walk(src):
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
                            if name and name not in seen:
                                seen.add(name)
                                by_source[label].append(name)
                            break
            except OSError:
                continue
        by_source[label] = sorted(by_source[label])

    # User-added source roots
    if extra_source_roots:
        for p in extra_source_roots:
            src = Path(p).resolve()
            if not src.exists() or not src.is_dir():
                continue
            label = f"Added ({src})"
            if label not in by_source:
                by_source[label] = []
            for root, _dirs, files in os.walk(src):
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
                                if name and name not in seen:
                                    seen.add(name)
                                    by_source[label].append(name)
                                break
                except OSError:
                    continue
            by_source[label] = sorted(by_source[label])

    return by_source
