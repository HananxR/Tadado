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

# Validate version format
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
    Accept = "application/vnd.github+json"
}

# --- Step 1: Build ---
Write-Host "`n=== Step 1: Build ===" -ForegroundColor Cyan

# Backup DB, generate package DB
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

    # Restore dev DB
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

# --- Step 2: Package ---
Write-Host "`n=== Step 2: Package ===" -ForegroundColor Cyan

# Portable ZIP
$PortableZip = "dist\Tadado_${Tag}_portable.zip"
Compress-Archive -Path dist\Tadado\* -DestinationPath $PortableZip -Force
Write-Host "Portable: $PortableZip" -ForegroundColor Green

# Inno Setup installer (if ISCC available)
$InstallerExe = $null
$Iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
if (-not $Iscc) {
    $IsccPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $IsccPath) { $Iscc = $IsccPath }
}

if ($Iscc) {
    (Get-Content installer.iss) -replace '#define MyAppVersion ".*"', "#define MyAppVersion ""$VerNum""" | Set-Content installer.iss
    & $Iscc installer.iss
    if ($LASTEXITCODE -eq 0) {
        $InstallerExe = "dist\Tadado_setup_v${VerNum}.exe"
        Write-Host "Installer: $InstallerExe" -ForegroundColor Green
    }
} else {
    Write-Host "Inno Setup not found, skipping installer" -ForegroundColor Yellow
}

# --- Step 3: Git tag & push ---
Write-Host "`n=== Step 3: Git tag & push ===" -ForegroundColor Cyan

$Existing = git tag -l $Tag
if ($Existing) {
    Write-Host "Tag $Tag already exists, skipping" -ForegroundColor Yellow
} else {
    git tag $Tag
    git push origin $Tag
    Write-Host "Tag $Tag pushed" -ForegroundColor Green
}

# --- Step 4: Create Release & upload ---
Write-Host "`n=== Step 4: Upload to GitHub ===" -ForegroundColor Cyan

$Body = @{
    tag_name = $Tag
    name = "Tadado $Tag"
    body = @"
## 安装方式

- **安装包**：`Tadado_setup_v${VerNum}.exe`，一键安装
- **便携版**：`Tadado_${Tag}_portable.zip`，解压即用

## 系统要求
- Windows 10 / 11
- 无需 Python 环境
"@
    draft = $false
} | ConvertTo-Json

$Release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases" -Method Post -Headers $Headers -Body $Body
Write-Host "Release created: $($Release.html_url)" -ForegroundColor Green

# Upload assets
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

# --- Done ---
Write-Host "`n=== Done ===" -ForegroundColor Cyan
Write-Host "Release: https://github.com/$Repo/releases/tag/$Tag" -ForegroundColor Magenta
