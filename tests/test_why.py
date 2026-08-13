"""Tests for `longpath why` - component-level budget breakdown."""
from __future__ import annotations

import json

from longpath.why import why_path

from conftest import WINDOWS, run_cli


# ---------------------------------------------------------------------------
# splitting & math (pure string work, identical on every OS)
# ---------------------------------------------------------------------------

def test_windows_drive_math():
    r = why_path("C:\\ab\\cd.txt", limit=260)
    names = [c.name for c in r.components]
    assert names == ["C:\\", "ab", "cd.txt"]
    assert [c.cum for c in r.components] == [3, 5, 12]
    assert r.length == 12
    assert r.style == "windows"
    assert r.over < 0 or r.over <= 0


def test_windows_path_analysed_on_any_os():
    r = why_path("C:\\Users\\me\\OneDrive\\Documents\\project\\file.txt")
    assert r.style == "windows"
    assert r.length == len("C:\\Users\\me\\OneDrive\\Documents\\project\\file.txt")


def test_unc_root():
    r = why_path("\\\\server\\share\\dir\\f.txt")
    assert r.components[0].name == "\\\\server\\share\\"
    assert r.components[0].cum == 15   # \\ + server + \ + share + \
    assert r.components[1].name == "dir"
    assert r.components[1].cum == 18
    assert r.length == len("\\\\server\\share\\dir\\f.txt") == 24


def test_posix_math():
    r = why_path("/usr/local/bin/tool")
    names = [c.name for c in r.components]
    assert names == ["/", "usr", "local", "bin", "tool"]
    assert [c.cum for c in r.components] == [1, 4, 10, 14, 19]
    assert r.style == "posix"


def test_forward_slash_windows_style():
    r = why_path("C:/Users/me/file.txt")
    assert r.style == "windows"
    assert r.components[0].name == "C:\\"
    assert r.length == len("C:\\Users\\me\\file.txt")


def test_crossing_marker_set_once():
    long_mid = "x" * 300
    r = why_path(f"C:\\{long_mid}\\end.txt", limit=260)
    crossing = [c for c in r.components if c.crosses]
    assert len(crossing) == 1
    assert crossing[0].name == long_mid
    assert r.over > 0


def test_under_budget_has_no_crossing():
    r = why_path("C:\\short.txt", limit=260)
    assert all(not c.crosses for c in r.components)


def test_suggestions_sorted_by_savings():
    r = why_path("C:\\tiny\\medium-name\\the-really-long-component\\f.txt")
    saves = [s["saves_up_to"] for s in r.suggestions]
    assert saves == sorted(saves, reverse=True)
    assert r.suggestions[0]["component"] == "the-really-long-component"


def test_emoji_counts_two_units():
    r = why_path("C:\\😀.txt")
    comp = r.components[1]
    assert comp.name == "😀.txt"
    assert comp.length == 6  # 2 (emoji) + 4 (".txt")


def test_relative_native_path_made_absolute(tmp_path):
    import os

    old = os.getcwd()
    os.chdir(str(tmp_path))
    try:
        r = why_path("some_file.txt")
        assert r.length > len("some_file.txt")  # absolute now
    finally:
        os.chdir(old)


def test_relative_forward_slash_path_is_native(tmp_path):
    """`longpath why src/deep/file` on Windows must be absolutised too."""
    import os

    old = os.getcwd()
    os.chdir(str(tmp_path))
    try:
        r = why_path("src/deep/file.txt")
        assert r.length > len("src/deep/file.txt")
    finally:
        os.chdir(old)


def test_rooted_posix_path_stays_foreign_on_windows():
    r = why_path("/var/log/app/service.log")
    assert r.style == "posix"
    assert r.length == len("/var/log/app/service.log")


def test_to_dict_schema():
    d = why_path("C:\\a\\b.txt").to_dict()
    assert {"path", "length", "limit", "budget", "over", "within_budget",
            "style", "components", "suggestions"} == set(d)
    assert d["components"][0]["name"] == "C:\\"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_why_over_budget_exit_1():
    p = run_cli("why", "C:\\" + "x" * 300 + "\\end.txt")
    assert p.returncode == 1
    assert "OVER the" in p.stdout
    assert "budget crossed here" in p.stdout


def test_cli_why_within_budget_exit_0():
    p = run_cli("why", "C:\\short\\path.txt")
    assert p.returncode == 0
    assert "fits the" in p.stdout
    assert "biggest wins" in p.stdout


def test_cli_why_json():
    p = run_cli("why", "C:\\deep\\" + "y" * 280 + "\\f.txt", "--json")
    assert p.returncode == 1
    data = json.loads(p.stdout)
    assert data["within_budget"] is False
    assert data["over"] > 0
    assert any(c["crosses_budget"] for c in data["components"])


def test_cli_why_nonexistent_path_is_fine():
    p = run_cli("why", "C:\\this\\does\\not\\exist\\anywhere.txt")
    assert p.returncode == 0


def test_cli_why_custom_limit():
    p = run_cli("why", "C:\\abcdef\\ghijkl.txt", "--limit", "16")
    assert p.returncode == 1


def test_cli_why_limit_guard():
    p = run_cli("why", "C:\\x", "--limit", "3")
    assert p.returncode == 2
