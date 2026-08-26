"""longpath - find, lint and delete paths that break the Windows 260-char limit.

Public API::

    from longpath import scan_tree, check_tree, rm_path

    result = scan_tree("D:/projects")             # what exceeds MAX_PATH?
    result = scan_tree(".", base=r"C:\\Users\\me\\OneDrive")   # pre-flight a copy
    issues, stats = check_tree(".")               # portability lint
    outcome = rm_path("D:/stuck/node_modules")    # delete the undeletable
"""
from .core import (
    ALL_RULES,
    DEFAULT_LIMIT,
    Issue,
    OverPath,
    ScanResult,
    check_name,
    check_sibling_names,
    check_tree,
    ext_path,
    long_paths_enabled,
    scan_tree,
    unext,
    wchar_len,
)
from .rm import RmResult, rm_path
from .why import WhyResult, why_path

__version__ = "0.3.2"

__all__ = [
    "ALL_RULES",
    "DEFAULT_LIMIT",
    "Issue",
    "OverPath",
    "RmResult",
    "ScanResult",
    "WhyResult",
    "check_name",
    "check_sibling_names",
    "check_tree",
    "ext_path",
    "long_paths_enabled",
    "rm_path",
    "scan_tree",
    "unext",
    "wchar_len",
    "why_path",
    "__version__",
]
