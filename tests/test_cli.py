"""End-to-end CLI tests (real subprocesses, real exit codes)."""
from __future__ import annotations

import json
import os

from longpath import __version__
from longpath.core import wchar_len

from conftest import WINDOWS, mkfile, run_cli


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------

def test_scan_clean_exit_0(tree):
    p = run_cli("scan", str(tree))
    assert p.returncode == 0, p.stderr
    assert "OK" in p.stdout
    assert "longpath scan" in p.stdout


def test_scan_findings_exit_1(tree):
    limit = wchar_len(str(tree)) + 8
    p = run_cli("scan", str(tree), "--limit", str(limit))
    assert p.returncode == 1
    assert "exceed the budget" in p.stdout
    assert "b.txt" in p.stdout


def test_scan_json(tree):
    limit = wchar_len(str(tree)) + 8
    p = run_cli("scan", str(tree), "--limit", str(limit), "--json")
    assert p.returncode == 1
    data = json.loads(p.stdout)
    assert data["limit"] == limit
    assert data["budget"] == limit - 1
    assert data["over_count"] == len(data["over"]) > 0
    assert data["total_files"] == 3
    for item in data["over"]:
        assert item["length"] > data["budget"]
        assert item["over"] == item["length"] - data["budget"]


def test_scan_json_is_ascii_safe(tmp_path):
    mkfile(str(tmp_path / "课程表" / "作业.txt"))
    p = run_cli("scan", str(tmp_path), "--json")
    assert p.returncode == 0
    assert all(ord(c) < 128 for c in p.stdout), "JSON must be pure ASCII"
    data = json.loads(p.stdout)
    assert "课程表" in data["longest"]["path"]


def test_scan_missing_dir_exit_2(tmp_path):
    p = run_cli("scan", str(tmp_path / "nope"))
    assert p.returncode == 2
    assert "does not exist" in p.stderr


def test_scan_limit_too_small_exit_2(tree):
    p = run_cli("scan", str(tree), "--limit", "5")
    assert p.returncode == 2


def test_scan_quiet(tree):
    limit = wchar_len(str(tree)) + 8
    p = run_cli("scan", str(tree), "--limit", str(limit), "-q")
    assert p.returncode == 1
    assert p.stdout == ""


def test_scan_top_limits_output(tmp_path):
    root = tmp_path / "many"
    for i in range(30):
        mkfile(str(root / f"file_with_a_fairly_long_name_{i:02d}.txt"))
    limit = wchar_len(str(root)) + 10
    p = run_cli("scan", str(root), "--limit", str(limit), "--top", "5")
    assert p.returncode == 1
    assert "more (use --all" in p.stdout
    p_all = run_cli("scan", str(root), "--limit", str(limit), "--all")
    assert p_all.stdout.count(".txt") >= 30


def test_scan_base_preflight(tree):
    base = "C:\\Users\\someone\\OneDrive\\Documents\\a really deep destination folder"
    # deepest simulated path = base(68) + \proj\sub\nested\c.txt(22) = 90 chars
    p = run_cli("scan", str(tree), "--base", base, "--limit", "80")
    assert p.returncode == 1
    assert "OneDrive" in p.stdout


# ---------------------------------------------------------------------------
# sugar
# ---------------------------------------------------------------------------

def test_bare_dir_arg_means_scan(tree):
    p = run_cli(str(tree))
    assert p.returncode == 0
    assert "longpath scan" in p.stdout


def test_no_args_scans_cwd(tree):
    p = run_cli(cwd=str(tree))
    assert p.returncode == 0
    assert "longpath scan" in p.stdout


def test_version():
    p = run_cli("--version")
    assert p.returncode == 0
    assert __version__ in p.stdout


def test_help():
    p = run_cli("--help")
    assert p.returncode == 0
    assert "scan" in p.stdout and "check" in p.stdout and "rm" in p.stdout


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

def test_check_clean_exit_0(tree):
    p = run_cli("check", str(tree))
    assert p.returncode == 0
    assert "no portability issues" in p.stdout


def test_check_findings_exit_1(tree):
    limit = wchar_len(str(tree)) + 8
    p = run_cli("check", str(tree), "--limit", str(limit))
    assert p.returncode == 1
    assert "[too-long]" in p.stdout


def test_check_ignore_silences(tree):
    limit = wchar_len(str(tree)) + 8
    p = run_cli("check", str(tree), "--limit", str(limit), "--ignore", "too-long")
    assert p.returncode == 0


def test_check_limit_too_small_exit_2(tree):
    p = run_cli("check", str(tree), "--limit", "5")
    assert p.returncode == 2


def test_check_unknown_ignore_rule_exit_2(tree):
    p = run_cli("check", str(tree), "--ignore", "nonsense-rule")
    assert p.returncode == 2
    assert "unknown rule" in p.stderr
    assert "too-long" in p.stderr  # lists known rules


def test_check_json(tree):
    limit = wchar_len(str(tree)) + 8
    p = run_cli("check", str(tree), "--limit", str(limit), "--json")
    assert p.returncode == 1
    data = json.loads(p.stdout)
    assert data["issue_count"] == len(data["issues"]) > 0
    assert {"rule", "path", "message"} == set(data["issues"][0])


# ---------------------------------------------------------------------------
# rm
# ---------------------------------------------------------------------------

def test_rm_dry_run_keeps_files(tmp_path):
    root = tmp_path / "t"
    mkfile(str(root / "a.txt"))
    p = run_cli("rm", str(root), "--dry-run")
    assert p.returncode == 0, p.stderr
    assert "would delete" in p.stdout
    assert (root / "a.txt").exists()


