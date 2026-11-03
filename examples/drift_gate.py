"""
Fail CI when a package's dependency set changes without the snapshot changing too.

    python drift_gate.py my_robot_bringup deps.lock.json            # check
    python drift_gate.py my_robot_bringup deps.lock.json --update   # accept

Commit the snapshot next to the code. A pull request that pulls in, drops or
bumps a dependency then has to update it in the same diff — so the change is
something a reviewer sees, rather than something they find out about later.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rostree.api import build_graph, dependency_versions, diff_dependencies


def current(package: str) -> dict[str, str]:
    return dependency_versions(build_graph(package), exclude=[package])


def main(argv: list[str]) -> int:
    package, lock = argv[0], Path(argv[1])
    now = current(package)
    if "--update" in argv[2:]:
        lock.write_text(json.dumps(now, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {len(now)} dependencies to {lock}")
        return 0

    diff = diff_dependencies(json.loads(lock.read_text(encoding="utf-8")), now)
    if not diff:
        print(f"ok: {package} matches {lock}")
        return 0
    for name in diff.added:
        print(f"+ {name} {now[name]}".rstrip())
    for name in diff.removed:
        print(f"- {name}")
    for name, (old, new) in diff.changed.items():
        print(f"~ {name} {old} -> {new}")
    print(f"dependencies of {package} changed; rerun with --update if that is intended")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
