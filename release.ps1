<#
  Tadado 自动发布脚本（基于 git 推送）
  用法: .\release.ps1 v0.1.0
  说明: 本地构建完后，通过 git 分支上传产物，自动创建 Release
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Token = $env:GITHUB_TOKEN
if (-not $Token) { $Token = Read-Host "GitHub Token" }

$Repo = "HananxR/Tadado"
$Headers = @{ Authorization = "Bearer $Token"; Accept = "application/vnd.github+json" }

# ── 1. Build ──
Write-Host "`n[1/4] PyInstaller 构建 ..." -ForegroundColor Cyan
& cmd /c build.bat
if ($LASTEXITCODE -ne 0) { throw "build.bat failed" }

# ── 2. Inno Setup ──
Write-Host "`n[2/4] Inno Setup 安装包 ..." -ForegroundColor Cyan
$iscc = @("C:\Program Files\Inno Setup 7\ISCC.exe",
          "C:\Program Files (x86)\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc installer.iss
    $setupExe = Get-ChildItem dist/Tadado_setup_*.exe | Sort-Object LastWriteTime -Descending | Select-Object -First 1
} else { Write-Warning "Inno Setup not found" }

# ── 3. ZIP ──
$zipPath = "dist/Tadado_${Version}_portable.zip"
Compress-Archive -Path dist/Tadado/* -DestinationPath $zipPath -Force

# ── 4. Push assets branch ──
Write-Host "`n[3/4] Push assets to git ..." -ForegroundColor Cyan
$branch = "release-$Version"
git checkout --orphan $branch 2>$null
git rm -rf --cached . 2>$null
Copy-Item $setupExe.FullName . -Force
Copy-Item $zipPath . -Force
git add *.exe *.zip
git commit -m "Release $Version assets"
git push origin $branch --force
git checkout main

# ── 5. Create release ──
Write-Host "`n[4/4] Create GitHub Release ..." -ForegroundColor Cyan
git tag -d $Version 2>$null
git tag $Version -m "Tadado $Version"
git push origin :refs/tags/$Version 2>$null
git push origin $Version

$changelog = Get-Content CHANGELOG.md -Raw -Encoding UTF8
$setupName = Split-Path $setupExe.FullName -Leaf
$zipName = Split-Path $zipPath -Leaf
$body = @"
$changelog

## 下载

| 文件 | 说明 |
|------|------|
| [$setupName](https://github.com/HananxR/Tadado/raw/$branch/$setupName) | Inno Setup 安装包 |
| [$zipName](https://github.com/HananxR/Tadado/raw/$branch/$zipName) | 便携版，解压即用 |
"@

$releaseData = @{ tag_name = $Version; name = "Tadado $Version"; body = $body; draft = $false } | ConvertTo-Json
$release = Invoke-RestMethod "https://api.github.com/repos/$Repo/releases" `
    -Method Post -Headers $Headers -Body $releaseData -ContentType "application/json"

Write-Host "`n=== Done! $($release.html_url) ===" -ForegroundColor Green
