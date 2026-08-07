"""Decide which packages a command should look at.

On a sourced ROS 2 machine most of what rostree can see belongs to the distro
rather than to you, so almost every command wants a way to narrow the field.
Filtering happens during traversal: a package that is filtered out is neither
shown nor followed, so anything reachable only through it disappears too. That
is the useful behaviour ("show me my workspace") but it does hide edges, which
is why :class:`FilterReport` exists — callers are expected to say what was cut.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field

from rostree.core.index import PackageEntry, PackageIndex, SourceKind
from rostree.core.parser import DEPENDENCY_TAGS

#: Dependency tags to traverse, per --dep-type choice.
DEP_TYPE_TAGS: dict[str, tuple[str, ...] | None] = {
    "runtime": ("depend", "exec_depend"),
    "build": ("depend", "build_depend", "build_export_depend"),
    "test": ("depend", "test_depend"),
    "all": None,  # None means "every tag in DEPENDENCY_TAGS"
}

DEP_TYPE_CHOICES = tuple(DEP_TYPE_TAGS)


def tags_for_dep_type(dep_type: str) -> tuple[str, ...] | None:
    """Translate a --dep-type choice into package.xml tags."""
    if dep_type not in DEP_TYPE_TAGS:
        raise ValueError(f"unknown dependency type: {dep_type!r}")
    tags = DEP_TYPE_TAGS[dep_type]
    if tags is None:
        return None
    return tuple(t for t in tags if t in DEPENDENCY_TAGS)


@dataclass
class FilterReport:
    """What a filter removed, so a command can say so rather than quietly lie."""

    excluded: set[str] = field(default_factory=set)

    def note(self, name: str) -> None:
        self.excluded.add(name)

    def __bool__(self) -> bool:
        return bool(self.excluded)

    def summary(self, limit: int = 6) -> str:
        """One line naming what was held back."""
        if not self.excluded:
            return ""
        names = sorted(self.excluded)
        shown = ", ".join(names[:limit])
        if len(names) > limit:
            shown += f", and {len(names) - limit} more"
        return f"{len(names)} package(s) hidden by filters: {shown}"


@dataclass(frozen=True)
class PackageFilter:
    """A name/source predicate applied while walking dependencies."""

    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    only_workspace: bool = False

    @classmethod
    def from_args(
        cls,
        *,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        only_workspace: bool = False,
    ) -> PackageFilter:
        """Build a filter from CLI-style arguments."""
        return cls(
            include=tuple(include or ()),
            exclude=tuple(exclude or ()),
            only_workspace=bool(only_workspace),
        )

    @property
    def is_noop(self) -> bool:
        """True when this filter cannot remove anything."""
        return not (self.include or self.exclude or self.only_workspace)

    def allows(self, name: str, entry: PackageEntry | None = None) -> bool:
        """
        Should ``name`` appear in the output?

        Patterns are shell globs matched against the package name, so
        ``nav2_*`` and ``*_msgs`` both work. Excludes win over includes.
        """
        if any(fnmatch.fnmatchcase(name, pattern) for pattern in self.exclude):
            return False
        if self.include and not any(fnmatch.fnmatchcase(name, pattern) for pattern in self.include):
            return False
        if self.only_workspace and entry is not None and entry.kind is SourceKind.SYSTEM:
            return False
        return True

    def filter_names(
        self,
        names: list[str],
        index: PackageIndex | None = None,
        report: FilterReport | None = None,
    ) -> list[str]:
        """Apply the filter to a flat list of package names, preserving order."""
        if self.is_noop:
            return list(names)
        kept = []
        for name in names:
            entry = index.get(name) if index is not None else None
            if self.allows(name, entry):
                kept.append(name)
            elif report is not None:
                report.note(name)
        return kept
