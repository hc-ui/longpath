"""Core logic: path length math, safe tree walking, scanning and portability checks.

Everything here is pure standard library and works on every platform.
Windows-only behaviour (extended-length ``\\\\?\\`` prefixes, the registry
policy) degrades gracefully elsewhere so the same code paths stay testable
on any OS.
"""
from __future__ import annotations

import fnmatch
import os
import stat
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator, List, Optional, Tuple

WINDOWS = os.name == "nt"

#: MAX_PATH as documented by Microsoft. The value includes the terminating
#: NUL, so the longest *usable* path is 259 characters (UTF-16 code units).
DEFAULT_LIMIT = 260

# Rule identifiers used by `check`.
RULE_TOO_LONG = "too-long"
RULE_RESERVED = "reserved-name"
RULE_ILLEGAL_CHAR = "illegal-char"
RULE_TRAILING = "trailing-dot-space"
RULE_CASE_COLLISION = "case-collision"
RULE_NORM_COLLISION = "unicode-collision"
RULE_COMPONENT_LONG = "component-too-long"
RULE_UNDECODABLE = "undecodable-name"

ALL_RULES = (
    RULE_TOO_LONG,
    RULE_RESERVED,
    RULE_ILLEGAL_CHAR,
    RULE_TRAILING,
    RULE_CASE_COLLISION,
    RULE_NORM_COLLISION,
    RULE_COMPONENT_LONG,
    RULE_UNDECODABLE,
)

# Names that map to DOS devices. Using them as a file/dir name (with or
# without an extension) breaks Explorer, cmd.exe and countless programs.
# Superscript digits are reserved too, per Microsoft's documentation.
_RESERVED_STEMS = (
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"COM{i}" for i in "123456789"}
    | {f"LPT{i}" for i in "123456789"}
    | {"COM\u00b9", "COM\u00b2", "COM\u00b3", "LPT\u00b9", "LPT\u00b2", "LPT\u00b3"}
)

# `\` can occur in POSIX filenames and guarantees breakage on Windows.
_BAD_CHARS = set('<>:"|?*\\')


# ---------------------------------------------------------------------------
# Length math
# ---------------------------------------------------------------------------

def wchar_len(s: str) -> int:
    """Length of *s* in UTF-16 code units - what the Windows API counts.

    ``len()`` counts code points, which under-counts anything outside the
    Basic Multilingual Plane: an emoji is one code point but *two* UTF-16
    units, and both count against MAX_PATH.
    """
    return len(s.encode("utf-16-le", "surrogatepass")) // 2


def utf8_len(s: str) -> int:
    """Length of *s* in UTF-8 bytes - what Linux filesystems count."""
    return len(s.encode("utf-8", "surrogateescape"))


# ---------------------------------------------------------------------------
# Extended-length path helpers
# ---------------------------------------------------------------------------

def ext_path(p: str) -> str:
    """Absolute form of *p* that survives the 260-char limit on Windows.

    On Windows the returned path carries the ``\\\\?\\`` prefix (or
    ``\\\\?\\UNC\\`` for network paths) so every stdlib call keeps working
    beyond MAX_PATH regardless of the ``LongPathsEnabled`` policy.
    On other platforms it is simply the absolute path.
    """
    if not WINDOWS:
        return os.path.abspath(p)
    if p.startswith("\\\\?\\"):
        return p
    ab = os.path.abspath(p)
    # os.path.abspath goes through GetFullPathNameW, which silently strips
    # trailing dots/spaces from the final component ('trailing.' -> 'trailing').
    # Those names are exactly what this tool must be able to address, so
    # restore the raw final component when it was damaged.
    raw = p.replace("/", "\\").rstrip("\\")
    raw_name = raw.rsplit("\\", 1)[-1] if "\\" in raw else raw
    ab_name = os.path.basename(ab)
    if (
        raw_name not in (".", "..")
        and raw_name != ab_name
        and raw_name.rstrip(". ") == ab_name
    ):
        ab = os.path.join(os.path.dirname(ab), raw_name)
    if ab.startswith("\\\\"):
        return "\\\\?\\UNC\\" + ab[2:]
    return "\\\\?\\" + ab


def unext(p: str) -> str:
    """Strip the extended-length prefix for display."""
    if p.startswith("\\\\?\\UNC\\"):
        return "\\\\" + p[8:]
    if p.startswith("\\\\?\\"):
        return p[4:]
    return p


