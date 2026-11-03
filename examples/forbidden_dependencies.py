"""
Enforce an architecture rule in CI: some packages must never depend on others.

    python forbidden_dependencies.py 'my_robot_driver_*' 'nav2_*'

Fails (exit 1) if any package matching the first glob depends, at any depth, on
a package matching the second — and prints the shortest chain that does it, so
the failure says *where* to cut, not just that a rule was broken.
"""

from __future__ import annotations

import fnmatch
import sys

from rostree.api import build_graph, get_index
from rostree.core.analysis import shortest_paths


def violations(source_glob: str, forbidden_glob: str) -> list[list[str]]:
    index = get_index()
    sources = [n for n in index.workspace_names() if fnmatch.fnmatchcase(n, source_glob)]
    found = []
    for source in sources:
        graph = build_graph(source, index=index)
        reached = sorted(n for n in graph.depths if fnmatch.fnmatchcase(n, forbidden_glob))
        for target in reached:
            if target != source:
                found.append(shortest_paths(graph, source, target, limit=1)[0])
    return found


def main(argv: list[str]) -> int:
    source_glob, forbidden_glob = argv
    bad = violations(source_glob, forbidden_glob)
    for path in bad:
        print("forbidden: " + " -> ".join(path))
    if not bad:
        print(f"ok: nothing matching {source_glob!r} depends on {forbidden_glob!r}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
