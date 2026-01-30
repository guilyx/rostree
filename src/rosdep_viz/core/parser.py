"""Parse ROS 2 package.xml for package metadata and dependencies."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

# Tags that declare dependency on another ROS package (we collect these for the tree).
DEPENDENCY_TAGS = (
    "depend",
    "exec_depend",
    "build_depend",
    "build_export_depend",
    "test_depend",
)


@dataclass
class PackageInfo:
    """Metadata parsed from a package.xml."""

    name: str
    version: str
    description: str
    path: Path
    dependencies: list[str]  # ROS package names only (no system/vendor deps)

    def __post_init__(self) -> None:
        # Normalize to set of unique names (order can be preserved if needed)
        self.dependencies = list(dict.fromkeys(self.dependencies))


def _is_ros_package_dependency(name: str) -> bool:
    """Heuristic: ROS packages are typically lowercase with underscores."""
    if not name or not name[0].isalpha():
        return False
    # Filter common non-ROS entries
    if name in ("python3", "python3-pytest", "python3-textual", "python3-rich"):
        return False
    if name.startswith("python3-") or name.startswith("lib"):
        return False
    return True


def parse_package_xml(path: Path) -> PackageInfo | None:
    """
    Parse a package.xml file and return package name, version, description, and dependencies.

    Only dependency tags that typically refer to ROS packages are collected;
    buildtool_depend and system-style deps may be excluded by heuristic.
    Returns None if the file cannot be read or is not valid package.xml.
    """
    if not path.exists() or not path.is_file():
        return None
    try:
        tree = ET.parse(path)
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

    deps: list[str] = []
    for tag in DEPENDENCY_TAGS:
        for elem in root.findall(f".//{tag}"):
            if elem.text:
                dep = elem.text.strip()
                if _is_ros_package_dependency(dep):
                    deps.append(dep)

    if not name:
        return None
    return PackageInfo(
        name=name,
        version=version,
        description=description or "",
        path=path.resolve(),
        dependencies=deps,
    )
