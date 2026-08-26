import pytest

from longpath.validate import require_nonneg_top

from conftest import run_cli


def test_require_nonneg_top():
    assert require_nonneg_top(0) == 0
    assert require_nonneg_top(20) == 20
    with pytest.raises(ValueError, match="--top"):
        require_nonneg_top(-1)


def test_scan_negative_top_exit_2(tree):
    p = run_cli("scan", str(tree), "--top", "-1")
    assert p.returncode == 2
    assert "--top must be >= 0" in p.stderr
