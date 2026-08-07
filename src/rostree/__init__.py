"""rostree: visualize ROS 2 package dependencies as a tree (library, TUI, CLI)."""

from importlib.metadata import PackageNotFoundError, version

from rostree.api import (
    WorkspaceInfo,
    build_tree,
    get_package_info,
    list_known_packages,
    list_known_packages_by_source,
    scan_workspaces,
)

__all__ = [
    "build_tree",
    "get_package_info",
    "list_known_packages",
    "list_known_packages_by_source",
    "scan_workspaces",
    "WorkspaceInfo",
    "__version__",
]

try:
    __version__ = version("rostree")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"  # Not installed as package
