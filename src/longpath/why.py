"""`longpath why` - explain where a path's length budget went.

Pure string analysis: the path does not need to exist, and Windows-style
paths can be analysed on any OS (paste one out of a log on your Linux box).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from .core import DEFAULT_LIMIT, WINDOWS, displayable, wchar_len


@dataclass
class WhyComponent:
    name: str        # component text ("C:\\" for the drive root)
    length: int      # UTF-16 units of this component alone
    cum: int         # cumulative path length up to and including this one
    crosses: bool    # first component that pushes past the budget

    def to_dict(self) -> dict:
        return {
            "name": displayable(self.name),
            "length": self.length,
            "cum": self.cum,
            "crosses_budget": self.crosses,
        }


@dataclass
class WhyResult:
    path: str
    length: int
    limit: int
    style: str                        # "windows" | "posix"
    components: List[WhyComponent] = field(default_factory=list)
    suggestions: List[dict] = field(default_factory=list)

    @property
    def budget(self) -> int:
        return self.limit - 1

    @property
    def over(self) -> int:
        return self.length - self.budget

    def to_dict(self) -> dict:
        return {
            "path": displayable(self.path),
            "length": self.length,
            "limit": self.limit,
            "budget": self.budget,
            "over": max(self.over, 0),
            "within_budget": self.over <= 0,
            "style": self.style,
            "components": [c.to_dict() for c in self.components],
            "suggestions": self.suggestions,
        }


def _looks_windows(path: str) -> bool:
    if "\\" in path:
        return True
    if len(path) >= 2 and path[1] == ":":
        return True
    # On Windows, `src/deep/file` is still a native path (forward slashes
    # are accepted); only a rooted "/..." string is treated as foreign.
    return WINDOWS and not path.startswith("/")


def _split(path: str) -> tuple:
    """Return (style, root, parts) without touching the filesystem."""
    if _looks_windows(path):
        p = path.replace("/", "\\")
        if p.startswith("\\\\"):
            # UNC: \\server\share\rest -> root is \\server\share\
            bits = p.lstrip("\\").split("\\")
            server_share = bits[:2]
            root = "\\\\" + "\\".join(server_share) + "\\"
            rest = "\\".join(bits[2:])
        elif len(p) >= 2 and p[1] == ":":
            root = p[:2] + "\\"
            rest = p[2:].lstrip("\\")
        else:
            root = ""
            rest = p.lstrip("\\")
        parts = [x for x in rest.split("\\") if x]
        return "windows", root, parts
    root = "/" if path.startswith("/") else ""
    parts = [x for x in path.split("/") if x]
    return "posix", root, parts


def why_path(path: str, *, limit: int = DEFAULT_LIMIT) -> WhyResult:
    """Break a path down component by component against the budget."""
    # Make relative native paths absolute so the answer reflects reality;
    # foreign-style paths (e.g. a Windows path pasted on Linux) are analysed
    # exactly as given.
    style_guess = "windows" if _looks_windows(path) else "posix"
    native = (style_guess == "windows") == WINDOWS
    is_abs = path.startswith(("/", "\\\\")) or (len(path) >= 2 and path[1] == ":")
    if native and not is_abs:
        path = os.path.abspath(path)

    style, root, parts = _split(path)

    result = WhyResult(path=path, length=0, limit=limit, style=style)
    budget = result.budget

    cum = 0
    crossed = False

    def push(name: str, new_cum: int) -> None:
        nonlocal crossed
        crosses = not crossed and new_cum > budget
        crossed = crossed or crosses
        result.components.append(WhyComponent(name, wchar_len(name), new_cum, crosses))

    if root:
        cum = wchar_len(root)
        push(root, cum)
    for i, part in enumerate(parts):
        if cum == 0:                # relative path, first component
            cum = wchar_len(part)
        elif root and i == 0:       # directly after "C:\", "\\server\share\", "/"
            cum = cum + wchar_len(part)
        else:                       # needs a separator
            cum = cum + 1 + wchar_len(part)
        push(part, cum)

    result.length = cum if result.components else wchar_len(path)

    # Suggestions: which single rename buys the most room?
    candidates = sorted(
        (c for c in result.components if c.name != root),
        key=lambda c: c.length,
        reverse=True,
    )
    for c in candidates[:3]:
        saves = c.length - 1
        if saves <= 0:
            continue
        result.suggestions.append({
            "component": displayable(c.name),
            "length": c.length,
            "saves_up_to": saves,
        })
    return result
