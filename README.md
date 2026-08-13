# longpath

[![CI](https://github.com/hc-ui/longpath/actions/workflows/ci.yml/badge.svg)](https://github.com/hc-ui/longpath/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/longpath)](https://pypi.org/project/longpath/)
[![Python](https://img.shields.io/badge/python-3.9%E2%80%933.14-blue)](https://github.com/hc-ui/longpath)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**English** | [中文](#longpath-中文)

Fix **"path too long"** for good — before *or* after it bites:

- `longpath scan` — find every path that breaks the Windows **260-character MAX_PATH** limit, or *simulate a copy* into a deep destination folder **before** you hit "Destination Path Too Long"
- `longpath check` — lint a repo/folder for names that break Windows & macOS: reserved names (`CON`, `NUL`, …), illegal characters, trailing dots, case collisions, over-long paths. CI-friendly exit codes
- `longpath rm` — delete the trees that Explorer, `del`, `rmdir` and `shutil.rmtree` refuse to delete

Pure Python standard library. **Zero dependencies.** Works on Windows, Linux and macOS.

```
pip install longpath
```

## Sound familiar?

> ❌ *Destination Path Too Long — The file name(s) would be too long for the destination folder.*

> ❌ *The source file name(s) are larger than is supported by the file system.*

> ❌ `error: invalid path 'aux.md'` / `error: unable to create file ... Filename too long` — during `git clone` on Windows

> ❌ `PermissionError: [WinError 206] The filename or extension is too long`

> ❌ Cannot delete `node_modules` — the path is too long, and the folk remedy is a weird `robocopy /MIR` trick

Windows still ships with a 260-character path budget. You usually discover this **after** the copy died at 87%, the backup silently skipped files, or a colleague on Windows can't clone the repo you made on Linux. `longpath` finds these landmines up front, and cleans up the wreckage when it's too late.

## Quick start

```bash
# what in this tree already breaks the 260-char limit?
longpath scan D:\projects

# PRE-FLIGHT: will copying this folder into that deep OneDrive dir break?
longpath scan .\thesis --base "C:\Users\me\OneDrive - University\Documents\FinalWork"

# lint this repo for Windows-breaking names (great in CI)
longpath check .

# delete what Explorer refuses to delete
longpath rm D:\stuck\node_modules
```

## What it looks like

### `scan` — find the landmines

```
$ longpath scan D:\data
longpath scan  D:\data
  budget: 259 usable chars (limit 260)
  scanned: 12,304 files, 1,201 dirs   deepest nesting: 14
  longest: 312 chars  D:\data\projects\archive\2024\group-final\node_modules\...\index.d.ts

3 paths exceed the budget (worst is 53 chars over):
  +53    312      D:\data\projects\archive\2024\group-final\node_modules\@typescript-eslint\...\index.d.ts
  +21    280      D:\data\projects\archive\2024\group-final\node_modules\.cache\babel-loader\...
  +2     261  DIR D:\data\backup\photos\2023 holiday trip with the whole family\raw exports\selected

Windows long-path policy: DISABLED - Explorer, cmd and most apps stop at 260 chars
  enable (admin): reg add "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled /t REG_DWORD /d 1 /f
hints: fix by shortening the deepest folders; delete stuck trees with 'longpath rm <path>'; preview a copy with '--base DEST'
```

### `scan --base` — pre-flight a copy *before* it fails

The killer feature nothing else does: measure your tree **as if it were copied into a destination**, so "Destination Path Too Long" never surprises you again. Works for OneDrive/SharePoint sync folders (which add their own long prefixes), USB hand-offs, zip extraction targets, NAS moves.

```
$ longpath scan .\thesis --base "C:\Users\student\OneDrive - University\Documents\Course Materials\Final"
longpath scan  D:\work\thesis
  budget: 259 usable chars (limit 260)   simulating copy into: C:\Users\student\OneDrive - University\...
  scanned: 214 files, 37 dirs   deepest nesting: 6

7 paths exceed the budget (worst is 44 chars over):
  +44    303      C:\Users\student\OneDrive - University\...\thesis\data\interviews\transcripts\...
  ...
```

Exit code is `1` when anything would break — perfect for a pre-copy check in scripts.

### `check` — portability lint for repos and shared folders

Made on Linux/macOS, broken on Windows: reserved device names, `:` in filenames, names ending with a dot, `README.md` vs `readme.md` in one directory. These make `git clone` fail or silently produce wrong files on other people's machines. Run `longpath check .` in CI and never ship one again.

```
$ longpath check .
longpath check  /home/me/my-repo
6 issue(s) in 3,456 paths

[reserved-name] (1)
  /home/me/my-repo/docs/aux.md
      'aux.md' is a reserved DOS device name on Windows (AUX); Windows cannot create it and git clone fails with 'invalid path'

[illegal-char] (2)
  /home/me/my-repo/notes/plan:v2.txt
      'plan:v2.txt' contains characters illegal on Windows: :

[case-collision] (1)
  /home/me/my-repo/src
      'Utils.py', 'utils.py' differ only by letter case; they collide on the case-insensitive filesystems of Windows/macOS and git checkout silently overwrites one with the other
...
```

Rules: `too-long` · `reserved-name` · `illegal-char` · `trailing-dot-space` · `case-collision` · `unicode-collision` · `component-too-long` · `undecodable-name` — suppress any with `--ignore`.

### `rm` — delete the undeletable

```
$ longpath rm D:\stuck\node_modules
Delete D:\stuck\node_modules? This cannot be undone. [y/N] y
deleted: D:\stuck\node_modules  (48,211 files, 6,890 dirs)
```

- handles paths **far beyond 260 chars** (extended-length `\\?\` API paths — no registry change, no reboot)
- clears the **read-only** attribute when it blocks deletion
- **never follows symlinks or junctions** — only the link is removed, the target survives (this is the mistake that turns "clean a temp folder" into "wipe your user profile")
- refuses to delete filesystem roots; `--dry-run` previews; keeps going on errors and reports every failure

## Why not X?

| | pip install, everywhere | Windows | Linux/macOS | Find/scan *before* copying | Repo lint (CI) | Delete >260 trees | Zero deps | Python API |
|---|---|---|---|---|---|---|---|---|
| **longpath** | ✅ | ✅ | ✅ | ✅ `--base` pre-flight | ✅ 8 rules | ✅ | ✅ | ✅ |
| SuperDelete (C#) | ❌ download .exe | ✅ | ❌ | ❌ | ❌ | ✅ | – | ❌ |
| winrmrf (Nim, 2017) | ❌ download .exe | ✅ | ❌ | ❌ | ❌ | ✅ | – | ❌ |
| `robocopy /MIR` empty-dir trick | built-in | ✅ | ❌ | ❌ | ❌ | ✅ arcane, destructive if mistyped | – | ❌ |
| PowerShell `\\?\` + `Remove-Item` | built-in | ✅ | ❌ | ❌ | ❌ | ⚠️ manual, easy to get wrong | – | ❌ |
| "Long Path Tool" | ❌ | ✅ | ❌ | ❌ | ❌ | 💰 nagware that monetises this exact search query | – | ❌ |
| Enabling `LongPathsEnabled` | – | ⚠️ | – | ❌ | ❌ | ⚠️ helps only manifest-aware apps; Explorer still fails | – | – |
| `git core.protectNTFS` | – | ✅ | – | ❌ | ⚠️ clone-time only, git files only | – | – | – |

## How it actually works (the 260 truth table)

Things almost every blog post gets subtly wrong — `longpath` gets them right:

- **`MAX_PATH` is 260, but the budget is 259** — the count includes a terminating `NUL`. A 260-char path already fails. (Directories effectively get ~248, because Windows reserves room for an 8.3 filename.)
- **The limit counts UTF-16 code units, not "characters".** An emoji or any non-BMP character costs **2** units. `longpath` measures `len(path.encode('utf-16-le'))//2`, not `len(path)` — so 中文 counts 1 per char, 😀 counts 2.
- **`LongPathsEnabled` is not a fix.** It lifts the limit only for applications that declare `longPathAware` in their manifest. Explorer, most installers and plenty of tools still fail. That's why `scan` tells you the policy state but treats 260 as the real-world budget.
- **`\\?\` extended-length paths bypass the limit entirely** (up to ~32,767 units). `longpath rm` and the scanner use them internally, which is also how the scanner can even *see* paths that other tools cannot traverse.
- **Junctions and symlinks are landmines during deletion.** `longpath` detects reparse points and removes the *link*, never the target — and its test suite proves it with real junctions.
- **OneDrive/SharePoint have their own ~400-char ceilings** that include the sync-root prefix. Model them with `--limit 400 --base "<your sync folder>"`.

## Python API

```python
from longpath import scan_tree, check_tree, rm_path

result = scan_tree(r"D:\projects")                     # what's over MAX_PATH?
for p in result.over:
    print(p.over, p.path)

result = scan_tree("thesis", base=r"C:\Users\me\OneDrive\Documents")   # pre-flight
issues, stats = check_tree(".", ignore={"too-long"})   # portability lint
outcome = rm_path(r"D:\stuck\node_modules")            # delete the undeletable
print(outcome.ok, outcome.files_removed, outcome.errors)
```

## CLI reference

```
longpath scan  [DIR] [--limit N] [--base DEST] [--top N] [--all] [--json] [-q]
longpath check [DIR] [--limit N] [--base DEST] [--ignore RULES]     [--json] [-q]
longpath rm    PATH... [-y] [-n/--dry-run]                          [--json] [-q]
```

`longpath <dir>` is shorthand for `longpath scan <dir>`. Exit codes: **0** clean · **1** findings · **2** error — so both `scan` and `check` drop straight into CI:

```yaml
- run: pip install longpath && longpath check .
```

## FAQ

**Do I need admin rights?** No. Everything works as a normal user (only *enabling* the long-path policy needs admin, and that's a suggestion `longpath` prints, not something it does).

**Why can't Explorer delete these folders anyway?** Explorer isn't long-path aware even with the policy enabled. `longpath rm` talks to the filesystem with `\\?\` extended-length paths, which have worked since Windows XP.

**I'm on Linux/macOS — why would I care?** Because your *users* are on Windows. `longpath check` in CI catches the `aux.md` file or the `Utils.py`/`utils.py` pair before they break `git clone` for half your team. It also pre-flights copies to NAS/USB/network shares.

**Is it safe?** `rm` never follows links (junction/symlink targets survive), refuses filesystem roots, has `--dry-run`, and requires `-y` in non-interactive use. The scanner is read-only.

**What Python versions?** 3.9 – 3.14, CPython, no dependencies at all.

## License

[MIT](LICENSE) © hc-ui

---

# longpath (中文)

[English](#longpath) | **中文**

一条命令根治**"路径太长"**——事前预防,事后救援:

- `longpath scan` —— 找出所有超过 Windows **260 字符 MAX_PATH** 限制的路径;还能**预演复制**:先算一遍"拷进那个很深的目标文件夹会不会爆",再动手
- `longpath check` —— 给仓库/文件夹做 Windows/macOS 兼容性体检:保留名(`CON`、`NUL`…)、非法字符、结尾句点、大小写冲突、超长路径,退出码适配 CI
- `longpath rm` —— 删除资源管理器、`del`、`rmdir`、`shutil.rmtree` 都删不掉的目录树

纯 Python 标准库,**零依赖**,Windows / Linux / macOS 全平台。

```
pip install longpath
```

## 这些报错眼熟吗?

> ❌ *目标路径太长 —— 文件名对目标文件夹可能过长。*

> ❌ *源文件名长度大于文件系统支持的长度。*

> ❌ Windows 上 `git clone` 报 `error: invalid path 'aux.md'` 或 `Filename too long`

> ❌ `PermissionError: [WinError 206] 文件名或扩展名太长`

> ❌ `node_modules` 删不掉,网上教你用 `robocopy /MIR` 空目录镜像这种偏方

Windows 至今默认带着 260 字符的路径预算。你往往在复制到 87% 失败、备份悄悄漏文件、或者 Windows 同学克隆不了你在 Linux 上建的仓库时,才发现踩了雷。`longpath` 把雷提前找出来;真炸了,也能收拾残局。

## 快速上手

```bash
# 这棵目录树里,哪些路径已经超 260 了?
longpath scan D:\资料

# 预演:把论文文件夹拷进 OneDrive 深层目录,会不会爆?
longpath scan .\毕业论文 --base "C:\Users\me\OneDrive - 学校\文档\最终版"

# 给仓库做兼容性体检(CI 必备)
longpath check .

# 删掉资源管理器删不掉的东西
longpath rm D:\卡住的\node_modules
```

## 三个子命令

**`scan`(扫描)**:统计文件/目录数、最深嵌套、最长路径;列出超预算的路径和超出量;在 Windows 上顺带告诉你 `LongPathsEnabled` 策略的状态和开启命令。退出码:发现超限为 `1`,干净为 `0`。

**`scan --base 目标路径`(复制预演)**:这是别的工具都没有的能力——把整棵树"虚拟拷贝"到目标文件夹再量一遍长度。OneDrive/SharePoint(同步前缀很长,总预算约 400,可配 `--limit 400`)、U 盘交作业、NAS 搬家、解压目标,都能提前算。

**`check`(体检)**:8 条规则——`too-long`(超长)、`reserved-name`(CON/NUL/COM1 等保留名)、`illegal-char`(`< > : " | ? *` 及控制字符)、`trailing-dot-space`(结尾句点/空格)、`case-collision`(仅大小写不同,Windows/macOS 上互相覆盖)、`unicode-collision`(NFC/NFD 同名,mac 常见)、`component-too-long`(单个名字超 255)、`undecodable-name`(非法编码文件名)。`--ignore` 可跳过任意规则。

**`rm`(强删)**:内部全程使用 `\\?\` 扩展路径(不改注册表、不用重启);自动清只读属性;**绝不跟随符号链接/junction**——只删链接本身,目标完好(这是把"清理临时目录"变成"清空用户资料"的经典事故,我们用真实 junction 测试过);拒绝删除盘符根目录;支持 `--dry-run` 预演;删除中途出错会继续删并汇总报告。

## 为什么不用别的?

| | pip 安装全平台 | 事前扫描/预演 | 仓库体检(CI) | 删除超长树 | 零依赖 | Python API |
|---|---|---|---|---|---|---|
| **longpath** | ✅ | ✅ `--base` 预演 | ✅ 8 条规则 | ✅ | ✅ | ✅ |
| SuperDelete(C#) | ❌ 下载 exe,仅 Windows | ❌ | ❌ | ✅ | – | ❌ |
| winrmrf(2017) | ❌ 下载 exe,仅 Windows | ❌ | ❌ | ✅ | – | ❌ |
| `robocopy /MIR` 偏方 | 系统自带 | ❌ | ❌ | ✅ 但阴间且打错就毁数据 | – | ❌ |
| Long Path Tool | ❌ | ❌ | ❌ | 💰 专门收割这个搜索词的流氓软件 | – | ❌ |
| 开 `LongPathsEnabled` | – | ❌ | ❌ | ⚠️ 只对声明过 manifest 的程序生效,资源管理器照样不行 | – | – |

## 原理(260 的真相)

- **MAX_PATH 是 260,但可用只有 259**——计数包含结尾的 `NUL` 终止符;目录实际约 248(要给 8.3 短文件名留位)。
- **限制按 UTF-16 码元计,不是"字符数"**:中文每字 1 个码元,emoji 每个 **2** 个码元。`longpath` 用 `len(path.encode('utf-16-le'))//2` 计量,而不是 `len(path)`——大多数工具连这一点都算错。
- **`LongPathsEnabled` 不是万灵药**:只对 manifest 里声明了 `longPathAware` 的程序生效。所以 `scan` 会显示策略状态,但仍按 260 作为现实预算。
- **`\\?\` 扩展路径彻底绕过限制**(上限约 32767 码元),`longpath` 的扫描器和删除器内部全程使用它——这也是它能"看见"别的工具遍历不进去的目录的原因。

## 退出码与 CI

`0` 干净 · `1` 有发现 · `2` 出错。`longpath <目录>` 等价于 `longpath scan <目录>`。三个子命令都有 `--json`(纯 ASCII 转义,任何终端编码下都安全)。

```yaml
- run: pip install longpath && longpath check .
```

## 许可

[MIT](LICENSE) © hc-ui
