"""Shared helpers for the longpath test suite."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SRC)

from longpath.core import ext_path  # noqa: E402

WINDOWS = os.name == "nt"
LINUX = sys.platform.startswith("linux")
MACOS = sys.platform == "darwin"


def mkfile(path: str, content: str = "x") -> str:
    """Create a file, transparently handling >260-char paths on Windows."""
    os.makedirs(ext_path(os.path.dirname(path)), exist_ok=True)
    with open(ext_path(path), "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


def make_long_tree(root: str, target_len: int = 320) -> str:
    """Grow a directory chain until its path exceeds *target_len* chars.

    Returns the (unprefixed) path of a file created at the bottom.
    """
    seg = "loooooooooooooooooooooooooooooooooooooong"  # 41 chars
    p = os.path.abspath(root)
    while len(p) < target_len:
        p = os.path.join(p, seg)
    os.makedirs(ext_path(p), exist_ok=True)
    return mkfile(os.path.join(p, "deep_file.txt"))


def run_cli(*args: str, cwd: str = None, input_text: str = None):
    """Run `python -m longpath ...` hermetically and capture everything."""
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("NO_COLOR", None)
    return subprocess.run(
        [sys.executable, "-m", "longpath", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env=env,
        input=input_text,
        stdin=subprocess.DEVNULL if input_text is None else None,
        timeout=120,
    )


@pytest.fixture
def tree(tmp_path):
    """A small, healthy tree."""
    root = tmp_path / "proj"
    mkfile(str(root / "a.txt"))
    mkfile(str(root / "sub" / "b.txt"))
    mkfile(str(root / "sub" / "nested" / "c.txt"))
    return root
