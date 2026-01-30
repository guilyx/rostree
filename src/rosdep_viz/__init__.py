"""rosdep_viz: visualize ROS 2 package dependencies as a tree (library, TUI, API)."""

from rosdep_viz.api import build_tree, get_package_info, list_known_packages

__all__ = [
    "build_tree",
    "get_package_info",
    "list_known_packages",
]
__version__ = "0.1.0"
