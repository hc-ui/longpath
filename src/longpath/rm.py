"""Robust deletion that works where Explorer, `del` and `rmdir` give up.

Key properties:

* uses extended-length ``\\\\?\\`` paths on Windows, so trees beyond the
  260-char MAX_PATH limit are deleted regardless of the LongPathsEnabled
  policy;
* never follows symlinks or junctions - the link itself is removed, the
  target is left untouched (this is the mistake that turns "clean a temp
  dir" into "wipe the user profile");
* clears the read-only attribute when it blocks deletion;
* keeps going after individual failures and reports them all at the end.
"""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from typing import List, Tuple

from .core import WINDOWS, ext_path, safe_walk, unext


@dataclass
class RmResult:
    path: str
    ok: bool = False
    files_removed: int = 0
    dirs_removed: int = 0
    errors: List[Tuple[str, str]] = field(default_factory=list)  # (path, error)
    dry_run: bool = False

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "ok": self.ok,
            "dry_run": self.dry_run,
            "files_removed": self.files_removed,
            "dirs_removed": self.dirs_removed,
            "errors": [{"path": p, "error": e} for p, e in self.errors],
        }


def _unlink(p: str, result: RmResult) -> bool:
    try:
        os.unlink(p)
        return True
    except PermissionError:
        try:
            os.chmod(p, stat.S_IWRITE)
            os.unlink(p)
            return True
        except OSError as exc:
            result.errors.append((unext(p), str(exc)))
            return False
    except OSError as exc:
        result.errors.append((unext(p), str(exc)))
        return False


def _rmdir(p: str, result: RmResult) -> bool:
    try:
        os.rmdir(p)
        return True
    except PermissionError:
        try:
            os.chmod(p, stat.S_IWRITE)
            os.rmdir(p)
            return True
        except OSError as exc:
            result.errors.append((unext(p), str(exc)))
            return False
    except OSError as exc:
        result.errors.append((unext(p), str(exc)))
        return False


def _is_reparse_root(p: str) -> bool:
    """Is *p* itself a symlink/junction? Then only the link is removed."""
    try:
        st = os.lstat(p)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    if WINDOWS:
        attrs = getattr(st, "st_file_attributes", 0)
        return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    return False


def rm_path(path: str, *, dry_run: bool = False) -> RmResult:
    """Delete *path* (file, link or whole tree). Never follows links."""
    result = RmResult(path=os.path.abspath(path), dry_run=dry_run)

    plain = os.path.abspath(path)
    if os.path.dirname(plain) == plain:
        result.errors.append((plain, "refusing to delete a filesystem root"))
        return result

    real = ext_path(path)

    try:
        st = os.lstat(real)
    except OSError as exc:
        result.errors.append((result.path, str(exc)))
        return result

    is_dir = stat.S_ISDIR(st.st_mode)

    # A symlink/junction root - remove the link itself, never the target.
    if _is_reparse_root(real):
        if dry_run:
            result.dirs_removed = 1 if is_dir else 0
            result.files_removed = 0 if is_dir else 1
            result.ok = True
            return result
        ok = _rmdir(real, result) if is_dir else _unlink(real, result)
        if is_dir:
            result.dirs_removed += 1 if ok else 0
        else:
            result.files_removed += 1 if ok else 0
        result.ok = ok
        return result

    if not is_dir:
        if dry_run:
            result.files_removed = 1
            result.ok = True
            return result
        ok = _unlink(real, result)
        result.files_removed += 1 if ok else 0
        result.ok = ok
        return result

    # Regular directory tree: collect top-down, delete bottom-up.
    collected = list(safe_walk(real))
    for wd in reversed(collected):
        for name in wd.files:
            p = os.path.join(wd.path, name)
            if dry_run:
                result.files_removed += 1
            elif _unlink(p, result):
                result.files_removed += 1
        for name in wd.noenter:
            p = os.path.join(wd.path, name)
            if dry_run:
                result.dirs_removed += 1
            elif _rmdir(p, result):
                result.dirs_removed += 1
        if dry_run:
            result.dirs_removed += 1
        elif _rmdir(wd.path, result):
            result.dirs_removed += 1

    result.ok = not result.errors and (dry_run or not os.path.lexists(real))
    return result
