"""
Write a JUnit XML report for `rostree check`, so CI dashboards can show findings.

This module exists to keep one thing in one place: it is the only part of rostree
that *writes* XML, and it never reads any. That distinction matters, because
security scanners flag `xml.etree` on sight and their advice — use `defusedxml` —
is about parsing hostile input. `defusedxml` exports no `Element`, `SubElement`
or `ElementTree`, so there is nothing to switch to on the writing side, and
nothing to defend against either: the only untrusted values here are package
names, which ElementTree escapes.

The one place rostree does parse XML is `core/parser.py`, and that one does use
defusedxml.
"""

from __future__ import annotations

from pathlib import Path

# Semgrep's XML rule is not suppressed by a `# nosemgrep` trailing the import —
# only by one on the line before it, which is what this is.
# nosemgrep
from xml.etree.ElementTree import Element, ElementTree, SubElement  # nosec B405

__all__ = ["write_junit_report"]


def write_junit_report(
    path: Path,
    roots: list[str],
    cycles: list[list[str]],
    missing: list[str],
) -> None:
    """
    Emit a two-case JUnit suite: one for cycles, one for unresolved dependencies.

    Built with ElementTree rather than string concatenation because package names
    are arbitrary text, and getting the escaping right by hand is how malformed
    reports happen.
    """
    suite = Element(
        "testsuite",
        name="rostree check",
        tests="2",
        failures=str(bool(cycles) + bool(missing)),
        package=",".join(roots[:20]),
    )

    cycle_case = SubElement(suite, "testcase", classname="rostree", name="no dependency cycles")
    if cycles:
        failure = SubElement(
            cycle_case,
            "failure",
            message=f"{len(cycles)} dependency cycle(s)",
            type="DependencyCycle",
        )
        failure.text = "\n".join(" -> ".join(cycle) for cycle in cycles)

    missing_case = SubElement(
        suite, "testcase", classname="rostree", name="all dependencies resolve"
    )
    if missing:
        failure = SubElement(
            missing_case,
            "failure",
            message=f"{len(missing)} unresolved dependency name(s)",
            type="UnresolvedDependency",
        )
        failure.text = "\n".join(missing)

    path.parent.mkdir(parents=True, exist_ok=True)
    ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)
