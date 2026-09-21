---
name: tadado-release
description: |
  Tadado2 的**发布流程**（项目级，只在本仓库用）：验收 → 打包 → 提交 → 推送 → 打 tag / 发 Release
  → 同步 skill 到本机。触发词：发布、发版、打包、重打包、提交、推送、上线、release、打 tag、
  传安装包、同步 skill。在 Tadado 仓库里提到「提交 / 推送 / 打包 / 发布」时用本 skill ——
  它规定每一步的顺序与**安全约束**（尤其是「谁有权推送」）。
---

# Tadado2 发布流程

本 skill 服务的是**这个仓库**：把「代码改完了」变成「用户手上有一个新安装包，仓库也同步了」。

> ⚠️ 动手前先读两份东西：仓库根的 **`CLAUDE.md`**（项目约定与命令）与 **`TODO.md` 末尾两条**
> （最近这轮做了什么、有没有留下没做完的事）。它们比本文件更贴近当下。

## 一次发布 = 五步

| # | 做什么 | 能不能跳 |
|:--:|---|---|
| 1 | **验收**：`npm run e2e` | 动过 `desktop/` 或 `resources/skill/**` 就不能跳 |
| 2 | **打包**：`npm run tauri build` + 便携 zip + 迁移 skill 的 zip | 同上；没动代码可以跳 |
| 3 | **提交**：`git add` + **一次** commit | 不能（有改动就得提交） |
| 4 | **推送**：`git push`、tag、`gh release create` | **用户明确说推才推** ← 见铁律 |
| 5 | **同步 skill**：仓库 → 本机 `.claude/skills/` | 动过 `resources/skill/` 就不能跳 |

## 铁律（这一节比后面所有步骤都重要）

- **推送是用户的动作，不是你的。** `git push`、`gh release create` 必须在用户**明确要求**后才做。
  用户只说「提交」时，做到 commit 为止，然后把该敲的推送命令**原样打给他**，不要自己补上。
- **绝不 force push** —— `--force`、`--force-with-lease` 都不行，`main` 上尤其不行。
- **绝不 `--no-verify`**。hook 拦下来就去看为什么，不要绕过。
- **绝不改 `git config`**（用户名、邮箱、remote 一个都不动）。
- **`--amend` 只在用户明确要求时用**；用之前先 `git log -1 --format='%an %ae'` 确认那条提交是自己的。
- **不把安装包提交进 git**：`desktop/src-tauri/target/`、`desktop/dist/`、`node_modules/`、
  `*.exe` / `*.msi` 一律不进仓库（三个产物加起来 14 MB，仓库不该背）。安装包走 **Release**。
- **提交之前，先让用户看见要提交什么**：给出 `git status --short` 与 `git diff --stat` 的摘要，
  等他确认，再 commit。**不要**自己决定「这些看起来都是我的改动」就一把梭。
- 工作区里混着**别人或上一轮的**改动时（这个仓库很常见），**先问**哪些该一起提交，
  不要替用户挑 —— 挑错的代价是一条提交里混进不相干的改动。

## 步骤 1：验收

```bash
cd desktop
npx tsc --noEmit          # 几秒，先把编译错误挡在前面
npm run e2e               # 构建 + 真浏览器冒烟，约 100–110s
```

- **e2e 必须全绿**（`全部通过`，末尾没有 `FAIL` 行）。红了就先修，不要带着红去打包。
- 顺手记下通过条数（`OK: N` 行数）—— 它突然少了说明有断言没被跑到，值得看一眼。
- **不要**为了「快点」只跑 `tsc` 就往下走：这个仓库栽过好几次「类型合法、点下去没反应」。

## 步骤 2：打包

```bash
cd desktop
npm run tauri build       # release 编译约 3 分钟；内部会先跑 npm run build
```

产物在 `desktop/src-tauri/target/release/bundle/`，**两个**由 bundler 产出：

- `nsis/Tadado2_<版本>_x64-setup.exe`
- `msi/Tadado2_<版本>_x64_en-US.msi`

