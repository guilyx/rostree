"""
Write the dependency graph in a format rostree does not ship: here, CSV.

    python export_edges.py my_robot_bringup > edges.csv

`build_graph` returns plain data — packages, edges, what is missing — so any
other format is a loop away. The same shape works for PlantUML, a database
import, or the input of another analysis tool.
"""

from __future__ import annotations

import csv
import sys

from rostree.api import build_graph, get_index


def rows(package: str):
    index = get_index()
    graph = build_graph(package, index=index)
    for parent, children in sorted(graph.edges.items()):
        source = index.get(parent)
        for child in children:
            target = index.get(child)
            yield {
                "from": parent,
                "to": child,
                "from_source": source.kind.value if source else "missing",
                "to_source": target.kind.value if target else "missing",
                "depth": graph.depths.get(parent, ""),
            }


def main(argv: list[str]) -> int:
    writer = csv.DictWriter(
        sys.stdout, fieldnames=["from", "to", "from_source", "to_source", "depth"]
    )
    writer.writeheader()
    writer.writerows(rows(argv[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
