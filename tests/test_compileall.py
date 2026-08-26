"""CI already runs pytest; this keeps a syntax check without editing workflows."""
from __future__ import annotations

import compileall
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_sources_and_tests_compile() -> None:
    assert compileall.compile_dir(str(ROOT / "src"), quiet=1, force=True)
    assert compileall.compile_dir(str(ROOT / "tests"), quiet=1, force=True)
