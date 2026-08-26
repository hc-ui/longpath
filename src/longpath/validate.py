"""Small CLI argument guards."""


def require_nonneg_top(n: int) -> int:
    if int(n) < 0:
        raise ValueError("--top must be >= 0")
    return int(n)