**第三个产物要两步手工补** —— 便携版**不在** bundler 的目标里（`bundle.targets = "all"` 在
Windows 上只出上面两个）：

```powershell
cd desktop/src-tauri/target/release
Copy-Item desktop.exe bundle\portable\Tadado2.exe -Force
Compress-Archive -Path bundle\portable\Tadado2.exe `
                 -DestinationPath bundle\portable\Tadado2-portable.zip -Force
```

**交付出去的是那个 zip，不是裸 exe**：7.7 MB 的 exe 直接发出去，用户拿到的是「一个不知道要
不要双击的东西」；zip 3.3 MB，一眼就知道是「下载 → 解压 → 运行」。zip 里**只放 `Tadado2.exe`**
一个文件，放在**根**（不要带目录层 —— 解压出来多一层 `portable/` 只会让人多点一下）。

⚠️ **这两步最容易漏，而且漏了都看不出来**：

- 漏第一步 → `Tadado2.exe` 是**上一轮**的二进制（名字一样、版本号一样）；
- 漏第二步 → zip 里装的是**上一次**的 exe（zip 名字也一样）。

核法：两个文件的**时间戳**都该是刚刚；再看一眼 zip 里确实只有 `Tadado2.exe`：

```powershell
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::OpenRead((Resolve-Path bundle\portable\Tadado2-portable.zip).Path).Entries |
  ForEach-Object { $_.Name }
```

**第四个产物：迁移 skill 的 zip** —— 它**不是应用的产物**，是**给用户的 skill 包**：用户下载
Tadado2 之后，想让自己的 Claude Code / Codex 帮忙搬旧数据，就得有这份 skill。所以它跟着
Release 一起发，不跟 `npm run tauri build` 走：

```powershell
cd <仓库根>
Compress-Archive -Path resources\skill\tadado-activity-import `
                 -DestinationPath desktop\src-tauri\target\release\bundle\tadado-activity-import.zip -Force
```

⚠️ **压目录本身，不要压里面的文件**（`-Path resources\skill\tadado-activity-import` 而不是
`...\tadado-activity-import\*`）：zip 里必须保留 `tadado-activity-import/` 这一层，用户解压出来
才能直接放进 `.claude/skills/` —— 少了这层，`.claude/skills/SKILL.md` 是**加载不到**的。

核对四份交付物：

```powershell
Get-ChildItem desktop/src-tauri/target/release/bundle -Recurse -File |
  Where-Object { $_.Extension -in '.msi', '.exe', '.zip' } |
  ForEach-Object { "{0,-42} {1,7} MB  {2}" -f $_.Name, [math]::Round($_.Length/1MB, 2),
                   $_.LastWriteTime.ToString('MM-dd HH:mm') }
```

参考体积：安装包 ≈2.59 MB、MSI ≈3.62 MB、便携 zip ≈3.33 MB（里面那个 exe 是 7.68 MB）、
迁移 skill zip ≈15.6 KB（压缩后；里面三个文件解压出来约 37.7 KB）。
**突然变大**通常意味着打包进了不该进的东西。

## 步骤 3：提交

**先看清楚要提交什么**（这一步是给用户看的，不是给你自己看的）：

```bash
git status --short
git diff --stat
```

然后把摘要讲给用户听，**等他说可以**，再提交。

**提交信息用 Conventional Commits**（这个仓库的既有风格，看 `git log --oneline`）：

| 前缀 | 用在 |
|---|---|
| `feat:` / `feat(desktop):` | 新功能 |
| `fix:` / `fix(desktop):` | 修 bug |
| `docs:` | 只动文档 |
| `test(desktop):` | 只动 e2e |
| `chore(desktop):` | 构建、图标、依赖这类杂事 |
| `refactor(desktop):` | 行为不变的重写 |

- **一次提交讲一件事**。这一轮改了三件不相干的事，就分三次 —— 「顺手一起提交」会让 `git log` 失去检索价值。
- 正文写**为什么**，不写「修改了 X」。`git diff` 已经说得清「改了什么」。
- 提交前扫一眼有没有**不该进**的东西：临时探针、`e2e-*.txt`、`*.tmp`、调试用的 console。

