"""Tests for package.xml parser."""

from pathlib import Path


from rosdep_viz.core.parser import parse_package_xml


def test_parse_package_xml_not_found() -> None:
    assert parse_package_xml(Path("/nonexistent/package.xml")) is None


def test_parse_package_xml_real(tmp_path: Path) -> None:
    pkg = tmp_path / "package.xml"
    pkg.write_text(
        """<?xml version="1.0"?>
<package format="3">
  <name>test_pkg</name>
  <version>1.2.3</version>
  <description>A test package</description>
  <depend>rclpy</depend>
  <exec_depend>std_msgs</exec_depend>
  <build_depend>ament_cmake</build_depend>
</package>
"""
    )
    info = parse_package_xml(pkg)
    assert info is not None
    assert info.name == "test_pkg"
    assert info.version == "1.2.3"
    assert info.description == "A test package"
    assert "rclpy" in info.dependencies
    assert "std_msgs" in info.dependencies
    # ament_cmake may be filtered by _is_ros_package_dependency
    assert len(info.dependencies) >= 2
