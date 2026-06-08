# Tadado Release Script — local build + upload
# Usage: .\release.ps1 v0.1.3
# Requires: GITHUB_TOKEN env var (Personal Access Token with repo scope)
param(
    [Parameter(Mandatory=$true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"
$Repo = "HananxR/Tadado"
$Tag = $Version

if ($Tag -notmatch '^v\d+\.\d+\.\d+$') {
    Write-Error "版本号格式错误，示例: v0.1.3"
    exit 1
}

$VerNum = $Tag -replace '^v', ''

# --- Auth ---
$Token = $env:GITHUB_TOKEN
if (-not $Token) {
    $Token = Read-Host "请输入 GitHub Personal Access Token (repo 权限)"
}
$Headers = @{
    Authorization = "Bearer $Token"
    Accept        = "application/vnd.github+json"
}

# --- Helper: confirm overwrite ---
function Confirm-Overwrite($thing) {
    $ans = Read-Host "$thing 已存在，[O]覆盖 [S]跳过? (默认: O)"
    if ($ans -eq '' -or $ans -eq 'O' -or $ans -eq 'o') { return 'overwrite' }
    return 'skip'
}

# --- Step 1: Find Inno Setup ---
Write-Host "`n=== Step 1: Find Inno Setup ===" -ForegroundColor Cyan

$Iscc = $null
$IsccPaths = @(
    "C:\Program Files (x86)\Inno Setup 7\ISCC.exe"
    "C:\Program Files\Inno Setup 7\ISCC.exe"
    "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe"
    "${env:ProgramFiles}\Inno Setup 7\ISCC.exe"
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "C:\Program Files\Inno Setup 6\ISCC.exe"
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    (Get-Command iscc.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
)

foreach ($p in $IsccPaths) {
    if ($p -and (Test-Path $p)) {
        $Iscc = $p
        Write-Host "Found: $Iscc" -ForegroundColor Green
        break
    }
}

if (-not $Iscc) {
    Write-Host "Inno Setup 未找到，将跳过 EXE 安装包构建" -ForegroundColor Yellow
    Write-Host "下载安装: https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
}

# --- Step 2: Build ---
Write-Host "`n=== Step 2: Build ===" -ForegroundColor Cyan

if (Test-Path build) { Remove-Item build -Recurse -Force }
if (Test-Path dist)  { Remove-Item dist -Recurse -Force }

if (Test-Path resources\tadado.data) {
    Copy-Item resources\tadado.data $env:TEMP\tadado_data_backup -Force
}

try {
    uv run python scripts/create_package_db.py
    if ($LASTEXITCODE -ne 0) { throw "Package DB generation failed" }

    uv run pyinstaller `
        --noconsole `
        --name=Tadado `
        --add-data="resources;resources" `
        --icon=resources/icons/app.ico `
        --hidden-import=PySide6.QtSvg `
        --clean `
        main.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

    if (Test-Path $env:TEMP\tadado_data_backup) {
        Copy-Item $env:TEMP\tadado_data_backup resources\tadado.data -Force
        Remove-Item $env:TEMP\tadado_data_backup -Force
    }
    if (Test-Path resources\config.json) { Remove-Item resources\config.json -Force }
} catch {
    if (Test-Path $env:TEMP\tadado_data_backup) {
        Copy-Item $env:TEMP\tadado_data_backup resources\tadado.data -Force
    }
    throw
}

Write-Host "Build OK: dist\Tadado\" -ForegroundColor Green

# --- Step 3: Package ---
Write-Host "`n=== Step 3: Package ===" -ForegroundColor Cyan

$PortableZip = "dist\Tadado_${Tag}_portable.zip"
Compress-Archive -Path dist\Tadado\* -DestinationPath $PortableZip -Force
Write-Host "Portable: $PortableZip" -ForegroundColor Green

$InstallerExe = $null
if ($Iscc) {
    (Get-Content installer.iss) -replace '#define MyAppVersion ".*"', "#define MyAppVersion ""$VerNum""" | Set-Content installer.iss
    & $Iscc installer.iss
    if ($LASTEXITCODE -eq 0) {
        $InstallerExe = "dist\Tadado_setup_v${VerNum}.exe"
        Write-Host "Installer: $InstallerExe" -ForegroundColor Green
    } else {
        Write-Host "Inno Setup compile failed" -ForegroundColor Red
    }
}

# --- Step 4: Git tag ---
Write-Host "`n=== Step 4: Git tag & push ===" -ForegroundColor Cyan

$ExistingTag = git tag -l $Tag
$Action = 'push'
if ($ExistingTag) {
    $Action = Confirm-Overwrite "Git tag $Tag"
    if ($Action -eq 'skip') {
        Write-Host "Tag skipped" -ForegroundColor Yellow
    } else {
        git tag -d $Tag
        git push origin --delete $Tag 2>$null
        git tag $Tag
        git push origin $Tag
        Write-Host "Tag $Tag overwritten & pushed" -ForegroundColor Green
    }
} else {
    git tag $Tag
    git push origin $Tag
    Write-Host "Tag $Tag pushed" -ForegroundColor Green
}

# --- Step 5: Release ---
Write-Host "`n=== Step 5: Upload to GitHub ===" -ForegroundColor Cyan

$ExistingRelease = try {
    $r = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/tags/$Tag" -Headers $Headers -ErrorAction Stop
    $r
} catch { $null }

if ($ExistingRelease) {
    $Action = Confirm-Overwrite "GitHub Release $Tag"
    if ($Action -eq 'skip') {
        Write-Host "Release skipped" -ForegroundColor Yellow
        Write-Host "`n=== Done ===" -ForegroundColor Cyan
        Write-Host "Release: $($ExistingRelease.html_url)" -ForegroundColor Magenta
        exit 0
    }
    # Delete existing release
    Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/$($ExistingRelease.id)" -Method Delete -Headers $Headers | Out-Null
    Write-Host "Old release deleted" -ForegroundColor Yellow
}

# Create release
$Body = @{
    tag_name = $Tag
    name     = "Tadado $Tag"
    body     = @"
## 安装方式

- **安装包**：`Tadado_setup_v${VerNum}.exe`，一键安装
- **便携版**：`Tadado_${Tag}_portable.zip`，解压即用

## 系统要求
- Windows 10 / 11
- 无需 Python 环境
"@
    draft    = $false
} | ConvertTo-Json

$Release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases" -Method Post -Headers $Headers -Body $Body
Write-Host "Release created: $($Release.html_url)" -ForegroundColor Green

# Upload
function Upload-Asset($FilePath, $FileName) {
    $Url = "https://uploads.github.com/repos/$Repo/releases/$($Release.id)/assets?name=$FileName"
    $ContentType = if ($FileName.EndsWith('.zip')) { "application/zip" } else { "application/octet-stream" }
    Invoke-RestMethod -Uri $Url -Method Post -Headers $Headers -ContentType $ContentType -InFile $FilePath | Out-Null
    Write-Host "  Uploaded: $FileName" -ForegroundColor Green
}

Upload-Asset $PortableZip (Split-Path $PortableZip -Leaf)
if ($InstallerExe -and (Test-Path $InstallerExe)) {
    Upload-Asset $InstallerExe (Split-Path $InstallerExe -Leaf)
}

Write-Host "`n=== Done ===" -ForegroundColor Cyan
Write-Host "Release: https://github.com/$Repo/releases/tag/$Tag" -ForegroundColor Magenta
