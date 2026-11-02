"""Evaluate the ``condition`` attribute on package.xml dependencies (REP 149).

A format-3 manifest can make a dependency conditional::

    <depend condition="$ROS_VERSION == 1">roscpp</depend>
    <depend condition="$ROS_VERSION == 2">rclcpp</depend>

Packages that build on both ROS 1 and ROS 2 do this constantly. Ignoring the
attribute makes ``roscpp`` look like a dependency on a ROS 2 machine, where it
never resolves — so ``rostree check`` fails CI for a package that is fine.

The grammar is the one catkin_pkg implements, which colcon and ament use::

    expr       := and_expr ("or" and_expr)*
    and_expr   := atom ("and" atom)*
    atom       := "(" expr ")" | term OP term
    term       := "$" NAME | value
    OP         := "==" | "!=" | ">=" | ">" | "<=" | "<"

Operands compare as strings. That is deliberate upstream, not a shortcut here:
ROS distro names are chosen in alphabetical order precisely so that
``$ROS_DISTRO >= humble`` works as a string comparison. A ``$NAME`` that is not
set evaluates to the empty string, again as catkin_pkg does.

Nothing here calls ``eval``. The manifest is untrusted text, and catkin_pkg's
own evaluator formats operands into a string it then evaluates; a hand-written
recursive-descent parser over a closed token set has no such exposure.
"""

from __future__ import annotations

import os
import re
from typing import Callable, Mapping

__all__ = ["ConditionError", "condition_context", "context_key", "evaluate_condition"]

#: Context defaults for variables a ROS 2 build tool would always set. rostree is
#: a ROS 2 tool, so a shell that has not sourced a setup file is still ROS 2.
_DEFAULTS = {"ROS_VERSION": "2", "ROS_PYTHON_VERSION": "3"}

#: The variables real-world conditions test. They are folded into the parse cache
#: key, so changing one mid-process cannot serve a stale answer.
CONTEXT_VARS = ("ROS_VERSION", "ROS_DISTRO", "ROS_PYTHON_VERSION")

_OPERATORS: dict[str, Callable[[str, str], bool]] = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    "<": lambda a, b: a < b,
}

# Longest operators first, so ">=" is never read as ">" followed by "=".
_TOKEN = re.compile(
    r"""\s*(?:
        (?P<op>==|!=|>=|<=|>|<)
      | (?P<paren>[()])
      | \$(?P<var>[A-Za-z0-9_]+)
      | "(?P<dq>[^"]*)"
      | '(?P<sq>[^']*)'
      | (?P<word>[A-Za-z0-9_.\-]+)
    )""",
    re.VERBOSE,
)


class ConditionError(ValueError):
    """A condition attribute that does not follow the REP 149 grammar."""


def condition_context(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The variables a condition is evaluated against: the environment, plus defaults."""
    context = dict(os.environ if environ is None else environ)
    for name, value in _DEFAULTS.items():
        context.setdefault(name, value)
    return context


def context_key(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """
    A small, hashable fingerprint of the context, for cache keys.

    Called on every parse-cache lookup, so it reads the three variables directly
    rather than copying the whole environment the way :func:`condition_context` does.
    """
    env = os.environ if environ is None else environ
    # Same rule as condition_context: a default applies only when a variable is
    # unset, never when it is set to the empty string.
    return tuple(env.get(name, _DEFAULTS.get(name, "")) for name in CONTEXT_VARS)


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    text = text.strip()
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if match is None or match.end() == pos:
            raise ConditionError(f"unexpected input at {text[pos:]!r}")
        pos = match.end()
        kind = match.lastgroup
        value = match.group(kind)
        if kind == "word" and value in ("and", "or"):
            tokens.append(("logic", value))
        elif kind in ("dq", "sq"):
            tokens.append(("word", value))
        else:
            tokens.append((kind, value))
    return tokens


class _Parser:
    """Recursive descent over the token list; evaluates as it parses."""

    def __init__(self, tokens: list[tuple[str, str]], context: Mapping[str, str]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.context = context

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> tuple[str, str]:
        token = self.peek()
        if token is None:
            raise ConditionError("condition ends too early")
        self.pos += 1
        return token

    def parse(self) -> bool:
        if not self.tokens:
            raise ConditionError("empty condition")
        result = self.expr()
        if self.peek() is not None:
            raise ConditionError(f"unexpected {self.peek()[1]!r}")
        return result

    def expr(self) -> bool:
        result = self.and_expr()
        while self.peek() == ("logic", "or"):
            self.take()
            rhs = self.and_expr()  # always parse both sides, so bad syntax is caught
            result = result or rhs
        return result

    def and_expr(self) -> bool:
        result = self.atom()
        while self.peek() == ("logic", "and"):
            self.take()
            rhs = self.atom()
            result = result and rhs
        return result

    def atom(self) -> bool:
        if self.peek() == ("paren", "("):
            self.take()
            result = self.expr()
            if self.take() != ("paren", ")"):
                raise ConditionError("missing ')'")
            return result
        lhs = self.term()
        kind, op = self.take()
        if kind != "op":
            raise ConditionError(f"expected a comparison operator, got {op!r}")
        rhs = self.term()
        return _OPERATORS[op](lhs, rhs)

    def term(self) -> str:
        kind, value = self.take()
        if kind == "var":
            return str(self.context.get(value, ""))
        if kind == "word":
            return value
        raise ConditionError(f"expected a value or $VARIABLE, got {value!r}")


def evaluate_condition(condition: str | None, context: Mapping[str, str] | None = None) -> bool:
    """
    True when ``condition`` holds in ``context`` (the environment by default).

    ``None`` or an empty attribute means unconditional. Raises
    :class:`ConditionError` on text that does not follow the grammar; callers
    that would rather keep a dependency than drop it on a typo should catch it.
    """
    if condition is None or not condition.strip():
        return True
    if context is None:
        context = condition_context()
    return _Parser(_tokenize(condition), context).parse()
