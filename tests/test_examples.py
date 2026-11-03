"""The programs in examples/ run, as real subprocesses, and say what the docs say they do."""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import write_package

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """
    A distro prefix and a source workspace, with one architecture violation:
    a camera driver that reaches into navigation.
    """
    share = tmp_path / "distro" / "share"
    write_package(share, "ros_environment")  # marks the prefix as the distro
    write_package(share, "rclcpp")
    write_package(share, "nav2_core", depends=["rclcpp"])

    src = tmp_path / "ws" / "src"
    write_package(src, "my_robot_msgs")
    write_package(src, "my_robot_utils", depends=["my_robot_msgs", "rclcpp"])
    write_package(src, "my_robot_driver_cam", depends=["my_robot_utils", "nav2_core"])
    write_package(src, "my_robot_driver_lidar", depends=["my_robot_utils"])
    write_package(src, "my_robot_bringup", depends=["my_robot_driver_cam", "my_robot_driver_lidar"])
    return {
        **os.environ,
        "AMENT_PREFIX_PATH": str(tmp_path / "distro"),
        "COLCON_PREFIX_PATH": "",
        "ROS2_WORKSPACE": str(tmp_path / "ws"),
        "COLCON_WORKSPACE": "",
    }


def run(env: dict[str, str], script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(EXAMPLES / script), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_every_example_is_covered_here() -> None:
    tested = {"forbidden_dependencies.py", "ripple_report.py", "drift_gate.py", "export_edges.py"}
    assert {p.name for p in EXAMPLES.glob("*.py")} == tested


class TestForbiddenDependencies:
    def test_reports_the_chain_that_breaks_the_rule(self, env) -> None:
        result = run(env, "forbidden_dependencies.py", "my_robot_driver_*", "nav2_*")
        assert result.returncode == 1, result.stderr
        assert "forbidden: my_robot_driver_cam -> nav2_core" in result.stdout
        assert "lidar" not in result.stdout

    def test_passes_when_the_rule_holds(self, env) -> None:
        result = run(env, "forbidden_dependencies.py", "my_robot_driver_*", "my_robot_bringup")
        assert result.returncode == 0, result.stderr
        assert result.stdout.startswith("ok:")


class TestRippleReport:
    def test_ranks_by_transitive_dependents(self, env) -> None:
        result = run(env, "ripple_report.py", "3")
        assert result.returncode == 0, result.stderr
        rows = [line.split() for line in result.stdout.splitlines()[1:]]
        # msgs <- utils <- both drivers <- bringup: four packages ripple from it.
        assert rows[0] == ["my_robot_msgs", "1", "4"]
        assert rows[1] == ["my_robot_utils", "2", "3"]
        assert len(rows) == 3
        # The distro is not "your" package and is never ranked.
        assert "nav2_core" not in result.stdout


class TestDriftGate:
    def test_lock_then_detect_a_new_dependency(self, env, tmp_path: Path) -> None:
        lock = tmp_path / "deps.lock.json"
        assert run(env, "drift_gate.py", "my_robot_bringup", str(lock), "--update").returncode == 0
        assert "my_robot_utils" in json.loads(lock.read_text())

        clean = run(env, "drift_gate.py", "my_robot_bringup", str(lock))
        assert clean.returncode == 0, clean.stdout + clean.stderr

        # A package the dependency set has never contained, so it must show as added.
        write_package(tmp_path / "ws" / "src", "my_robot_extra")
        write_package(
            tmp_path / "ws" / "src",
            "my_robot_bringup",
            depends=["my_robot_driver_cam", "my_robot_driver_lidar", "my_robot_extra"],
        )
        drift = run(env, "drift_gate.py", "my_robot_bringup", str(lock))
        assert drift.returncode == 1
        assert "+ my_robot_extra 1.0.0" in drift.stdout


class TestExportEdges:
    def test_writes_csv_with_sources(self, env) -> None:
        result = run(env, "export_edges.py", "my_robot_driver_cam")
        assert result.returncode == 0, result.stderr
        rows = list(csv.DictReader(io.StringIO(result.stdout)))
        edge = next(r for r in rows if r["to"] == "nav2_core")
        assert edge == {
            "from": "my_robot_driver_cam",
            "to": "nav2_core",
            "from_source": "source",
            "to_source": "system",
            "depth": "0",
        }
