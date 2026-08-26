"""CWD / parent delete guards — separate from --top / py.typed themes."""

from __future__ import annotations

import os

from longpath.cwdguard import cwd_delete_reason
from longpath.rm import rm_path

from conftest import mkfile, run_cli


def test_cwd_delete_reason_for_dot_and_cwd():
    assert "current working directory" in (cwd_delete_reason(".") or "")
    assert "current working directory" in (cwd_delete_reason(os.getcwd()) or "")


def test_cwd_delete_reason_for_parent():
    reason = cwd_delete_reason("..")
    assert reason is not None
    assert "parent" in reason


def test_rm_path_refuses_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mkfile(str(tmp_path / "keep.txt"))
    result = rm_path(".")
    assert not result.ok
    assert "current working directory" in result.errors[0][1]
    assert (tmp_path / "keep.txt").exists()


def test_rm_path_refuses_parent_of_cwd(tmp_path, monkeypatch):
    child = tmp_path / "child"
    child.mkdir()
    mkfile(str(tmp_path / "keep.txt"))
    monkeypatch.chdir(child)
    result = rm_path("..")
    assert not result.ok
    assert "parent" in result.errors[0][1]
    assert (tmp_path / "keep.txt").exists()


def test_rm_path_still_deletes_sibling(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    doomed = tmp_path / "doomed"
    mkfile(str(doomed / "x.txt"))
    result = rm_path(str(doomed))
    assert result.ok, result.errors
    assert not doomed.exists()


def test_cli_rm_dot_exits_2(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mkfile(str(tmp_path / "keep.txt"))
    p = run_cli("rm", ".", "-y", cwd=str(tmp_path))
    assert p.returncode == 2
    assert "current working directory" in p.stdout + p.stderr
    assert (tmp_path / "keep.txt").exists()
