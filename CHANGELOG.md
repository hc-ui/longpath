# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.1] - 2026-08-13

Self-audit round 3: final sweep.

### Fixed
- `why` on Windows now treats forward-slash relative paths (`src/deep/file`)
  as native and absolutises them; only rooted `/...` strings are analysed as
  foreign POSIX paths.

### Tests
- 159 tests (+3 unit, +1 full end-to-end user journey): a messy tree with a
  320-char branch, read-only files, emoji names, cursed `aux.log`/`report.`
  files and a junction into precious data goes through
  scan -> why -> check -> rm --dry-run -> rm --yes, asserting the junction
  target survives and the tree ends up clean.

## [0.3.0] - 2026-08-13

Self-audit round 2: product gaps.

### Added
- **New subcommand `longpath why PATH`** — component-by-component breakdown
  of where a path's length budget went: cumulative length column, a marker on
  the component that crosses the budget, and "biggest wins" rename
  suggestions. Pure string analysis: the path does not have to exist, and a
  Windows path pasted out of a log can be analysed on Linux/macOS.
- **`--exclude GLOB`** (repeatable) on `scan` and `check` to skip entries by
  name, e.g. `--exclude .git --exclude node_modules --exclude '*.tmp'`.
- `why` participates in the same exit-code contract (0 fits / 1 over / 2 error)
  and has `--json`.

### Tests
- 156 tests (+19): why-math for drive/UNC/posix/relative/emoji paths,
  crossing-marker uniqueness, suggestion ordering, CLI why e2e, exclude
  behaviour for scan and check.

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
