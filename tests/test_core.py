"""Unit tests for pure logic: length math, name rules, collisions, helpers."""
from __future__ import annotations

import os

import pytest

from longpath.core import (
    RULE_CASE_COLLISION,
    RULE_COMPONENT_LONG,
    RULE_ILLEGAL_CHAR,
    RULE_NORM_COLLISION,
    RULE_RESERVED,
    RULE_TRAILING,
    RULE_UNDECODABLE,
    base_style_sep,
    check_name,
    check_sibling_names,
    displayable,
    ext_path,
    simulate_dest,
    unext,
    utf8_len,
    wchar_len,
)

from conftest import WINDOWS


# ---------------------------------------------------------------------------
# length math
# ---------------------------------------------------------------------------

def test_wchar_len_ascii():
    assert wchar_len("C:\\Users\\yu") == 11


def test_wchar_len_cjk_is_one_unit_each():
    assert wchar_len("课程表") == 3


def test_wchar_len_emoji_is_two_units():
    # one code point, but two UTF-16 units - both count against MAX_PATH
    assert wchar_len("😀") == 2
    assert wchar_len("a😀b") == 4


def test_wchar_len_survives_lone_surrogates():
    assert wchar_len("\udcff") == 1


def test_utf8_len_cjk():
    assert utf8_len("课") == 3
    assert utf8_len("abc") == 3


# ---------------------------------------------------------------------------
# extended-length helpers
# ---------------------------------------------------------------------------

def test_unext_strips_prefix():
    assert unext("\\\\?\\C:\\x\\y") == "C:\\x\\y"
    assert unext("\\\\?\\UNC\\server\\share\\f") == "\\\\server\\share\\f"
    assert unext("C:\\plain") == "C:\\plain"
    assert unext("/posix/path") == "/posix/path"


@pytest.mark.skipif(not WINDOWS, reason="Windows path semantics")
def test_ext_path_windows_drive():
    assert ext_path("C:\\x\\y") == "\\\\?\\C:\\x\\y"
    # idempotent
    assert ext_path("\\\\?\\C:\\x\\y") == "\\\\?\\C:\\x\\y"


@pytest.mark.skipif(not WINDOWS, reason="Windows path semantics")
def test_ext_path_windows_unc():
    assert ext_path("\\\\server\\share\\f") == "\\\\?\\UNC\\server\\share\\f"


@pytest.mark.skipif(WINDOWS, reason="POSIX passthrough")
def test_ext_path_posix_is_abspath():
    assert ext_path("/a/b") == "/a/b"
    assert os.path.isabs(ext_path("rel"))


def test_ext_path_roundtrip(tmp_path):
    p = str(tmp_path / "x")
    assert unext(ext_path(p)) == os.path.abspath(p)


# ---------------------------------------------------------------------------
# destination simulation
# ---------------------------------------------------------------------------

def test_base_style_sep_windows_styles():
    assert base_style_sep("C:\\Users\\me") == "\\"
    assert base_style_sep("C:/Users/me") == "\\"       # drive letter wins
    assert base_style_sep("\\\\server\\share") == "\\"


def test_base_style_sep_posix():
    assert base_style_sep("/mnt/backup") == "/"


def test_simulate_dest_windows_base_on_any_os():
    out = simulate_dest("C:\\Users\\me\\OneDrive\\", ("proj", "sub", "a.txt"))
    assert out == "C:\\Users\\me\\OneDrive\\proj\\sub\\a.txt"


def test_simulate_dest_posix_base():
    out = simulate_dest("/mnt/nas", ("proj", "a.txt"))
    assert out == "/mnt/nas/proj/a.txt"


# ---------------------------------------------------------------------------
# check_name
# ---------------------------------------------------------------------------

def _rules(name):
    return {rule for rule, _ in check_name(name)}


@pytest.mark.parametrize("name", [
    "CON", "con", "Con.txt", "NUL.tar.gz", "PRN", "AUX.log",
    "COM1", "com9.dat", "LPT1", "lpt5.bak", "COM\u00b9",
    "AUX .txt",  # Windows strips trailing spaces from the stem
])
def test_reserved_names_flagged(name):
    assert RULE_RESERVED in _rules(name)


