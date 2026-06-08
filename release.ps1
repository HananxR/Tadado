<#
  Tadado 自动发布脚本
  用法: .\release.ps1 v0.1.0
  前置: 设置环境变量 $env:GITHUB_TOKEN 或在脚本中填入你的 GitHub Token
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# ── 获取 GitHub Token ──
$Token = $env:GITHUB_TOKEN
if (-not $Token) {
    $Token = Read-Host -Prompt "请输入 GitHub Personal Access Token (repo 权限)"
}
$Headers = @{
    Authorization = "Bearer $Token"
    Accept = "application/vnd.github+json"
}
$Repo = "HananxR/Tadado"

# ── Step 1: 本地构建 ──
Write-Host "`n[1/5] 构建 PyInstaller ..." -ForegroundColor Cyan
& cmd /c build.bat
if ($LASTEXITCODE -ne 0) { throw "build.bat 失败" }

# ── Step 2: Inno Setup 安装包 ──
Write-Host "`n[2/5] 编译 Inno Setup 安装包 ..." -ForegroundColor Cyan
$isccPaths = @(
    "C:\Program Files\Inno Setup 7\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
)
$iscc = $null
foreach ($p in $isccPaths) { if (Test-Path $p) { $iscc = $p; break } }
if ($iscc) {
    & $iscc installer.iss
    $setupExe = Get-ChildItem dist/Tadado_setup_*.exe | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Write-Host "  OK: $($setupExe.Name)" -ForegroundColor Green
} else {
    Write-Warning "Inno Setup 未安装，跳过安装包"
}

# ── Step 3: 便携 ZIP ──
Write-Host "`n[3/5] 压缩便携版 ..." -ForegroundColor Cyan
$zipPath = "dist/Tadado_${Version}_portable.zip"
Compress-Archive -Path dist/Tadado/* -DestinationPath $zipPath -Force
Write-Host "  OK: $zipPath" -ForegroundColor Green

# ── Step 4: 创建 Release ──
Write-Host "`n[4/5] 创建 GitHub Release ..." -ForegroundColor Cyan
$tagCheck = git tag -l $Version
if (-not $tagCheck) {
    git tag $Version -m "Tadado $Version"
    git push origin $Version
}

$changelog = Get-Content CHANGELOG.md -Raw -Encoding UTF8
$body = @{
    tag_name = $Version
    name = "Tadado $Version"
    body = $changelog
    draft = $false
    prerelease = $false
} | ConvertTo-Json

$release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases" `
    -Method Post -Headers $Headers -Body $body -ContentType "application/json"
$uploadUrl = $release.upload_url -replace '\{.*\}', ''
Write-Host "  Release created: $($release.html_url)" -ForegroundColor Green

# ── Step 5: 上传产物 ──
Write-Host "`n[5/5] 上传产物 ..." -ForegroundColor Cyan
$assets = @($zipPath)
if ($setupExe) { $assets += $setupExe.FullName }

foreach ($file in $assets) {
    $name = Split-Path $file -Leaf
    Write-Host "  上传: $name ..."
    $contentType = if ($file.EndsWith(".zip")) { "application/zip" } else { "application/vnd.microsoft.portable-executable" }
    Invoke-RestMethod -Uri "${uploadUrl}?name=$name" `
        -Method Post -Headers $Headers `
        -InFile $file `
        -ContentType $contentType
    Write-Host "  OK: $name" -ForegroundColor Green
}

Write-Host "`n=== 发布完成! $($release.html_url) ===" -ForegroundColor Green
