"""Refuse deletes that would wipe the working directory or its parent."""

from __future__ import annotations

import os
from typing import Optional


def cwd_delete_reason(path: str) -> Optional[str]:
    """Why *path* must not be deleted, or ``None`` if the cwd guard is silent.

    Root-device refusal stays in :func:`longpath.rm.rm_path` so this only
    covers the current working directory and its immediate parent.
    """
    try:
        target = os.path.realpath(os.path.abspath(path))
        cwd = os.path.realpath(os.getcwd())
    except OSError:
        return None
    if os.path.normcase(target) == os.path.normcase(cwd):
        return "refusing to delete the current working directory"
    parent = os.path.dirname(cwd)
    if not parent or os.path.dirname(parent) == parent:
        return None
    try:
        parent_real = os.path.realpath(parent)
    except OSError:
        return None
    if os.path.normcase(target) == os.path.normcase(parent_real):
        return "refusing to delete the parent of the current working directory"
    return None
