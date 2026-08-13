"""Command line interface for longpath."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from . import __version__
from .core import (
    ALL_RULES,
    DEFAULT_LIMIT,
    WINDOWS,
    ScanResult,
    check_tree,
    displayable,
    long_paths_enabled,
    scan_tree,
)
from .rm import rm_path

_SUBCOMMANDS = {"scan", "check", "rm"}

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2

_EPILOG = """\
exit codes:
  0  clean (nothing over budget / no issues / deleted successfully)
  1  findings (paths over budget or portability issues exist)
  2  error (bad arguments, unreadable root, deletion failures)

examples:
  longpath scan D:\\projects                 what breaks the 260-char limit?
  longpath scan . --base "C:\\Users\\me\\OneDrive\\Documents"
                                            pre-flight: will copying here break?
  longpath check . --json                   portability lint for this repo (CI-friendly)
  longpath rm D:\\stuck\\node_modules         delete what Explorer/rmdir cannot
"""


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def _enable_vt() -> bool:
    if not WINDOWS:
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


class Palette:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def _wrap(self, s: str, code: str) -> str:
        return f"\x1b[{code}m{s}\x1b[0m" if self.enabled else s

    def bold(self, s: str) -> str:
        return self._wrap(s, "1")

    def red(self, s: str) -> str:
        return self._wrap(s, "31")

    def green(self, s: str) -> str:
        return self._wrap(s, "32")

    def yellow(self, s: str) -> str:
        return self._wrap(s, "33")

    def dim(self, s: str) -> str:
        return self._wrap(s, "2")


def _make_palette(no_color: bool) -> Palette:
    enabled = (
        not no_color
        and os.environ.get("NO_COLOR") is None
        and hasattr(sys.stdout, "isatty")
        and sys.stdout.isatty()
        and _enable_vt()
    )
    return Palette(enabled)


def _print(s: str = "") -> None:
    sys.stdout.write(s + "\n")


def _err(s: str) -> None:
    sys.stderr.write(s + "\n")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="longpath",
        description=(
            "Find, lint and delete paths that break the Windows 260-character "
            "MAX_PATH limit - before OR after they bite."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-V", "--version", action="version", version=f"longpath {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--json", action="store_true", help="machine-readable JSON on stdout")
        p.add_argument("-q", "--quiet", action="store_true", help="no output, exit code only")
        p.add_argument("--no-color", action="store_true", help="disable colored output")

    p_scan = sub.add_parser(
        "scan",
        help="measure every path against a length budget (default: MAX_PATH 260)",
        description="Measure every path under DIR against a length budget.",
    )
    p_scan.add_argument("dir", nargs="?", default=".", help="directory (or file) to scan, default: .")
    p_scan.add_argument("--limit", type=int, default=DEFAULT_LIMIT, metavar="N",
                        help="path length limit to test against (default: 260 = MAX_PATH)")
    p_scan.add_argument("--base", metavar="DEST",
                        help="simulate copying DIR into DEST and measure the resulting paths "
                             "(pre-flight for 'Destination Path Too Long', OneDrive, zip extraction)")
    p_scan.add_argument("--top", type=int, default=20, metavar="N",
                        help="show at most N offending paths (default: 20)")
    p_scan.add_argument("--all", action="store_true", help="show every offending path")
    common(p_scan)

    p_check = sub.add_parser(
        "check",
        help="portability lint: reserved names, illegal chars, case clashes, over-long paths",
        description=(
            "Lint a tree for names that break Windows/macOS or cross-platform git. "
            "Rules: " + ", ".join(ALL_RULES)
        ),
    )
    p_check.add_argument("dir", nargs="?", default=".", help="directory to check, default: .")
    p_check.add_argument("--limit", type=int, default=DEFAULT_LIMIT, metavar="N",
                         help="path length limit for the too-long rule (default: 260)")
    p_check.add_argument("--base", metavar="DEST",
                         help="apply the too-long rule as if the tree were copied into DEST")
    p_check.add_argument("--ignore", metavar="RULES", default="",
                         help="comma-separated rules to skip (e.g. too-long,case-collision)")
    common(p_check)

    p_rm = sub.add_parser(
        "rm",
        help="delete files/trees that Explorer, del and rmdir refuse to delete",
        description=(
            "Robust delete: handles paths beyond 260 chars, clears read-only "
            "attributes, and never follows symlinks or junctions (only the link "
            "itself is removed)."
        ),
    )
    p_rm.add_argument("paths", nargs="+", metavar="PATH", help="files or directories to delete")
    p_rm.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    p_rm.add_argument("-n", "--dry-run", action="store_true",
                      help="only report what would be deleted")
    common(p_rm)

    return parser


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------

def _policy_lines(pal: Palette) -> List[str]:
    state = long_paths_enabled()
    if state is None:
        return []
    if state:
        return [
            pal.dim("Windows long-path policy: ENABLED "
                    "(manifest-aware apps may exceed 260; Explorer still cannot)"),
        ]
    return [
        "Windows long-path policy: " + pal.yellow("DISABLED")
        + " - Explorer, cmd and most apps stop at 260 chars",
        pal.dim('  enable (admin): reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem" '
                "/v LongPathsEnabled /t REG_DWORD /d 1 /f"),
    ]


def _run_scan(args: argparse.Namespace) -> int:
    if not os.path.exists(args.dir):
        _err(f"longpath: path does not exist: {args.dir}")
        return EXIT_ERROR
    if args.limit < 16:
        _err("longpath: --limit must be at least 16")
        return EXIT_ERROR

    result = scan_tree(args.dir, limit=args.limit, base=args.base)
    findings = len(result.over) > 0

    if args.json:
        _print(json.dumps(result.to_dict(), indent=2, ensure_ascii=True))
        return EXIT_FINDINGS if findings else EXIT_CLEAN
    if args.quiet:
        return EXIT_FINDINGS if findings else EXIT_CLEAN

    pal = _make_palette(args.no_color)
    total = result.total_files + result.total_dirs
    _print(pal.bold(f"longpath scan  {displayable(result.root)}"))
    budget_note = f"budget: {result.budget} usable chars (limit {result.limit})"
    if args.base:
        budget_note += f"   simulating copy into: {args.base}"
    _print("  " + budget_note)
    scanned = f"  scanned: {result.total_files:,} files, {result.total_dirs:,} dirs"
    if result.errors:
        scanned += pal.yellow(f"  ({result.errors} unreadable, skipped)")
    _print(scanned + f"   deepest nesting: {result.max_depth}")
    if result.longest is not None:
        _print(f"  longest: {result.longest.length} chars  "
               + pal.dim(displayable(result.longest.path)))
    _print()

    if not findings:
        _print(pal.green(f"OK - nothing exceeds {result.budget} chars ({total:,} paths checked)"))
        for line in _policy_lines(pal):
            _print(line)
        return EXIT_CLEAN

    worst = result.over[0]
    _print(pal.red(pal.bold(
        f"{len(result.over):,} paths exceed the budget (worst is {worst.over} chars over):")))
    shown = result.over if args.all else result.over[: max(args.top, 0)]
    for o in shown:
        marker = "DIR " if o.is_dir else "    "
        _print(f"  +{o.over:<4} {o.length:>4}  {marker}{displayable(o.path)}")
    hidden = len(result.over) - len(shown)
    if hidden > 0:
        _print(pal.dim(f"  ... and {hidden:,} more (use --all, or --json for everything)"))
    _print()
    for line in _policy_lines(pal):
        _print(line)
    _print(pal.dim("hints: fix by shortening the deepest folders; delete stuck trees with "
                   "'longpath rm <path>'; preview a copy with '--base DEST'"))
    return EXIT_FINDINGS


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

def _run_check(args: argparse.Namespace) -> int:
    if not os.path.exists(args.dir):
        _err(f"longpath: path does not exist: {args.dir}")
        return EXIT_ERROR

    ignore = {r.strip() for r in args.ignore.split(",") if r.strip()}
    unknown = ignore - set(ALL_RULES)
    if unknown:
        _err(f"longpath: unknown rule(s) in --ignore: {', '.join(sorted(unknown))}")
        _err(f"          known rules: {', '.join(ALL_RULES)}")
        return EXIT_ERROR

    issues, scan = check_tree(args.dir, limit=args.limit, base=args.base, ignore=ignore)

    if args.json:
        payload = {
            "root": displayable(scan.root),
            "limit": scan.limit,
            "base": scan.base,
            "total_files": scan.total_files,
            "total_dirs": scan.total_dirs,
            "issue_count": len(issues),
            "issues": [i.to_dict() for i in issues],
        }
        _print(json.dumps(payload, indent=2, ensure_ascii=True))
        return EXIT_FINDINGS if issues else EXIT_CLEAN
    if args.quiet:
        return EXIT_FINDINGS if issues else EXIT_CLEAN

    pal = _make_palette(args.no_color)
    total = scan.total_files + scan.total_dirs
    _print(pal.bold(f"longpath check  {displayable(scan.root)}"))
    if not issues:
        _print(pal.green(f"OK - {total:,} paths, no portability issues found"))
        return EXIT_CLEAN

    by_rule: dict = {}
    for issue in issues:
        by_rule.setdefault(issue.rule, []).append(issue)

    _print(pal.red(pal.bold(f"{len(issues)} issue(s) in {total:,} paths")))
    for rule in ALL_RULES:
        group = by_rule.get(rule)
        if not group:
            continue
        _print()
        _print(pal.yellow(pal.bold(f"[{rule}] ({len(group)})")))
        for issue in group:
            _print(f"  {displayable(issue.path)}")
            _print(pal.dim(f"      {issue.message}"))
    _print()
    _print(pal.dim("suppress a rule with --ignore RULE; machine output with --json"))
    return EXIT_FINDINGS


# ---------------------------------------------------------------------------
# rm
# ---------------------------------------------------------------------------

def _confirm(prompt: str) -> bool:
    try:
        answer = input(prompt)
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() in ("y", "yes")


def _run_rm(args: argparse.Namespace) -> int:
    missing = [p for p in args.paths if not os.path.lexists(p)]
    if missing:
        for p in missing:
            _err(f"longpath: path does not exist: {p}")
        return EXIT_ERROR

    if not args.dry_run and not args.yes:
        if args.json:
            _err("longpath: rm --json needs -y/--yes (or -n/--dry-run); it cannot prompt")
            return EXIT_ERROR
        if not sys.stdin.isatty():
            _err("longpath: refusing to delete without -y/--yes when not running interactively")
            return EXIT_ERROR
        targets = ", ".join(args.paths)
        if not _confirm(f"Delete {targets}? This cannot be undone. [y/N] "):
            _err("longpath: aborted, nothing deleted")
            return EXIT_ERROR

    results = [rm_path(p, dry_run=args.dry_run) for p in args.paths]
    all_ok = all(r.ok for r in results)

    if args.json:
        _print(json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=True))
        return EXIT_CLEAN if all_ok else EXIT_ERROR
    if args.quiet:
        return EXIT_CLEAN if all_ok else EXIT_ERROR

    pal = _make_palette(args.no_color)
    verb = "would delete" if args.dry_run else "deleted"
    for r in results:
        if r.ok:
            _print(pal.green(f"{verb}: {displayable(r.path)}  "
                             f"({r.files_removed:,} files, {r.dirs_removed:,} dirs)"))
        else:
            _print(pal.red(f"FAILED: {displayable(r.path)}  "
                           f"({r.files_removed:,} files, {r.dirs_removed:,} dirs removed before failing)"))
            for path, error in r.errors[:10]:
                _print(pal.dim(f"    {displayable(path)}: {error}"))
            if len(r.errors) > 10:
                _print(pal.dim(f"    ... and {len(r.errors) - 10} more errors"))
    return EXIT_CLEAN if all_ok else EXIT_ERROR


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, OSError):
            pass

    # sugar: `longpath D:\dir` == `longpath scan D:\dir`; bare `longpath` scans .
    if not argv:
        argv = ["scan"]
    elif argv[0] not in _SUBCOMMANDS and not argv[0].startswith("-"):
        argv = ["scan"] + argv

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "scan":
            return _run_scan(args)
        if args.command == "check":
            return _run_check(args)
        return _run_rm(args)
    except KeyboardInterrupt:
        _err("longpath: interrupted")
        return 130
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except OSError:
            pass
        return EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
