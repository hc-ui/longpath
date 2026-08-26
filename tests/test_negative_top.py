import pytest

from longpath.validate import require_nonneg_top


def test_require_nonneg_top():
    assert require_nonneg_top(0) == 0
    assert require_nonneg_top(20) == 20
    with pytest.raises(ValueError, match="--top"):
        require_nonneg_top(-1)
