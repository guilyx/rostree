"""A cached, one-pass index of every ROS 2 package visible to the current environment.

Resolving a package name used to mean walking the filesystem again for every node
of a dependency tree, which made large trees quadratic in disk I/O. This module
scans each install prefix and source tree exactly once, then answers lookups from
memory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable

from rostree.core.parser import PackageInfo, parse_package_xml, quick_package_name

# Directories that never contain source packages worth indexing.
_PRUNE_DIRS = frozenset(
    {
        ".git",
        ".svn",
        ".hg",
        "build",
        "install",
        "log",
        "logs",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
    }
)

# colcon/ament markers that tell tooling to skip a directory tree.
_IGNORE_MARKERS = ("COLCON_IGNORE", "AMENT_IGNORE", "CATKIN_IGNORE")

_ENV_VARS = ("AMENT_PREFIX_PATH", "COLCON_PREFIX_PATH", "ROS2_WORKSPACE", "COLCON_WORKSPACE")


class SourceKind(str, Enum):
    """Where a package was found."""

    SYSTEM = "system"  # /opt/ros/<distro> — the ROS distro itself
    WORKSPACE = "workspace"  # first non-system install space — your workspace
    OTHER = "other"  # further install spaces — overlays, third-party
    SOURCE = "source"  # unbuilt packages in a workspace src tree
    ADDED = "added"  # user-supplied source roots


@dataclass(frozen=True)
class PackageEntry:
    """One package known to the index."""

    name: str
    manifest: Path  # path to package.xml
    kind: SourceKind
    origin: Path  # install prefix or source root it was found under
    label: str  # human-readable source label, e.g. "System (/opt/ros/jazzy)"

    @property
    def directory(self) -> Path:
        """Directory containing the package.xml."""
        return self.manifest.parent


def env_paths(env_var: str) -> list[Path]:
    """Split an environment variable by os.pathsep and return existing Paths."""
    value = os.environ.get(env_var, "")
    if not value:
        return []
    return [Path(p).resolve() for p in value.split(os.pathsep) if p.strip() and Path(p).exists()]


def is_system_prefix(prefix: Path) -> bool:
    """True if prefix is under /opt/ros (a ROS distro install)."""
    try:
        return "/opt/ros" in str(prefix.resolve())
    except OSError:
        return False


def workspace_root_from_prefix(prefix: Path) -> Path | None:
    """If prefix is inside an install dir, return the workspace root (parent of install)."""
    try:
        p = prefix.resolve()
    except OSError:
        return None
    if p.name == "install":
        return p.parent
    if p.parent.name == "install":
        return p.parent.parent
    return p


def gather_source_roots(extra_source_roots: Iterable[Path] | None = None) -> list[Path]:
    """Collect workspace src roots from the environment plus any extra roots, deduplicated."""
    roots: list[Path] = []
    for env in ("COLCON_PREFIX_PATH", "AMENT_PREFIX_PATH"):
        for prefix in env_paths(env):
            # Both colcon layouts appear on the path: a merged install prefix
            # (<ws>/install) and an isolated per-package one (<ws>/install/<pkg>).
            # Either way the source tree is <ws>/src, not <install>/src.
            workspace = workspace_root_from_prefix(prefix)
            if workspace is None:
                continue
            src = workspace / "src"
            if src.is_dir():
                roots.append(src)
    for env in ("ROS2_WORKSPACE", "COLCON_WORKSPACE"):
        for raw in os.environ.get(env, "").split(os.pathsep):
            if not raw.strip():
                continue
            p = Path(raw).expanduser()
            if p.exists():
                p = p.resolve()
                roots.append(p / "src" if (p / "src").is_dir() else p)
    if extra_source_roots:
        for raw in extra_source_roots:
            p = Path(raw).expanduser()
            if p.is_dir():
                roots.append(p.resolve())

    seen: set[Path] = set()
    out: list[Path] = []
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        out.append(root)
    return out


def iter_manifests_in_source_tree(root: Path) -> Iterable[Path]:
    """
    Yield every package.xml under a source tree.

    Prunes build artefacts, VCS metadata and directories marked with COLCON_IGNORE,
    and does not descend into a package once its manifest is found — the same rules
    colcon uses, and a large speedup on real workspaces.
    """
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=lambda _e: None):
        if any(marker in filenames for marker in _IGNORE_MARKERS):
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in _PRUNE_DIRS and not d.startswith(".")]
        if "package.xml" in filenames:
            dirnames[:] = []
            yield Path(dirpath) / "package.xml"


def iter_manifests_in_prefix(prefix: Path) -> Iterable[Path]:
    """Yield share/<pkg>/package.xml for every package installed under a prefix."""
    share = prefix / "share"
    if not share.is_dir():
        return
    try:
        children = sorted(share.iterdir())
    except OSError:
        return
    for child in children:
        manifest = child / "package.xml"
        try:
            if child.is_dir() and manifest.is_file():
                yield manifest
        except OSError:
            continue


@dataclass
class PackageIndex:
    """
    Every package rostree can see, resolvable by name in constant time.

    Build it once per operation (or once per process, via :func:`get_index`) and
    pass it down; every lookup afterwards is a dict access rather than a syscall.
    """

    entries: dict[str, PackageEntry] = field(default_factory=dict)
    source_roots: list[Path] = field(default_factory=list)
    prefixes: list[Path] = field(default_factory=list)
    # Populated on demand by reverse_dependencies(), keyed by dependency tag set.
    _reverse: dict[tuple[str, ...] | None, dict[str, set[str]]] = field(
        default_factory=dict, repr=False
    )

    def __len__(self) -> int:
        return len(self.entries)

    def __contains__(self, name: object) -> bool:
        return name in self.entries

    def get(self, name: str) -> PackageEntry | None:
        """Return the entry for a package name, or None if it is unknown."""
        return self.entries.get(name)

    def resolve(self, name: str) -> Path | None:
        """Return the package.xml path for a package name, or None."""
        entry = self.entries.get(name)
        return entry.manifest if entry is not None else None

    def names(self) -> list[str]:
        """All known package names, sorted."""
        return sorted(self.entries)

    def paths(self) -> dict[str, Path]:
        """Mapping of package name -> package.xml path."""
        return {name: entry.manifest for name, entry in self.entries.items()}

    def by_label(self) -> dict[str, list[str]]:
        """Package names grouped by human-readable source label, in discovery order."""
        grouped: dict[str, list[str]] = {}
        for entry in self.entries.values():
            grouped.setdefault(entry.label, []).append(entry.name)
        return {label: sorted(names) for label, names in grouped.items()}

    def by_kind(self, kind: SourceKind) -> list[str]:
        """Package names from a particular kind of source."""
        return sorted(n for n, e in self.entries.items() if e.kind is kind)

    def workspace_names(self) -> list[str]:
        """Packages that belong to the user's own workspaces (not the ROS distro)."""
        return sorted(n for n, e in self.entries.items() if e.kind is not SourceKind.SYSTEM)

    def info(self, name: str, *, include_tags: tuple[str, ...] | None = None) -> PackageInfo | None:
        """Parse and return the manifest for a package (memoized by the parser)."""
        manifest = self.resolve(name)
        if manifest is None:
            return None
        return parse_package_xml(manifest, include_tags=include_tags)

    def reverse_dependencies(
        self,
        *,
        include_tags: tuple[str, ...] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> dict[str, set[str]]:
        """
        Map each package name to the set of known packages that depend on it.

        Requires parsing every manifest, so the result is cached on the index —
        per tag set, since runtime-only and full dependency maps differ.
        """
        cached = self._reverse.get(include_tags)
        if cached is not None:
            return cached
        reverse: dict[str, set[str]] = {}
        total = len(self.entries)
        for i, (name, entry) in enumerate(self.entries.items()):
            info = parse_package_xml(entry.manifest, include_tags=include_tags)
            if info is not None:
                for dep in info.dependencies:
                    reverse.setdefault(dep, set()).add(name)
            if on_progress is not None:
                on_progress(i + 1, total)
        self._reverse[include_tags] = reverse
        return reverse


def build_index(
    *,
    extra_source_roots: Iterable[Path] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> PackageIndex:
    """
    Scan the environment once and return a :class:`PackageIndex`.

    Install prefixes win over source trees, and earlier prefixes win over later
    ones, matching how the ROS 2 environment itself resolves packages.
    """
    entries: dict[str, PackageEntry] = {}
    prefixes = env_paths("AMENT_PREFIX_PATH") + env_paths("COLCON_PREFIX_PATH")

    seen_prefixes: set[Path] = set()
    workspace_root: Path | None = None
    ordered_prefixes: list[Path] = []
    for prefix in prefixes:
        if prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)
        ordered_prefixes.append(prefix)
        if not (prefix / "share").is_dir():
            continue
        if is_system_prefix(prefix):
            kind = SourceKind.SYSTEM
            label = f"System ({prefix})"
        else:
            root = workspace_root_from_prefix(prefix) or prefix
            if workspace_root is None:
                workspace_root = root
            if root == workspace_root:
                kind = SourceKind.WORKSPACE
                label = f"Workspace ({root})"
            else:
                kind = SourceKind.OTHER
                label = f"Other ({root})"
        if on_progress is not None:
            on_progress(f"Indexing {prefix}")
        for manifest in iter_manifests_in_prefix(prefix):
            name = manifest.parent.name
            if name not in entries:
                entries[name] = PackageEntry(
                    name=name, manifest=manifest, kind=kind, origin=prefix, label=label
                )

    env_roots = gather_source_roots()
    extra = [Path(p).expanduser().resolve() for p in (extra_source_roots or []) if Path(p).is_dir()]
    for root in gather_source_roots(extra_source_roots):
        added = root in extra and root not in env_roots
        kind = SourceKind.ADDED if added else SourceKind.SOURCE
        label = f"{'Added' if added else 'Source'} ({root})"
        if on_progress is not None:
            on_progress(f"Scanning {root}")
        for manifest in iter_manifests_in_source_tree(root):
            name = quick_package_name(manifest)
            if name and name not in entries:
                entries[name] = PackageEntry(
                    name=name, manifest=manifest, kind=kind, origin=root, label=label
                )

    return PackageIndex(
        entries=entries,
        source_roots=gather_source_roots(extra_source_roots),
        prefixes=ordered_prefixes,
    )


_CACHE: dict[tuple, PackageIndex] = {}


def _cache_key(extra_source_roots: Iterable[Path] | None) -> tuple:
    env = tuple(os.environ.get(var, "") for var in _ENV_VARS)
    roots = tuple(sorted(str(Path(p).expanduser()) for p in (extra_source_roots or [])))
    return (env, roots)


def get_index(
    *,
    extra_source_roots: Iterable[Path] | None = None,
    refresh: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> PackageIndex:
    """
    Return a process-wide cached index for the current environment.

    The cache key covers the ROS environment variables and any extra source roots,
    so switching workspaces mid-process rebuilds the index automatically. Pass
    ``refresh=True`` after packages change on disk.
    """
    key = _cache_key(extra_source_roots)
    if refresh:
        _CACHE.pop(key, None)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    index = build_index(extra_source_roots=extra_source_roots, on_progress=on_progress)
    _CACHE[key] = index
    return index


def clear_index_cache() -> None:
    """Forget every cached index (used by tests and the TUI refresh action)."""
    _CACHE.clear()
