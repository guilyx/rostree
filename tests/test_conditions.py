"""REP 149 dependency conditions, and the parser honouring them."""

from __future__ import annotations

from pathlib import Path

import pytest

from rostree.core.conditions import (
    ConditionError,
    condition_context,
    context_key,
    evaluate_condition,
)
from rostree.core.parser import clear_parse_cache, parse_package_xml

ROS2_JAZZY = {"ROS_VERSION": "2", "ROS_DISTRO": "jazzy", "ROS_PYTHON_VERSION": "3"}


class TestEvaluateCondition:
    @pytest.mark.parametrize(
        ("condition", "expected"),
        [
            ("$ROS_VERSION == 2", True),
            ("$ROS_VERSION == 1", False),
            ("$ROS_VERSION != 1", True),
            # Distro names are alphabetical upstream so that this works as a
            # string comparison; it is the documented semantics, not a shortcut.
            ("$ROS_DISTRO >= humble", True),
            ("$ROS_DISTRO > jazzy", False),
            ("$ROS_DISTRO <= jazzy", True),
            ("$ROS_DISTRO < humble", False),
            ("$ROS_VERSION == 1 or $ROS_DISTRO == jazzy", True),
            ("$ROS_VERSION == 2 and $ROS_DISTRO == humble", False),
            # `and` binds tighter than `or`.
            ("$ROS_VERSION == 1 and $ROS_DISTRO == jazzy or $ROS_VERSION == 2", True),
            ("$ROS_VERSION == 2 and ($ROS_DISTRO == iron or $ROS_DISTRO == jazzy)", True),
            ("( ( $ROS_VERSION == 2 ) )", True),
            # An unset variable is the empty string, as in catkin_pkg.
            ('$NOT_SET == ""', True),
            ("$NOT_SET == 2", False),
            # Quoted text is a literal, not a variable reference.
            ('"$ROS_DISTRO" == jazzy', False),
            ("'jazzy' == $ROS_DISTRO", True),
        ],
    )
    def test_grammar(self, condition: str, expected: bool) -> None:
        assert evaluate_condition(condition, ROS2_JAZZY) is expected

    @pytest.mark.parametrize("condition", [None, "", "   "])
    def test_absent_condition_is_unconditional(self, condition: str | None) -> None:
        assert evaluate_condition(condition, ROS2_JAZZY) is True

    @pytest.mark.parametrize(
        "condition",
        [
            "$ROS_VERSION ==",
            "== 2",
            "($ROS_VERSION == 2",
            "$ROS_VERSION == 2)",
            "$ROS_VERSION = 2",
            "$ROS_VERSION == 2 and",
            "$ROS_VERSION",
            "and",
            "($ROS_VERSION == 2 $ROS_DISTRO",  # an unclosed group followed by more input
        ],
    )
    def test_malformed_conditions_are_rejected(self, condition: str) -> None:
        with pytest.raises(ConditionError):
            evaluate_condition(condition, ROS2_JAZZY)

    def test_defaults_to_the_process_environment(self, monkeypatch) -> None:
        monkeypatch.setenv("ROS_DISTRO", "jazzy")
        assert evaluate_condition("$ROS_DISTRO == jazzy") is True

    def test_manifest_text_is_never_evaluated_as_code(self) -> None:
        """The manifest is untrusted; catkin_pkg's own evaluator calls eval()."""
        with pytest.raises(ConditionError):
            evaluate_condition('__import__("os").system("true")', ROS2_JAZZY)


class TestContext:
    def test_defaults_to_ros2_when_nothing_is_sourced(self) -> None:
        ctx = condition_context({})
        assert ctx["ROS_VERSION"] == "2"
        assert ctx["ROS_PYTHON_VERSION"] == "3"

    def test_environment_wins_over_defaults(self) -> None:
        assert condition_context({"ROS_VERSION": "1"})["ROS_VERSION"] == "1"

    def test_key_matches_context_rules(self) -> None:
        assert context_key({}) == ("2", "", "3")
        assert context_key({"ROS_DISTRO": "jazzy"}) == ("2", "jazzy", "3")
        # An explicitly empty variable is not replaced by the default.
        assert context_key({"ROS_VERSION": ""}) == ("", "", "3")


