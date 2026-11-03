"""
Which of your packages would a change ripple furthest from?

    python ripple_report.py [N]

Ranks your workspace packages by how many other packages depend on them,
directly or transitively. The top of this list is where a breaking change costs
the most, and where tests and review matter most.
"""

from __future__ import annotations

import sys

from rostree.api import get_index, reverse_dependencies


def ripple(limit: int = 10) -> list[tuple[str, int, int]]:
    index = get_index()
    rows = []
    for name in index.workspace_names():
        direct = reverse_dependencies(name, index=index)
        everything = reverse_dependencies(name, index=index, transitive=True)
        rows.append((name, len(direct), len(everything)))
    rows.sort(key=lambda row: (-row[2], -row[1], row[0]))
    return rows[:limit]


def main(argv: list[str]) -> int:
    limit = int(argv[0]) if argv else 10
    print(f"{'package':32} {'direct':>7} {'transitive':>11}")
    for name, direct, total in ripple(limit):
        print(f"{name:32} {direct:>7} {total:>11}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