def displayable(p: str) -> str:
    """Return *p* safe to print/serialise even with undecodable bytes."""
    try:
        p.encode("utf-8")
        return p
    except UnicodeEncodeError:
        return p.encode("utf-8", "backslashreplace").decode("ascii", "replace")


# ---------------------------------------------------------------------------
# Destination simulation (--base)
# ---------------------------------------------------------------------------

def base_style_sep(base: str) -> str:
    """Guess the separator a destination path uses (windows vs posix)."""
    if "\\" in base or (len(base) >= 2 and base[1] == ":"):
        return "\\"
    return "/"


def simulate_dest(base: str, rel_parts: Tuple[str, ...]) -> str:
    """Path that ``<rel_parts>`` would occupy after copying into *base*."""
    sep = base_style_sep(base)
    return base.rstrip("\\/") + sep + sep.join(rel_parts)


# ---------------------------------------------------------------------------
# Safe tree walking
# ---------------------------------------------------------------------------

def _is_reparse_or_link(entry: "os.DirEntry[str]") -> bool:
    """True for anything we must not descend into (symlinks, junctions)."""
    try:
        if entry.is_symlink():
            return True
        if WINDOWS:
            st = entry.stat(follow_symlinks=False)
            return bool(st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return False
    except OSError:
        return True


@dataclass
class WalkedDir:
    """One directory visited by :func:`safe_walk`."""

    path: str                    # real (possibly \\?\-prefixed) path
    subdirs: List[str]           # names we will descend into
    noenter: List[str]           # dir-like names we will NOT descend into
    files: List[str]             # everything else


def compile_exclude(patterns: Optional[Iterable[str]]) -> Optional[Callable[[str], bool]]:
    """Turn glob patterns into a name matcher (case rules follow the OS)."""
    pats = [p for p in (patterns or []) if p]
    if not pats:
        return None

    def match(name: str) -> bool:
        return any(fnmatch.fnmatch(name, p) for p in pats)

    return match


def safe_walk(
    root: str,
    on_error: Optional[Callable[[OSError], None]] = None,
    exclude: Optional[Callable[[str], bool]] = None,
) -> Iterator[WalkedDir]:
    """Top-down walk that never follows symlinks/junctions and never raises.

    *root* should already be :func:`ext_path`-ified by the caller when the
    tree may exceed MAX_PATH. Parents are always yielded before children.
    Entries whose *name* matches *exclude* are invisible to the walk.
    """
    stack = [root]
    while stack:
        d = stack.pop()
        subdirs: List[str] = []
        noenter: List[str] = []
        files: List[str] = []
        try:
            with os.scandir(d) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as exc:
            if on_error is not None:
                on_error(exc)
            continue
        for e in entries:
            if exclude is not None and exclude(e.name):
                continue
            try:
                is_dir = e.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False
            if is_dir:
                if _is_reparse_or_link(e):
                    noenter.append(e.name)
                else:
                    subdirs.append(e.name)
            else:
                files.append(e.name)
        yield WalkedDir(d, subdirs, noenter, files)
        # push in reverse so iteration order matches sorted order
        for name in reversed(subdirs):
            stack.append(os.path.join(d, name))


# ---------------------------------------------------------------------------
# Scan (length audit)
# ---------------------------------------------------------------------------

@dataclass
class OverPath:
    path: str        # display path (destination path when --base is used)
    length: int      # UTF-16 length
    over: int        # how many chars past the budget
    is_dir: bool

    def to_dict(self) -> dict:
        return {
            "path": displayable(self.path),
            "length": self.length,
            "over": self.over,
            "is_dir": self.is_dir,
        }


@dataclass
class ScanResult:
    root: str
    limit: int
    base: Optional[str]
    total_files: int = 0
    total_dirs: int = 0
    errors: int = 0
    over: List[OverPath] = field(default_factory=list)
    longest: Optional[OverPath] = None      # longest path seen, even if OK
    max_depth: int = 0

    @property
    def budget(self) -> int:
        """Longest usable path: MAX_PATH counts the terminating NUL."""
        return self.limit - 1

    def to_dict(self) -> dict:
        return {
            "root": displayable(self.root),
            "limit": self.limit,
            "budget": self.budget,
            "base": self.base,
            "total_files": self.total_files,
            "total_dirs": self.total_dirs,
            "errors": self.errors,
            "max_depth": self.max_depth,
            "over_count": len(self.over),
            "over": [o.to_dict() for o in self.over],
            "longest": self.longest.to_dict() if self.longest else None,
        }


def _iter_tree_paths(
    root: str,
    on_error: Optional[Callable[[OSError], None]] = None,
    exclude: Optional[Callable[[str], bool]] = None,
) -> Iterator[Tuple[str, Tuple[str, ...], bool]]:
    """Yield ``(real_path, rel_parts, is_dir)`` for root and everything below.

    ``rel_parts`` includes the root's own basename, so destination
    simulation mirrors copying the scanned folder itself into the target.
    """
    real_root = ext_path(root)
    root_name = os.path.basename(os.path.normpath(os.path.abspath(root)))
    if not root_name:  # scanning a drive root like C:\
        root_name = os.path.abspath(root).rstrip("\\/").replace(":", "")
    if not os.path.isdir(real_root) or os.path.islink(root):
        yield real_root, (root_name,), False
        return
    yield real_root, (root_name,), True
    for wd in safe_walk(real_root, on_error=on_error, exclude=exclude):
        rel = os.path.relpath(wd.path, real_root)
        if rel == ".":
            parts: Tuple[str, ...] = (root_name,)
        else:
            parts = (root_name, *rel.split(os.sep))
        for name in wd.files:
            yield os.path.join(wd.path, name), parts + (name,), False
        for name in wd.noenter:
            yield os.path.join(wd.path, name), parts + (name,), True
        for name in wd.subdirs:
            yield os.path.join(wd.path, name), parts + (name,), True


def scan_tree(
    root: str,
    *,
    limit: int = DEFAULT_LIMIT,
    base: Optional[str] = None,
    exclude: Optional[Iterable[str]] = None,
    on_error: Optional[Callable[[OSError], None]] = None,
) -> ScanResult:
    """Measure every path under *root* against a MAX_PATH-style budget.

    With *base*, lengths are computed as if *root* itself were copied into
    that destination folder (pre-flight for "Destination Path Too Long",
    OneDrive/SharePoint limits, zip extraction, ...).
    *exclude* takes glob patterns matched against entry names.
    """
    result = ScanResult(root=os.path.abspath(root), limit=limit, base=base)
    matcher = compile_exclude(exclude)

    def track_error(exc: OSError) -> None:
        result.errors += 1
        if on_error is not None:
            on_error(exc)

    for real, rel_parts, is_dir in _iter_tree_paths(root, on_error=track_error,
                                                    exclude=matcher):
        if is_dir:
            result.total_dirs += 1
        else:
            result.total_files += 1
        result.max_depth = max(result.max_depth, len(rel_parts) - 1)
        if base is not None:
            shown = simulate_dest(base, rel_parts)
        else:
            shown = unext(real)
        length = wchar_len(shown)
        entry = OverPath(shown, length, length - result.budget, is_dir)
        if result.longest is None or length > result.longest.length:
            result.longest = entry
        if length > result.budget:
            result.over.append(entry)

    result.over.sort(key=lambda o: (-o.length, o.path))
    return result


# ---------------------------------------------------------------------------
# Check (portability lint)
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    rule: str
    path: str          # display path of the offending entry (or directory)
    message: str

    def to_dict(self) -> dict:
        return {"rule": self.rule, "path": displayable(self.path), "message": self.message}


def _printable_char(c: str) -> str:
    if ord(c) < 32:
        return f"\\x{ord(c):02x}"
    return c


def check_name(name: str) -> List[Tuple[str, str]]:
    """Portability problems of a single file/dir *name* (no path).

    Returns ``(rule, message)`` tuples. Pure function - unit-testable with
    names that cannot even exist on the current filesystem.
    """
    problems: List[Tuple[str, str]] = []

    stem = name.split(".", 1)[0].rstrip(" ")
    if stem.upper() in _RESERVED_STEMS:
        problems.append((
            RULE_RESERVED,
            f"'{displayable(name)}' is a reserved DOS device name on Windows "
            f"({stem.upper()}); Windows cannot create it and git clone fails with 'invalid path'",
        ))

    bad = sorted({c for c in name if c in _BAD_CHARS or ord(c) < 32})
    if bad:
        chars = " ".join(_printable_char(c) for c in bad)
        problems.append((
            RULE_ILLEGAL_CHAR,
            f"'{displayable(name)}' contains characters illegal on Windows: {chars}",
        ))

    if name != name.rstrip(". "):
        problems.append((
            RULE_TRAILING,
            f"'{displayable(name)}' ends with a dot or space; Windows silently strips "
            f"them, so the file becomes inaccessible or clashes with its sibling",
        ))

    wlen = wchar_len(name)
    blen = utf8_len(name)
    if wlen > 255 or blen > 255:
        detail = f"{wlen} UTF-16 units" if wlen > 255 else f"{blen} UTF-8 bytes"
        problems.append((
            RULE_COMPONENT_LONG,
            f"single name is longer than 255 ({detail}); no mainstream filesystem accepts it",
        ))

    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        problems.append((
            RULE_UNDECODABLE,
            f"'{displayable(name)}' is not valid Unicode (raw bytes leaked from another "
            f"encoding); zip, git and Windows will all choke on it",
        ))

    return problems


def _collision_key(name: str) -> str:
    try:
        return unicodedata.normalize("NFC", name).upper()
    except ValueError:
        return name.upper()


def check_sibling_names(names: List[str]) -> List[Tuple[str, str]]:
    """Collision problems among sibling *names* in one directory.

    Names are grouped by their NFC-normalised, upper-cased form: that is how
    a case-insensitive, normalisation-insensitive filesystem (NTFS defaults,
    APFS/HFS+) sees them. One group -> one issue.
    """
    problems: List[Tuple[str, str]] = []

    groups: dict = {}
    for n in names:
        groups.setdefault(_collision_key(n), []).append(n)

    for group in groups.values():
        if len(group) < 2:
            continue
        listed = ", ".join(f"'{displayable(n)}'" for n in sorted(group))
        try:
            nfc_forms = {unicodedata.normalize("NFC", n) for n in group}
        except ValueError:
            nfc_forms = set(group)
        if len(nfc_forms) == 1:
            problems.append((
                RULE_NORM_COLLISION,
                f"{listed} are the same name in different Unicode normal forms "
                f"(NFC/NFD); macOS treats them as one file and git checkout breaks",
            ))
        else:
            problems.append((
                RULE_CASE_COLLISION,
                f"{listed} differ only by letter case; they collide on the "
                f"case-insensitive filesystems of Windows/macOS and git checkout "
                f"silently overwrites one with the other",
            ))
    return problems


def check_tree(
    root: str,
    *,
    limit: int = DEFAULT_LIMIT,
    base: Optional[str] = None,
    ignore: Optional[set] = None,
    exclude: Optional[Iterable[str]] = None,
    on_error: Optional[Callable[[OSError], None]] = None,
) -> Tuple[List[Issue], ScanResult]:
    """Run every portability rule over the tree. Returns (issues, scan stats)."""
    ignore = ignore or set()
    issues: List[Issue] = []
    matcher = compile_exclude(exclude)

    scan = scan_tree(root, limit=limit, base=base, exclude=exclude, on_error=on_error)
    if RULE_TOO_LONG not in ignore:
        for o in scan.over:
            issues.append(Issue(
                RULE_TOO_LONG,
                o.path,
                f"{o.length} chars, {o.over} over the {scan.budget}-char budget",
            ))

    real_root = ext_path(root)
    if os.path.isdir(real_root) and not os.path.islink(root):
        for wd in safe_walk(real_root, exclude=matcher):
            display_dir = unext(wd.path)
            names = wd.subdirs + wd.noenter + wd.files
            for name in names:
                for rule, message in check_name(name):
                    if rule not in ignore:
                        issues.append(Issue(rule, os.path.join(display_dir, name), message))
            for rule, message in check_sibling_names(names):
                if rule not in ignore:
                    issues.append(Issue(rule, display_dir, message))
    else:
        name = os.path.basename(os.path.normpath(root))
        for rule, message in check_name(name):
            if rule not in ignore:
                issues.append(Issue(rule, os.path.abspath(root), message))

    return issues, scan


# ---------------------------------------------------------------------------
# Windows long-path policy
# ---------------------------------------------------------------------------

def long_paths_enabled() -> Optional[bool]:
    """State of HKLM LongPathsEnabled. None when unknown / not Windows."""
    if not WINDOWS:
        return None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
            return bool(value)
    except OSError:
        return None
