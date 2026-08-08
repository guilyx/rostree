"""Parse ROS 2 package.xml for package metadata and dependencies."""

from __future__ import annotations

import xml.etree.ElementTree as ET  # see the note below  # nosec B405
from dataclasses import dataclass, field
from pathlib import Path

# On the stdlib XML parser
# -----------------------
# Security scanners flag `xml.etree` on sight. What it is actually exposed to
# here is worth stating, because the answer is not "nothing":
#
#   * CPython's ElementTree does not resolve external entities and does not
#     fetch DTDs, so XXE and SSRF do not apply (see the XML vulnerability table
#     in the Python docs).
#   * It *is* susceptible to entity-expansion denial of service ("billion
#     laughs"). A hand-crafted package.xml could hang rostree.
#
# The files parsed here are the package.xml manifests already sitting on your
# AMENT_PREFIX_PATH or in your workspace's src/ tree. Anyone able to plant one
# of those can also edit the CMakeLists.txt and setup.py next to it, so they own
# your build long before rostree reads anything. Hardening this against a DoS
# would mean a defusedxml dependency for a threat that is strictly weaker than
# ones already present, so the stdlib parser stays.

# Tags that declare dependency on another ROS package (we collect these for the tree).
DEPENDENCY_TAGS = (
    "depend",
    "exec_depend",
    "build_depend",
    "build_export_depend",
    "test_depend",
)

# Tags used when runtime_only=True (smaller, faster tree; no build/test deps).
RUNTIME_DEPENDENCY_TAGS = ("depend", "exec_depend")


@dataclass
class PackageInfo:
    """Metadata parsed from a package.xml."""

    name: str
    version: str
    description: str
    path: Path
    dependencies: list[str]  # ROS package names only (no system/vendor deps)
    # rosdep keys that clearly are not ROS packages (python3-foo, libboost-dev, ...).
    # Kept so callers can surface them instead of silently dropping them.
    system_dependencies: list[str] = field(default_factory=list)
    # dependency name -> the package.xml tag it was declared under
    dependency_tags: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalize to unique names, preserving declaration order.
        self.dependencies = list(dict.fromkeys(self.dependencies))
        self.system_dependencies = list(dict.fromkeys(self.system_dependencies))


def _is_ros_package_dependency(name: str) -> bool:
    """
    Heuristic: does this dependency name look like a ROS package (vs a rosdep key)?

    ROS 2 package names are restricted to lowercase letters, digits and underscores,
    so anything containing a dash is a rosdep/system key (``libboost-dev``,
    ``python3-numpy``, ``ros-humble-rclcpp``). Names starting with ``python3`` are
    system Python packages.

    Note that a ``lib`` prefix alone means nothing: ``libstatistics_collector``,
    ``libyaml_vendor`` and ``libcurl_vendor`` are genuine ROS 2 packages, so they
    must not be filtered out here. Whether a name really resolves to a package is
    decided later by the package index, not by this heuristic.
    """
    if not name or not name[0].isalpha():
        return False
    if "-" in name:
        return False
    if name.startswith("python3"):
        return False
    return True


def quick_package_name(path: Path) -> str | None:
    """
    Read just the ``<name>`` of a package.xml, without parsing the whole document.

    Used when indexing thousands of packages, where a full ElementTree parse per
    file is wasteful. Falls back to a full parse if the streaming scan finds
    nothing (multi-line or attribute-bearing ``<name>`` tags).
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                start = line.find("<name>")
                if start == -1:
                    continue
                end = line.find("</name>", start)
                if end == -1:
                    break  # split across lines: fall through to the full parse
                name = line[start + len("<name>") : end].strip()
                if name:
                    return name
                break
    except OSError:
        return None
    info = parse_package_xml(path)
    return info.name if info is not None else None


# Parsing the same package.xml repeatedly is the single hottest operation when
# walking a dependency graph, so results are cached by (path, mtime, size, tags).
_PARSE_CACHE: dict[tuple[str, int, int, tuple[str, ...] | None], PackageInfo | None] = {}


def clear_parse_cache() -> None:
    """Drop memoized package.xml parses (call after packages change on disk)."""
    _PARSE_CACHE.clear()


def parse_package_xml(
    path: Path,
    *,
    include_tags: tuple[str, ...] | None = None,
    use_cache: bool = True,
) -> PackageInfo | None:
    """
    Parse a package.xml file and return package name, version, description, and dependencies.

    Only dependency tags that typically refer to ROS packages are collected;
    rosdep-style system keys are kept separately in ``system_dependencies``.

    Args:
        path: Path to package.xml.
        include_tags: If set, only collect deps from these tags (e.g. ("depend", "exec_depend")
            for runtime-only). If None, use all DEPENDENCY_TAGS.
        use_cache: Reuse a memoized result when the file has not changed on disk.

    Returns None if the file cannot be read or is not valid package.xml.
    """
    key: tuple[str, int, int, tuple[str, ...] | None] | None = None
    if use_cache:
        try:
            st = path.stat()
            key = (str(path), int(st.st_mtime_ns), int(st.st_size), include_tags)
        except OSError:
            return None
        if key in _PARSE_CACHE:
            return _PARSE_CACHE[key]

    info = _parse_package_xml_uncached(path, include_tags=include_tags)
    if key is not None:
        _PARSE_CACHE[key] = info
    return info


def _parse_package_xml_uncached(
    path: Path,
    *,
    include_tags: tuple[str, ...] | None,
) -> PackageInfo | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        tree = ET.parse(path)  # a local manifest, see the note at the imports  # nosec B314
    except (ET.ParseError, OSError):
        return None
    root = tree.getroot()
    if root.tag != "package":
        return None

    name = ""
    version = ""
    description = ""

    for child in root:
        if child.tag == "name" and child.text:
            name = child.text.strip()
        elif child.tag == "version" and child.text:
            version = child.text.strip()
        elif child.tag == "description" and child.text:
            description = child.text.strip()

    tags = include_tags if include_tags is not None else DEPENDENCY_TAGS
    wanted = tuple(t for t in tags if t in DEPENDENCY_TAGS)
    deps: list[str] = []
    system_deps: list[str] = []
    dep_tags: dict[str, str] = {}
    for tag in wanted:
        for elem in root.findall(f".//{tag}"):
            if not elem.text:
                continue
            dep = elem.text.strip()
            if not dep:
                continue
            if _is_ros_package_dependency(dep):
                deps.append(dep)
                dep_tags.setdefault(dep, tag)
            else:
                system_deps.append(dep)

    if not name:
        return None
    return PackageInfo(
        name=name,
        version=version,
        description=" ".join((description or "").split()),
        path=path.resolve(),
        dependencies=deps,
        system_dependencies=system_deps,
        dependency_tags=dep_tags,
    )