@pytest.mark.parametrize("name", [
    "COM0", "LPT0", "COM10", "CONS", "CONTENT.txt", "console.py", "aux2.js", "nульб",
])
def test_non_reserved_names_pass(name):
    assert RULE_RESERVED not in _rules(name)


@pytest.mark.parametrize("name,bad", [
    ("a:b.txt", ":"),
    ("what?.md", "?"),
    ("star*.log", "*"),
    ('quote".txt', '"'),
    ("pipe|.txt", "|"),
    ("lt<gt>.txt", "<"),
    ("bell\x07.txt", "\\x07"),
])
def test_illegal_chars_flagged(name, bad):
    problems = dict(check_name(name))
    assert RULE_ILLEGAL_CHAR in problems
    assert bad in problems[RULE_ILLEGAL_CHAR]


def test_normal_names_have_no_illegal_chars():
    assert RULE_ILLEGAL_CHAR not in _rules("perfectly_fine-name (1).txt")
    assert RULE_ILLEGAL_CHAR not in _rules("中文名字.pdf")


@pytest.mark.parametrize("name", ["ends.", "ends ", "both. ", "dir."])
def test_trailing_dot_or_space_flagged(name):
    assert RULE_TRAILING in _rules(name)


def test_inner_dots_and_spaces_ok():
    assert RULE_TRAILING not in _rules("v1.2.3 final.txt")


def test_component_too_long_utf16():
    assert RULE_COMPONENT_LONG in _rules("a" * 256)
    assert RULE_COMPONENT_LONG not in _rules("a" * 255)


def test_component_too_long_utf8_bytes():
    # 100 CJK chars: 100 UTF-16 units (fine) but 300 UTF-8 bytes (breaks ext4)
    assert RULE_COMPONENT_LONG in _rules("课" * 100)
    assert RULE_COMPONENT_LONG not in _rules("课" * 85)  # 255 bytes exactly


def test_undecodable_name_flagged():
    assert RULE_UNDECODABLE in _rules("caf\udce9.txt")


def test_clean_name_is_clean():
    assert check_name("README.md") == []


# ---------------------------------------------------------------------------
# sibling collisions
# ---------------------------------------------------------------------------

def _sib_rules(names):
    return [rule for rule, _ in check_sibling_names(names)]


def test_case_collision_detected():
    rules = _sib_rules(["readme.md", "README.md", "other.txt"])
    assert rules == [RULE_CASE_COLLISION]


def test_case_collision_three_way_is_one_issue():
    rules = _sib_rules(["a.txt", "A.txt", "A.TXT"])
    assert rules == [RULE_CASE_COLLISION]


def test_no_collision_for_distinct_names():
    assert _sib_rules(["a.txt", "b.txt", "ab.txt"]) == []


def test_unicode_normalization_collision():
    nfc = "caf\u00e9.txt"          # é precomposed
    nfd = "cafe\u0301.txt"         # e + combining acute
    assert nfc != nfd
    rules = _sib_rules([nfc, nfd])
    assert rules == [RULE_NORM_COLLISION]


def test_mixed_case_and_normalization_reports_case_rule():
    nfc_upper = "CAF\u00c9.txt"
    nfd_lower = "cafe\u0301.txt"
    rules = _sib_rules([nfc_upper, nfd_lower])
    assert rules == [RULE_CASE_COLLISION]


def test_collision_key_survives_surrogates():
    assert _sib_rules(["a\udcff", "b\udcff"]) == []


# ---------------------------------------------------------------------------
# displayable
# ---------------------------------------------------------------------------

def test_displayable_passthrough():
    assert displayable("普通/path.txt") == "普通/path.txt"


def test_displayable_replaces_surrogates():
    out = displayable("bad\udcffname")
    assert "\udcff" not in out
    assert "bad" in out and "name" in out
