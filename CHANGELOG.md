# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-08-13

Self-audit round 1: correctness fixes found by deliberately hunting for bugs.

### Fixed
- **CLI existence pre-checks are now long-path aware.** `longpath rm <320-char
  path>` used to answer "path does not exist" on default-policy Windows -
  the exact scenario the tool exists for.
- **`ext_path` preserves trailing dots/spaces in the final component.**
  `os.path.abspath` (GetFullPathNameW) silently strips them, so
  `longpath rm "trailing."` addressed the wrong name. Cursed names now
  round-trip correctly.
- `rm --json` output is safe for undecodable (raw-byte) paths.
- The scan header echoed the raw `--base` value before quote-artifact cleanup.

### Added
- `\` (backslash) flagged as illegal-on-Windows: such names can be created on
  POSIX filesystems and guarantee breakage when checked out on Windows.
- `CONIN$` / `CONOUT$` added to the reserved-name rule.
- `--limit` validation on `check` (previously only `scan` validated it).
- PowerShell trailing-quote artifacts in `--base "C:\dest\"` are stripped.

### Tests
- 137 tests (+11): cursed-name creation via `\\?\` with detection & deletion
  on real NTFS, >260-char direct-target CLI regressions, exact 259/260
  boundary, backslash rule, JSON surrogate safety.

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
