"""Core library: package discovery, package.xml parsing, dependency tree building."""

from rostree.core.finder import (
    find_package_path,
    list_package_paths,
    list_packages_by_source,
    scan_for_workspaces,
    WorkspaceInfo,
)
from rostree.core.parser import parse_package_xml
from rostree.core.tree import DependencyNode, build_dependency_tree

__all__ = [
    "find_package_path",
    "list_package_paths",
    "list_packages_by_source",
    "scan_for_workspaces",
    "WorkspaceInfo",
    "parse_package_xml",
    "DependencyNode",
    "build_dependency_tree",
]
