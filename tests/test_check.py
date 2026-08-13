"""Tests for check_tree - the portability linter."""
from __future__ import annotations

import os

import pytest

from longpath.core import (
    ALL_RULES,
    RULE_CASE_COLLISION,
    RULE_ILLEGAL_CHAR,
    RULE_NORM_COLLISION,
    RULE_RESERVED,
    RULE_TOO_LONG,
    RULE_TRAILING,
    RULE_UNDECODABLE,
    check_tree,
    wchar_len,
)

from conftest import LINUX, MACOS, WINDOWS, mkfile


def _rules(issues):
    return {i.rule for i in issues}


def test_clean_tree_has_no_issues(tree):
    issues, stats = check_tree(str(tree))
    assert issues == []
    assert stats.total_files == 3


def test_too_long_rule_uses_limit(tree):
    limit = wchar_len(str(tree)) + 8
    issues, _ = check_tree(str(tree), limit=limit)
    assert RULE_TOO_LONG in _rules(issues)
    for i in issues:
        if i.rule == RULE_TOO_LONG:
            assert "over the" in i.message


def test_ignore_silences_rule(tree):
    limit = wchar_len(str(tree)) + 8
    issues, _ = check_tree(str(tree), limit=limit, ignore={RULE_TOO_LONG})
    assert RULE_TOO_LONG not in _rules(issues)


@pytest.mark.skipif(WINDOWS, reason="Windows cannot create these names at all")
def test_windows_breaking_names_detected_on_posix(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    mkfile(str(root / "CON"))              # reserved
    mkfile(str(root / "notes:v2.txt"))     # illegal colon
    mkfile(str(root / "back\\slash.txt"))  # backslash breaks Windows
    mkfile(str(root / "draft. "))          # trailing dot/space
    mkfile(str(root / "ok.txt"))
    issues, _ = check_tree(str(root))
    rules = _rules(issues)
    assert RULE_RESERVED in rules
    assert RULE_ILLEGAL_CHAR in rules
    assert RULE_TRAILING in rules
    # each issue carries the offending path
    paths = {i.path for i in issues}
    assert any(p.endswith("CON") for p in paths)
    # both the colon file and the backslash file are illegal-char issues
    assert sum(1 for i in issues if i.rule == RULE_ILLEGAL_CHAR) == 2


@pytest.mark.skipif(not WINDOWS, reason="creates cursed names via \\\\?\\ on Windows")
def test_cursed_names_created_via_ext_path_detected_on_windows(tmp_path):
    """git/WSL/7-zip can drop 'con' or 'file.' onto NTFS; check must see them."""
    from longpath.core import ext_path

    root = tmp_path / "repo"
    root.mkdir()
    for cursed in ("con", "trailing."):
        with open(ext_path(str(root / cursed)), "w") as fh:
            fh.write("x")
    issues, _ = check_tree(str(root))
    rules = _rules(issues)
    assert RULE_RESERVED in rules
    assert RULE_TRAILING in rules


@pytest.mark.skipif(
    WINDOWS or MACOS,
    reason="needs a case-sensitive filesystem to create both names")
def test_case_collision_detected_in_real_tree(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    mkfile(str(root / "Makefile"))
    mkfile(str(root / "makefile"))
    issues, _ = check_tree(str(root))
    case_issues = [i for i in issues if i.rule == RULE_CASE_COLLISION]
    assert len(case_issues) == 1
    assert "Makefile" in case_issues[0].message
    assert case_issues[0].path == str(root)


@pytest.mark.skipif(
    WINDOWS or MACOS,
    reason="needs a normalization-sensitive filesystem")
def test_unicode_collision_detected_in_real_tree(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    mkfile(str(root / "caf\u00e9.txt"))
    mkfile(str(root / "cafe\u0301.txt"))
    issues, _ = check_tree(str(root))
    assert RULE_NORM_COLLISION in _rules(issues)


@pytest.mark.skipif(not LINUX, reason="only Linux lets raw bytes through")
def test_undecodable_name_detected_in_real_tree(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    os.mkdir(os.path.join(str(root).encode(), b"b\xffad"))
    issues, _ = check_tree(str(root))
    assert RULE_UNDECODABLE in _rules(issues)


def test_check_single_file(tmp_path):
    f = mkfile(str(tmp_path / "report.txt"))
    issues, _ = check_tree(f)
    assert issues == []


@pytest.mark.skipif(WINDOWS, reason="cannot create a reserved name on Windows")
def test_check_single_bad_file(tmp_path):
    f = mkfile(str(tmp_path / "NUL.json"))
    issues, _ = check_tree(f)
    assert RULE_RESERVED in _rules(issues)


def test_all_rules_constant_matches_emittable_rules():
    assert len(ALL_RULES) == 8
    assert len(set(ALL_RULES)) == 8


def test_issue_to_dict(tree):
    limit = wchar_len(str(tree)) + 8
    issues, _ = check_tree(str(tree), limit=limit)
    d = issues[0].to_dict()
    assert set(d) == {"rule", "path", "message"}