## 步骤 4：推送（**要用户点头**）

**只有用户明确说要推送时**才执行这一段。否则把命令打给他，停在这里。

```bash
git push origin main
```

### 4a. 要不要打 tag / 发 Release

**版本号没变**（还是同一个版本重打包）→ **不打新 tag**，`git push` 完就结束。

**版本号变了**（要发新版本）→ 三处必须**同步改**，缺一处就是不一致：

| 文件 | 字段 |
|---|---|
| `desktop/src-tauri/tauri.conf.json` | `version` |
| `desktop/src-tauri/Cargo.toml` | `[package] version` |
| `desktop/package.json` | `version` |

外加 **[`CHANGELOG.md`](../CHANGELOG.md)** 补一节 `## [x.y.z] — YYYY-MM-DD`（`Added` / `Changed`
/ `Removed` / `Fixed`，参考已有的 v1.0.0 那条的写法）。版本号改动**单独一次提交**，信息写
`chore: 版本号 x.y.z`。

打 tag 与发 Release（`gh` 已装；remote 是 `git@github.com:HananxR/Tadado.git`）：

```bash
git tag -a v1.0.0 -m "Tadado2 v1.0.0"
git push origin v1.0.0
```

```bash
# Release 说明直接用 CHANGELOG 里那一节：先摘出来存成临时文件
gh release create v1.0.0 --title "Tadado2 v1.0.0" --notes-file RELEASE_NOTES.md \
  "desktop/src-tauri/target/release/bundle/nsis/Tadado2_1.0.0_x64-setup.exe" \
  "desktop/src-tauri/target/release/bundle/msi/Tadado2_1.0.0_x64_en-US.msi" \
  "desktop/src-tauri/target/release/bundle/portable/Tadado2-portable.zip" \
  "desktop/src-tauri/target/release/bundle/tadado-activity-import.zip"
```

**四份都要传**，包括那个 15.6 KB 的 skill 包 —— 它体积最小，却最容易被漏（它不跟
`npm run tauri build` 走，`bundle/` 里也不会自己出现）。漏了它，用 AI 助手搬旧数据的用户
只能回去改仓库 URL。

发完把 Release 链接给用户。README 里的下载说明指向 Releases，不用改。

## 步骤 5：同步 skill 到本机

`resources/skill/` 是**仓库里的权威源**，但 `.claude/` 在 `.gitignore` 里 ——
**改完仓库那份，本机那份不会跟着变**。要生效得把它拷过去：

```powershell
cd <仓库根>
Get-ChildItem resources\skill -Directory | ForEach-Object {
  $dest = "$env:USERPROFILE\.claude\skills\$($_.Name)"
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  Copy-Item "$($_.FullName)\*" $dest -Recurse -Force
}
```

- 拷完**核一眼**：本机那份的 `SKILL.md` 与仓库那份的 `version:` 应当一致。
- ⚠️ **不要在 `.claude/skills/` 那边改内容** —— 两份必然分叉。改仓库，再拷过来。
- 新加了一个 skill 目录时也要跑这一步，否则它在本机**根本不会被加载**。

## 常见情况

| 情况 | 怎么办 |
|---|---|
| 工作区是干净的（没有改动） | 跳过步骤 3、4；只做验收 + 打包 + 同步 skill |
| 只动了文档 / skill，没动 `desktop/` | 可以跳步骤 2 的打包（产物不会变），但 `resources/skill/**` 动了就得跑 e2e（CI 也监听它） |
| 用户说「重新打包」但没说推送 | 做完 1、2，提交与否**问他**，推送**等他明说** |
| 打包失败 | 先看是不是 Rust 编译错误（`2m` 那一步）；不要为了绕过去把 `lto` / `strip` 关掉 |
| e2e 红了但用户催着打包 | **不要**带着红的构建去打包。先修，或者明确告诉他「这是带病的包」并让他定 |
| 版本号没变却要发 Release | 别发 —— `gh release create` 同 tag 会失败，先确认用户到底要什么 |

