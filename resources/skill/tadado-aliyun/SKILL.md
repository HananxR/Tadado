---
name: tadado-aliyun
description: |
  把 Tadado2 的安装包上传到**阿里云盘**（国内下载渠道）、生成分享链接，再把链接写进 README。
  触发词：阿里云、阿里云盘、国内下载、国内镜像、网盘、上传安装包、分享链接、aliyunpan、提取码。
  与 `tadado-release` 的分工：那个管「从代码到 GitHub Release」，这个管「Release 之后，
  让国内用户真的下得到」。
---

# 安装包 → 阿里云盘（国内下载渠道）

## 为什么要有这一步

GitHub Releases 在国内**经常打不开**。旧版（v0.x）就吃过这个亏：`v0.1.2.1` 加了阿里云盘渠道，
`v0.1.2.3` 把「检查更新」也改成**阿里云盘优先、GitHub 备用**。Tadado2 没有联网能力、不会自己
检查更新，但**下载这一步照样会被挡住** —— 所以要有镜像。

## 工具：`aliyunpan`（第三方，不是官方）

阿里云盘**没有官方 API**，官方客户端也不提供命令行。能自动化的唯一途径是社区工具
**[`aliyunpan`](https://github.com/tickstep/aliyunpan)**（Go 写的单文件 exe，开源）。

**先找它在哪** —— 不要假设它在 `PATH` 里（实测它就是放在某个自解压目录下的）：

```powershell
Get-ChildItem -Path "C:\", "D:\" -Filter "aliyunpan.exe" -Recurse -Depth 3 -ErrorAction SilentlyContinue |
  ForEach-Object { $_.FullName }
```

**没找到就问用户**。**不要**自己下载安装 —— 它是第三方工具，装不装、装在哪由用户决定。

登录由用户做（`.\aliyunpan.exe login`，浏览器 + 手机扫码两次）。**这一步别代劳**，
也别去读它写下的凭证。

### ⚠️ 账号安全：这个 skill 里一个字都不许出现

工具把登录凭证存在它自己目录下的 `aliyunpan_config.json`。四条规矩，**没有例外**：

1. **不读** `aliyunpan_config.json`，也不读 `aliyunpan_command_history.txt`；
2. **不把它们的路径或内容**写进 skill、`TODO.md`、提交信息、对话；
3. 要看登录状态就**让工具自己回答** —— `aliyunpan ls /` 能列出内容就是登录了。
   **别用 `who` / `loglist` / `quota`**：那几条会打印账号名、手机号、UID、空间配额；
4. **不把工具目录复制进仓库**。它本来就该在仓库外（`D:\…` 之类），保持这样。

## 步骤 1：上传前校验

```powershell
cd <仓库根>/desktop/src-tauri/target/release/bundle
Get-ChildItem -Recurse -File | Where-Object { $_.Extension -in '.exe','.msi','.zip' } |
  Sort-Object Name | ForEach-Object { "{0,-42} {1,7} MB  {2}" -f $_.Name,
    [math]::Round($_.Length/1MB,2), $_.LastWriteTime.ToString('MM-dd HH:mm') }
```

**时间戳必须都是刚刚** —— 几个产物里只要有一个偏旧，传上去的就是上一版，而名字、版本号
全是对的，看不出来。参考体积：setup ≈2.59 MB / MSI ≈3.62 MB / portable zip ≈3.33 MB /
skill zip ≈15.6 KB。

**算 SHA256 并当场记下来** —— 它是「网盘上那份和 Release 上那份是不是同一个文件」的唯一证据：

```powershell
Get-FileHash nsis\Tadado2_<版本>_x64-setup.exe -Algorithm SHA256
```

## 步骤 2：上传

```powershell
cd <aliyunpan 所在目录>
.\aliyunpan.exe ls /                    # 能列出来 = 已登录
.\aliyunpan.exe ls /Tadado              # 看目标目录在不在（不在就 mkdir /Tadado）
.\aliyunpan.exe upload "<仓库根>\desktop\src-tauri\target\release\bundle\nsis\Tadado2_<版本>_x64-setup.exe" /Tadado
```

⚠️ **`upload` 最后一个参数是「目标目录」，不是「另存为的文件名」。** 写成
`upload <本地文件> /Tadado/Tadado2_setup_v1.0.0.exe` 会得到一个**同名目录**，文件被塞进去：
`/Tadado/Tadado2_setup_v1.0.0.exe/Tadado2_1.0.0_x64-setup.exe`。
这是实际踩过的坑 —— **传完一定 `ls /Tadado` 核一眼**，发现错了就 `rm` 掉那个目录重来
（回收站可恢复）。

**命名沿用 `/Tadado` 里既有的规律**（那里面是 v0.x 的全套历史：`Tadado_setup_v0.2.4.exe`、
`Tadado_v0.2.4_portable.zip`、`Tadado_v0.2.4_linux.tar.gz`、`Tadado_v0.2.0_source.zip`）：

```powershell
.\aliyunpan.exe rename /Tadado/Tadado2_<版本>_x64-setup.exe /Tadado/Tadado2_setup_v<版本>.exe
```

**传什么**：默认**只传 setup.exe**。用户点名要便携版就再加 `portable/Tadado2-portable.zip`。
**不传 MSI** —— 它是企业静默分发的用途，那种场景本来也不走网盘。

## 步骤 3：生成分享链接

```powershell
.\aliyunpan.exe share set -mode 1 /Tadado/Tadado2_setup_v<版本>.exe
# → 链接：https://www.alipan.com/s/xxxxxxxx   提取码：xxxx
```

两种模式：`-mode 1` 普通分享（**只支持少数文件类型**，`.exe` 实测可以）、
`-mode 3` 快传链接（支持大部分文件，zip 之类走这条）。**先试 `-mode 1`**，失败再换 `-mode 3`。

⚠️ 它默认生成的是**私密分享（带提取码）**。这是好事，但 **README 里必须把提取码写上** ——
不写等于没分享。

⚠️ **文件分享的链接绑的是「这一次」的那个文件。** 下次发版要**重新分享**、并**回来改 README**。
所以步骤 5 的回执里必须有这一条提醒。想彻底避免的话是去云盘里**分享文件夹**（整个 `/Tadado`，
链接长期不变），但那样用户进去会看到三十几个历史版本、得自己挑 —— 现阶段
**「文件分享 + 每次改 README」更直接**。

## 步骤 4：写进 README

README 的「安装」一节表格之后加（已有就改）：

```md
> **国内下载**（不用访问 GitHub）：阿里云盘 <链接>，提取码 `<码>`。
> 与 Releases 上的文件完全相同 —— 安装包 SHA256 `C8741B…`，下完可以自己核一下。
```

- **写清提取码**（藏起来等于没有）；
- **附上 SHA256** —— 网盘上的文件没有签名，哈希是唯一能让用户自证「下的没被换过」的东西。

## 步骤 5：回执与留痕

- 告诉用户：传了什么、多大、SHA256、链接与提取码；
- **记进 `TODO.md`**；
- **明确提醒**：下次发版要重新分享并回来改 README。

## 常见问题

| 情况 | 怎么办 |
|---|---|
| 找不到 `aliyunpan.exe` | 问用户，**别自己下载**（第三方工具，装哪由他定） |
| 想查当前登录的是哪个账号 | **不要**。用 `ls /` 证明登录即可（`who` / `loglist` 会打印账号信息） |
| 上传后云盘上多了个怪目录 | 八成是把目标目录写成了文件名 —— `ls` 看一眼，`rm` 掉重传 |
| 分享失败（文件类型不支持） | 换 `-mode 3`（快传）；再不行把 exe 压成 zip 再分享 |
| 用户给的是夸克 / 百度 / 蓝奏云 | 同一套流程，只是工具和命令不同；**账号那四条规矩照旧** |
| 想顺便做「检查更新」 | Tadado2 **没有联网能力**（权限清单里没有网络权限），**别去实现** |
| 传完发现传错了（旧文件 / 少传） | 回步骤 1 重核时间戳与哈希，**别只改 README 了事** |
