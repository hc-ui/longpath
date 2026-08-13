# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-08-13

Initial release.

### Added
- `longpath scan` — measure every path in a tree against a MAX_PATH-style
  budget (default 260), with UTF-16 code-unit accurate lengths, worst-first
  listing, nesting depth, and the Windows `LongPathsEnabled` policy state.
- `longpath scan --base DEST` — destination simulation: pre-flight a copy
  into a deep folder (OneDrive/SharePoint/USB/NAS) before it fails with
  "Destination Path Too Long".
- `longpath check` — portability lint with 8 rules: `too-long`,
  `reserved-name`, `illegal-char`, `trailing-dot-space`, `case-collision`,
  `unicode-collision`, `component-too-long`, `undecodable-name`.
- `longpath rm` — robust delete for trees beyond 260 chars: extended-length
  `\\?\` paths, read-only attribute clearing, never follows symlinks or
  junctions, refuses filesystem roots, `--dry-run`, error aggregation.
- `--json` (ASCII-safe) and `-q` on every command; lint-style exit codes
  (0 clean / 1 findings / 2 error).
- Python API: `scan_tree`, `check_tree`, `rm_path`, `check_name`,
  `check_sibling_names`, `wchar_len`, `ext_path`.
- 126 tests across Windows/Linux/macOS semantics, including real junction
  and symlink safety tests and a junction-loop termination test.