## 在这台机器上干活：PowerShell 的几个坑

仓库的自动化都在 Windows 的 PowerShell 下跑，下面几条是**实际踩过的**（不是理论上的）。

### 1. `Get-Content` 默认按 GBK 读，UTF-8 文件会整段乱码

`CHANGELOG.md` / `README.md` / `TODO.md` 都是 UTF-8。直接读会得到「鈥?」「銆?」这种 ——
**看着像文件坏了，其实只是解码错了**。摘 CHANGELOG 做 Release 说明时踩过一次。

```powershell
# 读：显式给 UTF8
$all = Get-Content CHANGELOG.md -Raw -Encoding UTF8

# 写：也要显式，并且关掉 BOM
[System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding $false))
```

⚠️ `Set-Content -Encoding UTF8` 在 PowerShell 5.1 下会**写 BOM**；给 `gh --notes-file` 用还能忍，
但 `WriteAllText` 干净。

**判断文件到底坏没坏**：用编辑器（或 AI 工具的 `read_file`）打开看一眼 —— 那边按 UTF-8 解码。
**不要**因为控制台乱码就去「修」文件。

### 2. `git mv` 搬不动未跟踪的文件

`git mv` 要求源文件**已被跟踪**。这个仓库有过整个 `tools/` 目录都没 `git add` 过的情况，
于是 `git mv tools/x.mjs resources/x.mjs` 直接报 `fatal: not under version control`。

```powershell
Move-Item tools\x.mjs resources\x.mjs -Force    # 退而求其次
```

代价：git 认不出这是一次「重命名」，日志里会显示成一条删除 + 一条新增。文件已被跟踪之后再搬就没这问题。

### 3. `gh … --jq` 在 PowerShell 里会被拆参数

```powershell
# ✗ accepts at most 1 arg(s), received 3 —— `|` 那些被 PowerShell 先吃了
gh release view v1.0.0 --json assets --jq '.assets[] | "\(.name)"'

# ✓ 交给 ConvertFrom-Json
(gh release view v1.0.0 --json assets | ConvertFrom-Json).assets |
  ForEach-Object { "{0}  {1} KB" -f $_.name, [math]::Round($_.size/1KB, 1) }
```

### 4. `git push` 的进度输出走 stderr —— **报红不等于失败**

`git push` 把 `To github.com:…` 和 `* [new tag] …` 写在 **stderr**，而 PowerShell 会把原生命令的
stderr 渲染成红字 + `NativeCommandError`。**看这一行判断成败**：

```
7544c12..acf75ec  main -> main
```

### 5. 长日志别用 `Select-String` 全量过

`npm run e2e` 会打几百行，`Select-String` 会把整份输出读进内存再过滤，很容易爆掉内部缓冲
（输出被截断，看不到真正想找的那条）。做法是**先落盘再筛**：

```powershell
npm run e2e 2>&1 | Tee-Object -FilePath e2e-check.txt | Select-String -Pattern '^FAIL|全部通过'
```

之后再从那个文件里统计（`Select-String -Path e2e-check.txt -Pattern '^OK' | Measure-Object`）。
**跑完记得删** —— 它是临时文件，不该留在工作区（`git status` 里会冒出来）。

## 这份 skill 为什么存在

因为这套流程**每一步都踩过坑**：

- 便携版**不在 bundler 的目标里**，要手工「拷 exe + 压 zip」两步 —— 漏哪一步都会得到一个
  「名字对、版本对、其实是旧的」文件；
- 迁移 skill 的 zip **不在任何构建流程里**，要手工压一次 —— 漏了它，Release 上就只有应用、
  没有配套的 skill；
- 版本号散在**三个文件**里 —— 只改一个，装出来的程序版本资源与仓库对不上；
- `resources/skill/` 是权威源而 `.claude/` 被忽略 —— 不同步，改了等于没改；
- 安装包**不能进 git** —— 走 Release。

前三条都在 `TODO.md` 里留着当时的记录，遇到疑问去那儿翻。
