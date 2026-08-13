"""End-to-end user journey: a messy real tree goes through the whole toolkit.

scan finds the damage -> why explains it -> check lints it -> rm --dry-run
previews -> rm --yes cleans up -> scan confirms clean.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess

from longpath.core import ext_path

from conftest import WINDOWS, make_long_tree, mkfile, run_cli


def _build_messy_tree(tmp_path):
    root = tmp_path / "messy"
    root.mkdir()
    # normal content
    mkfile(str(root / "docs" / "readme.txt"))
    # a >260-char branch
    make_long_tree(str(root / "deep"), target_len=320)
    # a read-only file
    locked = mkfile(str(root / "locked" / "readonly.dat"))
    os.chmod(locked, stat.S_IREAD)
    # unicode + emoji names
    mkfile(str(root / "课程资料😀" / "期末作业.docx"))
    if WINDOWS:
        # cursed names dropped by git/WSL/7-zip
        for cursed in ("aux.log", "report."):
            with open(ext_path(str(root / "docs" / cursed)), "w") as fh:
                fh.write("x")
        # a junction pointing INTO precious data
        precious = tmp_path / "precious"
        mkfile(str(precious / "keep.me"))
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(root / "junc"), str(precious)],
            capture_output=True,
        )
    return root


def test_full_user_journey(tmp_path):
    root = _build_messy_tree(tmp_path)

    # 1. scan: finds the long branch
    p = run_cli("scan", str(root), "--json")
    assert p.returncode == 1
    scan = json.loads(p.stdout)
    assert scan["over_count"] >= 1
    worst = scan["over"][0]["path"]
    assert scan["over"][0]["over"] > 0

    # 2. why: explains the worst offender (path exists, but that's not required)
    p = run_cli("why", worst, "--json")
    assert p.returncode == 1
    why = json.loads(p.stdout)
    assert why["within_budget"] is False
    assert any(c["crosses_budget"] for c in why["components"])
    assert why["suggestions"], "should suggest what to rename"

    # 3. check: lints everything (cursed names flagged on Windows)
    p = run_cli("check", str(root), "--json")
    assert p.returncode == 1
    check = json.loads(p.stdout)
    rules = {i["rule"] for i in check["issues"]}
    assert "too-long" in rules
    if WINDOWS:
        assert "reserved-name" in rules
        assert "trailing-dot-space" in rules

    # 4. rm --dry-run: previews, deletes nothing
    p = run_cli("rm", str(root), "--dry-run", "--json")
    assert p.returncode == 0
    preview = json.loads(p.stdout)[0]
    assert preview["dry_run"] is True
    assert preview["files_removed"] >= 4
    assert root.exists()

    # 5. rm --yes: the whole mess disappears, junction target survives
    p = run_cli("rm", str(root), "--yes", "--json")
    assert p.returncode == 0, p.stdout
    outcome = json.loads(p.stdout)[0]
    assert outcome["ok"] is True
    assert not root.exists()
    if WINDOWS:
        assert (tmp_path / "precious" / "keep.me").exists(), \
            "junction target must survive the deletion"

    # 6. the parent is clean now
    p = run_cli("scan", str(tmp_path))
    assert p.returncode == 0
