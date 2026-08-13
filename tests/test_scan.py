"""Tests for scan_tree: budgets, simulation, long paths, loops, errors."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from longpath.core import scan_tree, wchar_len

from conftest import WINDOWS, make_long_tree, mkfile


def test_clean_tree_nothing_over(tree):
    result = scan_tree(str(tree))
    assert result.over == []
    assert result.total_files == 3
    assert result.total_dirs == 3  # proj, sub, nested
    assert result.errors == 0
    assert result.longest is not None
    assert result.longest.length >= wchar_len(str(tree))


def test_small_limit_flags_paths(tree):
    limit = wchar_len(str(tree)) + 8
    result = scan_tree(str(tree), limit=limit)
    assert result.over, "expected findings with a tiny budget"
    # sorted by length, worst first
    lengths = [o.length for o in result.over]
    assert lengths == sorted(lengths, reverse=True)
    for o in result.over:
        assert o.over == o.length - (limit - 1)
        assert o.length == wchar_len(o.path)


def test_real_long_path_flagged_with_default_limit(tmp_path):
    deep_file = make_long_tree(str(tmp_path), target_len=320)
    result = scan_tree(str(tmp_path))
    assert result.total_files == 1
    over_paths = [o.path for o in result.over]
    assert any(p.endswith("deep_file.txt") for p in over_paths)
    # display paths never carry the \\?\ prefix
    for p in over_paths:
        assert not p.startswith("\\\\?\\")
    assert result.longest.length >= 320
    assert deep_file.endswith("deep_file.txt")


def test_max_depth_counts_levels(tree):
    result = scan_tree(str(tree))
    # proj -> sub -> nested -> c.txt: file sits 3 levels below the root entry
    assert result.max_depth == 3


def test_base_simulation_windows_style(tree):
    base = "C:\\Users\\student\\OneDrive - University\\Documents\\shared_projects\\semester" \
           "\\group with a long name\\final final version 2\\really final"
    result = scan_tree(str(tree), limit=140, base=base)
    assert result.base == base
    assert result.over, "deep destination should push short paths over 140"
    for o in result.over:
        assert o.path.startswith(base)
        assert "/" not in o.path[2:]  # windows-style joining throughout
        assert o.length == wchar_len(o.path)


def test_base_simulation_includes_root_name(tree):
    result = scan_tree(str(tree), limit=100, base="D:\\dest")
    all_paths = [o.path for o in result.over] + (
        [result.longest.path] if result.longest else [])
    assert any("\\proj\\" in p or p.endswith("\\proj") for p in all_paths)


def test_base_posix_style(tree):
    # deepest simulated path: /mnt/backup/very/deep/dir/proj/sub/nested/c.txt = 47
    result = scan_tree(str(tree), limit=40, base="/mnt/backup/very/deep/dir")
    assert result.over
    assert all(o.path.startswith("/mnt/backup/") for o in result.over)
    assert all("\\" not in o.path for o in result.over)


def test_scan_single_file(tree):
    target = str(tree / "a.txt")
    result = scan_tree(target, limit=1000)
    assert result.total_files == 1
    assert result.total_dirs == 0
    assert result.longest.path.endswith("a.txt")


def test_scan_missing_vs_empty(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = scan_tree(str(empty))
    assert result.total_files == 0
    assert result.total_dirs == 1  # the root itself
    assert result.over == []


@pytest.mark.skipif(not WINDOWS, reason="junctions are a Windows feature")
def test_junction_loop_terminates(tmp_path):
    root = tmp_path / "looproot"
    inner = root / "inner"
    inner.mkdir(parents=True)
    mkfile(str(inner / "f.txt"))
    link = inner / "loop"
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(root)],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    result = scan_tree(str(root), limit=10_000)
    # terminates, and the junction is counted once as a dir, not descended
    assert result.total_dirs >= 3  # root, inner, loop-junction
    assert result.total_files == 1


@pytest.mark.skipif(WINDOWS, reason="POSIX symlinks")
def test_symlink_loop_terminates(tmp_path):
    root = tmp_path / "looproot"
    inner = root / "inner"
    inner.mkdir(parents=True)
    mkfile(str(inner / "f.txt"))
    os.symlink(str(root), str(inner / "loop"))
    result = scan_tree(str(root), limit=10_000)
    assert result.total_files >= 1


@pytest.mark.skipif(
    WINDOWS or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="permission test needs POSIX non-root")
def test_unreadable_dir_counted_as_error(tmp_path):
    root = tmp_path / "r"
    secret = root / "secret"
    secret.mkdir(parents=True)
    mkfile(str(secret / "hidden.txt"))
    mkfile(str(root / "visible.txt"))
    secret.chmod(0)
    try:
        result = scan_tree(str(root))
        assert result.errors == 1
        assert result.total_files == 1  # only visible.txt
    finally:
        secret.chmod(0o755)


def test_unicode_paths_measured_correctly(tmp_path):
    f = mkfile(str(tmp_path / "课程表😀" / "期末大作业.docx"))
    result = scan_tree(str(tmp_path), limit=10_000)
    assert result.total_files == 1
    # the emoji is 1 code point but 2 UTF-16 units, so wchar len = len() + 1
    assert result.longest.length == wchar_len(result.longest.path)
    assert result.longest.length == len(result.longest.path) + 1
    assert f.endswith(".docx")