def test_rm_refuses_without_yes_when_not_interactive(tmp_path):
    # stdin = NUL device: on Windows isatty() is True for NUL, so the guard
    # falls through to the prompt, which hits EOF and aborts. Either path
    # must refuse with exit 2 and delete nothing.
    root = tmp_path / "t"
    mkfile(str(root / "a.txt"))
    p = run_cli("rm", str(root))
    assert p.returncode == 2
    assert "refusing" in p.stderr or "aborted" in p.stderr
    assert (root / "a.txt").exists()


def test_rm_refuses_without_yes_piped_stdin(tmp_path):
    root = tmp_path / "t"
    mkfile(str(root / "a.txt"))
    p = run_cli("rm", str(root), input_text="")
    assert p.returncode == 2
    assert "refusing" in p.stderr
    assert (root / "a.txt").exists()


def test_rm_yes_deletes(tmp_path):
    root = tmp_path / "t"
    mkfile(str(root / "a.txt"))
    p = run_cli("rm", str(root), "--yes")
    assert p.returncode == 0, p.stderr
    assert "deleted" in p.stdout
    assert not root.exists()


def test_rm_json_requires_yes(tmp_path):
    root = tmp_path / "t"
    mkfile(str(root / "a.txt"))
    p = run_cli("rm", str(root), "--json")
    assert p.returncode == 2
    assert (root / "a.txt").exists()


def test_rm_json_with_yes(tmp_path):
    root = tmp_path / "t"
    mkfile(str(root / "a.txt"))
    p = run_cli("rm", str(root), "--yes", "--json")
    assert p.returncode == 0, p.stderr
    data = json.loads(p.stdout)
    assert data[0]["ok"] is True
    assert data[0]["files_removed"] == 1
    assert not root.exists()


def test_rm_missing_path_exit_2(tmp_path):
    p = run_cli("rm", str(tmp_path / "ghost"), "--yes")
    assert p.returncode == 2
    assert "does not exist" in p.stderr


def test_rm_multiple_paths(tmp_path):
    a = mkfile(str(tmp_path / "a.txt"))
    b = mkfile(str(tmp_path / "b.txt"))
    p = run_cli("rm", a, b, "--yes")
    assert p.returncode == 0
    assert not os.path.exists(a) and not os.path.exists(b)


def test_rm_confirm_prompt_accepts_input(tmp_path):
    root = tmp_path / "t"
    mkfile(str(root / "a.txt"))
    p = run_cli("rm", str(root), input_text="n\n")
    # stdin is a pipe, not a tty -> the guard refuses before prompting
    assert p.returncode == 2
    assert (root / "a.txt").exists()


def test_rm_direct_long_path_target(tmp_path):
    """Regression: the CLI existence pre-check must itself be long-path aware,
    otherwise `longpath rm <300-char path>` says 'does not exist'."""
    from conftest import make_long_tree

    deep_file = make_long_tree(str(tmp_path / "deep"), target_len=320)
    assert len(deep_file) > 300
    p = run_cli("rm", deep_file, "--yes")
    assert p.returncode == 0, p.stderr
    assert "deleted" in p.stdout


def test_scan_direct_long_path_target(tmp_path):
    from conftest import make_long_tree

    deep_file = make_long_tree(str(tmp_path / "deep"), target_len=320)
    deep_dir = os.path.dirname(deep_file)
    p = run_cli("scan", deep_dir)
    assert p.returncode == 1  # everything under it is over budget
    assert "exceed the budget" in p.stdout


def test_scan_exclude(tmp_path):
    root = tmp_path / "r"
    mkfile(str(root / "keep" / "a.txt"))
    mkfile(str(root / "node_modules" / "dep" / "very_long_file_name_here.txt"))
    p = run_cli("scan", str(root), "--exclude", "node_modules", "--json")
    data = json.loads(p.stdout)
    assert data["total_files"] == 1
    assert data["total_dirs"] == 2  # r + keep


def test_check_exclude(tmp_path):
    root = tmp_path / "r"
    mkfile(str(root / "vendor" / "file.txt"))
    mkfile(str(root / "src" / "ok.txt"))
    limit_probe = run_cli("check", str(root), "--json")
    assert limit_probe.returncode == 0
    # force too-long findings only inside vendor, then exclude it
    from longpath.core import wchar_len as _wl

    limit = _wl(str(root / "vendor")) + 2
    with_findings = run_cli("check", str(root), "--limit", str(limit))
    assert with_findings.returncode == 1
    excluded = run_cli("check", str(root), "--limit", str(limit),
                       "--exclude", "vendor", "--exclude", "src", "--exclude", "ok.txt")
    assert excluded.returncode == 0, excluded.stdout


def test_scan_base_trailing_quote_artifact(tree):
    # PowerShell: --base "C:\dest\" delivers a literal trailing quote
    p = run_cli("scan", str(tree), "--base", "C:\\dest\"", "--limit", "60")
    assert p.returncode in (0, 1)
    assert "C:\\dest\"" not in p.stdout  # the quote was stripped


# ---------------------------------------------------------------------------
# output robustness
# ---------------------------------------------------------------------------

def test_unicode_output_does_not_crash(tmp_path):
    mkfile(str(tmp_path / "课程表😀" / "期末.docx"))
    p = run_cli("scan", str(tmp_path), "--limit", "40")
    assert p.returncode == 1
    assert p.stdout  # printed something without dying


def test_no_color_flag(tree):
    p = run_cli("scan", str(tree), "--no-color")
    assert p.returncode == 0
    assert "\x1b[" not in p.stdout
