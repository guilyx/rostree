"""Discover ROS 2 package paths from install space and source workspace.

The lookups here are thin wrappers over :mod:`rostree.core.index`, which does the
filesystem work once and answers by name from memory. Workspace *scanning*
(finding whole workspaces on the host) lives here because it is a different job:
it looks for directory layouts, not for packages by name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rostree.core.index import (
    _PRUNE_DIRS,
    PackageIndex,
    SourceKind,
    build_index,
    env_paths,
    gather_source_roots,
    get_index,
    is_system_prefix,
    iter_manifests_in_source_tree,
    workspace_root_from_prefix,
)
from rostree.core.parser import quick_package_name

# These helpers moved to rostree.core.index, but finder remains their published
# home; the underscore names are kept so existing callers keep working.
_env_paths = env_paths
_gather_workspace_src_roots = gather_source_roots
_is_system_prefix = is_system_prefix
_workspace_root_from_prefix = workspace_root_from_prefix

__all__ = [
    "PackageIndex",
    "SourceKind",
    "WorkspaceInfo",
    "build_index",
    "find_package_path",
    "get_index",
    "list_package_paths",
    "list_packages_by_source",
    "scan_for_workspaces",
]


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
            for subdir in ("dev", "src", "projects", "workspace", "workspaces"):
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
        """
        Check if path is a ROS 2 workspace root.

        Having a ``src/`` directory proves nothing — every JavaScript project and
        half of ``~/dev`` has one. A workspace has to show evidence of ROS: a
        package in its source tree, or an install space colcon or ament made.
        """
        resolved = p.resolve()
        if resolved in seen:
            return None
        has_src = (p / "src").is_dir()
        has_install = (p / "install").is_dir()
        has_build = (p / "build").is_dir()
        # For /opt/ros distros, the prefix itself has a share/ directory.
        has_share = (p / "share").is_dir()
        if not (has_src or has_install or has_share):
            return None

        packages: list[str] = []
        if has_src:
            packages = _list_packages_in_src(p / "src")
        if not packages and has_install:
            packages = _list_packages_in_install(p / "install")
        if not packages and has_share:
            packages = _list_packages_in_install(p)
        if not packages and not _has_install_marker(p):
            return None

        seen.add(resolved)
        return WorkspaceInfo(
            path=resolved,
            has_src=has_src,
            has_install=has_install or has_share,
            has_build=has_build,
            packages=packages,
        )

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
            for child in sorted(p.iterdir()):
                if (
                    child.is_dir()
                    and not child.name.startswith(".")
                    and child.name not in _PRUNE_DIRS
                ):
                    _scan_dir(child, depth + 1)
        except OSError:  # PermissionError, a vanished directory, a dead mount
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


#: Files colcon and ament leave behind. ``COLCON_IGNORE`` is the precise one:
#: colcon drops it into the build/, install/ and log/ directories it creates, and
#: a React or Gradle project's build/ never has it. An install space with none of
#: these and no packages is not something rostree can say anything about.
_COLCON_MARKERS = (
    ("install", ".colcon_install_layout"),
    ("install", "setup.bash"),
    ("install", "setup.sh"),
    ("install", "local_setup.bash"),
    ("install", "local_setup.sh"),
    ("install", "COLCON_IGNORE"),
    ("build", "COLCON_IGNORE"),
    ("log", "COLCON_IGNORE"),
    (".", "setup.bash"),  # a distro prefix such as /opt/ros/<distro>
    (".", "local_setup.bash"),
)


def _has_install_marker(workspace: Path) -> bool:
    """True if colcon or ament has laid anything down in ``workspace``."""
    return any((workspace / sub / marker).is_file() for sub, marker in _COLCON_MARKERS)


def _list_packages_in_src(src: Path) -> list[str]:
    """List package names from a src directory."""
    names = (quick_package_name(m) for m in iter_manifests_in_source_tree(src))
    return sorted({n for n in names if n})


def _list_packages_in_install(install: Path) -> list[str]:
    """List package names from an install prefix, or from a share directory directly."""
    share = install / "share" if (install / "share").is_dir() else install
    try:
        return sorted(
            child.name
            for child in share.iterdir()
            if child.is_dir() and (child / "package.xml").is_file()
        )
    except (OSError, PermissionError):
        return []


def _find_package_xml_in_prefix(prefix: Path, package_name: str) -> Path | None:
    """Look for share/<package_name>/package.xml under a colcon/ament prefix."""
    candidate = prefix / "share" / package_name / "package.xml"
    if candidate.exists():
        return candidate
    return None


def _find_package_xml_in_src(src_root: Path, package_name: str) -> Path | None:
    """Search a source tree for the package.xml whose <name> matches."""
    for manifest in iter_manifests_in_source_tree(src_root):
        if quick_package_name(manifest) == package_name:
            return manifest
    return None


def find_package_path(
    package_name: str,
    *,
    extra_source_roots: list[Path] | None = None,
    index: PackageIndex | None = None,
) -> Path | None:
    """
    Find the package.xml for a ROS 2 package.

    Install spaces (AMENT_PREFIX_PATH, then COLCON_PREFIX_PATH) win over source
    trees, and earlier prefixes win over later ones — the same order the ROS 2
    environment itself uses. ``extra_source_roots`` are searched last.

    Pass an ``index`` to reuse an existing scan; otherwise a process-wide cached
    index is used, so repeated lookups do not touch the filesystem again.

    Returns the path to the package.xml file, or None if not found.
    """
    if index is None:
        index = get_index(extra_source_roots=extra_source_roots)
    return index.resolve(package_name)


def list_package_paths(
    *,
    extra_source_roots: list[Path] | None = None,
    index: PackageIndex | None = None,
) -> dict[str, Path]:
    """
    List all known ROS 2 packages (install + source) and their package.xml paths.

    Returns a dict mapping package name -> path to package.xml.
    """
    if index is None:
        index = get_index(extra_source_roots=extra_source_roots)
    return index.paths()


def list_packages_by_source(
    *,
    extra_source_roots: list[Path] | None = None,
    index: PackageIndex | None = None,
) -> dict[str, list[str]]:
    """
    List packages grouped by source label.

    Lets you distinguish:
    - System: the ROS distro itself (/opt/ros/..., or a source/conda install)
    - Workspace: first non-system install (your workspace)
    - Other: other install prefixes (third-party workspaces)
    - Source: unbuilt packages from workspace src trees
    - Added: packages from extra_source_roots (user-added paths)

    Returns dict mapping source_label -> sorted list of package names.
    """
    if index is None:
        index = get_index(extra_source_roots=extra_source_roots)
    return index.by_label()
