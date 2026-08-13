"""Tests for rm_path - the robust deleter. Safety first: links are never followed."""
from __future__ import annotations

import os
import stat
import subprocess

import pytest

from longpath.core import ext_path
from longpath.rm import rm_path

from conftest import WINDOWS, make_long_tree, mkfile


def test_delete_simple_tree(tmp_path):
    root = tmp_path / "t"
    mkfile(str(root / "a.txt"))
    mkfile(str(root / "sub" / "b.txt"))
    result = rm_path(str(root))
    assert result.ok, result.errors
    assert not root.exists()
    assert result.files_removed == 2
    assert result.dirs_removed == 2  # sub + root


def test_delete_single_file(tmp_path):
    f = mkfile(str(tmp_path / "one.txt"))
    result = rm_path(f)
    assert result.ok
    assert result.files_removed == 1
    assert result.dirs_removed == 0
    assert not os.path.exists(f)


def test_delete_readonly_file(tmp_path):
    root = tmp_path / "t"
    f = mkfile(str(root / "locked.txt"))
    os.chmod(f, stat.S_IREAD)
    result = rm_path(str(root))
    assert result.ok, result.errors
    assert not root.exists()


def test_delete_long_path_tree(tmp_path):
    root = tmp_path / "deep"
    root.mkdir()
    make_long_tree(str(root), target_len=320)
    result = rm_path(str(root))
    assert result.ok, result.errors
    assert not root.exists()
    assert result.files_removed == 1
    assert result.dirs_removed > 3


def test_dry_run_deletes_nothing(tmp_path):
    root = tmp_path / "t"
    mkfile(str(root / "a.txt"))
    mkfile(str(root / "sub" / "b.txt"))
    result = rm_path(str(root), dry_run=True)
    assert result.ok
    assert result.dry_run
    assert result.files_removed == 2
    assert result.dirs_removed == 2
    assert root.exists()
    assert (root / "a.txt").exists()


def test_missing_path_reports_error(tmp_path):
    result = rm_path(str(tmp_path / "ghost"))
    assert not result.ok
    assert result.errors


def test_refuses_filesystem_root():
    root = "C:\\" if WINDOWS else "/"
    result = rm_path(root)
    assert not result.ok
    assert "refusing" in result.errors[0][1]


@pytest.mark.skipif(WINDOWS, reason="POSIX symlink semantics")
def test_symlink_dir_inside_tree_not_followed(tmp_path):
    target = tmp_path / "precious"
    keep = mkfile(str(target / "keep.txt"))
    root = tmp_path / "doomed"
    root.mkdir()
    os.symlink(str(target), str(root / "link"))
    mkfile(str(root / "x.txt"))

    result = rm_path(str(root))
    assert result.ok, result.errors
    assert not root.exists()
    assert os.path.exists(keep), "symlink target must survive"


@pytest.mark.skipif(WINDOWS, reason="POSIX symlink semantics")
def test_symlink_root_removes_link_only(tmp_path):
    target = tmp_path / "precious"
    keep = mkfile(str(target / "keep.txt"))
    link = tmp_path / "link"
    os.symlink(str(target), str(link))

    result = rm_path(str(link))
    assert result.ok, result.errors
    assert not os.path.lexists(str(link))
    assert os.path.exists(keep)


@pytest.mark.skipif(not WINDOWS, reason="junctions are a Windows feature")
def test_junction_inside_tree_not_followed(tmp_path):
    target = tmp_path / "precious"
    keep = mkfile(str(target / "keep.txt"))
    root = tmp_path / "doomed"
    root.mkdir()
    mkfile(str(root / "x.txt"))
    link = root / "junc"
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    result = rm_path(str(root))
    assert result.ok, result.errors
    assert not root.exists()
    assert os.path.exists(keep), "junction target must survive"


@pytest.mark.skipif(not WINDOWS, reason="junctions are a Windows feature")
def test_junction_root_removes_link_only(tmp_path):
    target = tmp_path / "precious"
    keep = mkfile(str(target / "keep.txt"))
    link = tmp_path / "junc"
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    result = rm_path(str(link))
    assert result.ok, result.errors
    assert not os.path.lexists(str(link))
    assert os.path.exists(keep)


def test_delete_tree_with_unicode_names(tmp_path):
    root = tmp_path / "中文目录😀"
    mkfile(str(root / "期末作业 final.docx"))
    result = rm_path(str(root))
    assert result.ok, result.errors
    assert not root.exists()


def test_deep_nesting(tmp_path):
    root = tmp_path / "deep"
    p = str(root)
    for i in range(60):
        p = os.path.join(p, f"level{i:03d}")
    os.makedirs(ext_path(p))
    mkfile(os.path.join(p, "bottom.txt"))
    result = rm_path(str(root))
    assert result.ok, result.errors
    assert not root.exists()
    assert result.dirs_removed == 61
    assert result.files_removed == 1


def test_to_dict_schema(tmp_path):
    f = mkfile(str(tmp_path / "x.txt"))
    d = rm_path(f).to_dict()
    assert set(d) == {"path", "ok", "dry_run", "files_removed", "dirs_removed", "errors"}
