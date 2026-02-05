"""Tests for package.xml parser."""

from pathlib import Path


from rostree.core.parser import (
    parse_package_xml,
    PackageInfo,
    _is_ros_package_dependency,
)


class TestIsRosPackageDependency:
    """Tests for _is_ros_package_dependency helper."""

    def test_valid_ros_package(self) -> None:
        assert _is_ros_package_dependency("rclpy") is True
        assert _is_ros_package_dependency("std_msgs") is True
        assert _is_ros_package_dependency("ament_cmake") is True

    def test_empty_name(self) -> None:
        assert _is_ros_package_dependency("") is False

    def test_starts_with_number(self) -> None:
        assert _is_ros_package_dependency("3rdparty") is False

    def test_python3_packages(self) -> None:
        assert _is_ros_package_dependency("python3") is False
        assert _is_ros_package_dependency("python3-pytest") is False
        assert _is_ros_package_dependency("python3-textual") is False
        assert _is_ros_package_dependency("python3-rich") is False

    def test_python3_prefix(self) -> None:
        assert _is_ros_package_dependency("python3-something") is False

    def test_lib_prefix(self) -> None:
        assert _is_ros_package_dependency("libboost-dev") is False
        assert _is_ros_package_dependency("libpng") is False


class TestPackageInfo:
    """Tests for PackageInfo dataclass."""

    def test_deduplicates_dependencies(self) -> None:
        info = PackageInfo(
            name="test",
            version="1.0",
            description="desc",
            path=Path("/test"),
            dependencies=["dep_a", "dep_b", "dep_a", "dep_c", "dep_b"],
        )
        # Should deduplicate while preserving order
        assert info.dependencies == ["dep_a", "dep_b", "dep_c"]


class TestParsePackageXml:
    """Tests for parse_package_xml function."""

    def test_not_found(self) -> None:
        assert parse_package_xml(Path("/nonexistent/package.xml")) is None

    def test_is_directory(self, tmp_path: Path) -> None:
        assert parse_package_xml(tmp_path) is None

    def test_valid_package(self, tmp_path: Path) -> None:
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
        assert len(info.dependencies) >= 2

    def test_invalid_xml(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.xml"
        pkg.write_text("not valid xml <<<>>>")
        assert parse_package_xml(pkg) is None

    def test_not_package_root(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.xml"
        pkg.write_text(
            """<?xml version="1.0"?>
<notpackage>
  <name>test</name>
</notpackage>
"""
        )
        assert parse_package_xml(pkg) is None

    def test_no_name(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.xml"
        pkg.write_text(
            """<?xml version="1.0"?>
<package format="3">
  <version>1.0.0</version>
</package>
"""
        )
        assert parse_package_xml(pkg) is None

    def test_empty_description(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.xml"
        pkg.write_text(
            """<?xml version="1.0"?>
<package format="3">
  <name>no_desc_pkg</name>
  <version>1.0.0</version>
</package>
"""
        )
        info = parse_package_xml(pkg)
        assert info is not None
        assert info.description == ""

    def test_include_tags_filter(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.xml"
        pkg.write_text(
            """<?xml version="1.0"?>
<package format="3">
  <name>filter_pkg</name>
  <version>1.0.0</version>
  <description>Test filtering</description>
  <depend>runtime_dep</depend>
  <exec_depend>exec_dep</exec_depend>
  <build_depend>build_dep</build_depend>
  <test_depend>test_dep</test_depend>
</package>
"""
        )
        # Only include depend and exec_depend
        info = parse_package_xml(pkg, include_tags=("depend", "exec_depend"))
        assert info is not None
        assert "runtime_dep" in info.dependencies
        assert "exec_dep" in info.dependencies
        assert "build_dep" not in info.dependencies
        assert "test_dep" not in info.dependencies

    def test_include_tags_invalid_tag(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.xml"
        pkg.write_text(
            """<?xml version="1.0"?>
<package format="3">
  <name>invalid_tag_pkg</name>
  <version>1.0.0</version>
  <description>Test invalid tag</description>
  <depend>valid_dep</depend>
</package>
"""
        )
        # Include a non-existent tag
        info = parse_package_xml(pkg, include_tags=("depend", "invalid_tag"))
        assert info is not None
        assert "valid_dep" in info.dependencies

    def test_all_dependency_types(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.xml"
        pkg.write_text(
            """<?xml version="1.0"?>
<package format="3">
  <name>all_deps_pkg</name>
  <version>1.0.0</version>
  <description>Test all dep types</description>
  <depend>dep1</depend>
  <exec_depend>dep2</exec_depend>
  <build_depend>dep3</build_depend>
  <build_export_depend>dep4</build_export_depend>
  <test_depend>dep5</test_depend>
</package>
"""
        )
        info = parse_package_xml(pkg)
        assert info is not None
        assert "dep1" in info.dependencies
        assert "dep2" in info.dependencies
        assert "dep3" in info.dependencies
        assert "dep4" in info.dependencies
        assert "dep5" in info.dependencies

    def test_filters_non_ros_deps(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.xml"
        pkg.write_text(
            """<?xml version="1.0"?>
<package format="3">
  <name>filter_non_ros</name>
  <version>1.0.0</version>
  <description>Test filtering non-ROS deps</description>
  <depend>rclpy</depend>
  <depend>python3-pytest</depend>
  <depend>libboost-dev</depend>
</package>
"""
        )
        info = parse_package_xml(pkg)
        assert info is not None
        assert "rclpy" in info.dependencies
        assert "python3-pytest" not in info.dependencies
        assert "libboost-dev" not in info.dependencies

    def test_empty_dep_text(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.xml"
        pkg.write_text(
            """<?xml version="1.0"?>
<package format="3">
  <name>empty_dep</name>
  <version>1.0.0</version>
  <description>Test empty dep</description>
  <depend></depend>
  <depend>valid_dep</depend>
</package>
"""
        )
        info = parse_package_xml(pkg)
        assert info is not None
        assert "valid_dep" in info.dependencies
        assert "" not in info.dependencies

    def test_whitespace_handling(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.xml"
        pkg.write_text(
            """<?xml version="1.0"?>
<package format="3">
  <name>  whitespace_pkg  </name>
  <version>  2.0.0  </version>
  <description>  Whitespace test  </description>
  <depend>  rclpy  </depend>
</package>
"""
        )
        info = parse_package_xml(pkg)
        assert info is not None
        assert info.name == "whitespace_pkg"
        assert info.version == "2.0.0"
        assert info.description == "Whitespace test"
        assert "rclpy" in info.dependencies