DUAL_PACKAGE = """<?xml version="1.0"?>
<package format="3">
  <name>dual_pkg</name>
  <version>1.0.0</version>
  <description>Builds on ROS 1 and ROS 2.</description>
  <depend condition="$ROS_VERSION == 1">roscpp</depend>
  <depend condition="$ROS_VERSION == 2">rclcpp</depend>
  <exec_depend condition="$ROS_VERSION == 1">python-yaml</exec_depend>
  <exec_depend condition="$ROS_VERSION == 2">python3-yaml</exec_depend>
  <depend>std_msgs</depend>
  <export>
    <build_type condition="$ROS_VERSION == 2">ament_cmake</build_type>
    <depend>not_a_dependency</depend>
  </export>
</package>
"""


@pytest.fixture
def dual_manifest(tmp_path: Path) -> Path:
    manifest = tmp_path / "dual_pkg" / "package.xml"
    manifest.parent.mkdir()
    manifest.write_text(DUAL_PACKAGE)
    return manifest


class TestParserHonoursConditions:
    def test_ros2_sees_only_ros2_dependencies(self, dual_manifest: Path, monkeypatch) -> None:
        monkeypatch.setenv("ROS_VERSION", "2")
        info = parse_package_xml(dual_manifest)
        assert info is not None
        # roscpp never resolves on ROS 2, so before this `rostree check` failed CI
        # for every package that also supports ROS 1.
        assert info.dependencies == ["rclcpp", "std_msgs"]
        assert info.system_dependencies == ["python3-yaml"]

    def test_ros1_sees_only_ros1_dependencies(self, dual_manifest: Path, monkeypatch) -> None:
        monkeypatch.setenv("ROS_VERSION", "1")
        info = parse_package_xml(dual_manifest)
        assert info is not None
        assert info.dependencies == ["roscpp", "std_msgs"]
        assert info.system_dependencies == ["python-yaml"]

    def test_unsourced_shell_is_treated_as_ros2(self, dual_manifest: Path, monkeypatch) -> None:
        monkeypatch.delenv("ROS_VERSION", raising=False)
        info = parse_package_xml(dual_manifest)
        assert info is not None
        assert "rclcpp" in info.dependencies
        assert "roscpp" not in info.dependencies

    def test_cache_is_keyed_on_the_condition_context(
        self, dual_manifest: Path, monkeypatch
    ) -> None:
        """Switching ROS_VERSION mid-process must not return the other answer."""
        clear_parse_cache()
        monkeypatch.setenv("ROS_VERSION", "2")
        assert "rclcpp" in parse_package_xml(dual_manifest).dependencies
        monkeypatch.setenv("ROS_VERSION", "1")
        assert "roscpp" in parse_package_xml(dual_manifest).dependencies

    def test_dependency_tags_inside_export_are_ignored(self, dual_manifest: Path) -> None:
        """REP 149 puts dependency tags directly under <package>; <export> is free-form."""
        info = parse_package_xml(dual_manifest)
        assert info is not None
        assert "not_a_dependency" not in info.dependencies

    def test_unparsable_condition_keeps_the_dependency(self, tmp_path: Path) -> None:
        """A typo in a condition must not make the tree quietly smaller."""
        manifest = tmp_path / "typo_pkg" / "package.xml"
        manifest.parent.mkdir()
        manifest.write_text(
            '<package format="3"><name>typo_pkg</name><version>1.0.0</version>'
            "<description>x</description>"
            '<depend condition="$ROS_VERSION = 2">rclcpp</depend></package>'
        )
        info = parse_package_xml(manifest)
        assert info is not None
        assert info.dependencies == ["rclcpp"]
