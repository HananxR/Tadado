@echo off
cd /d "%~dp0.."
echo === Tadado PyInstaller Build ===

:: Clean old build artifacts
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

:: Backup dev database files so the release ships clean
set DB_BACKUP=%TEMP%\tadado_db_backup
if not exist "%DB_BACKUP%" mkdir "%DB_BACKUP%"
set BACKUP_COUNT=0
if exist resources\tadado.data (
    copy resources\tadado.data "%DB_BACKUP%\tadado.data" >nul
    del resources\tadado.data
    set /a BACKUP_COUNT+=1
)
if exist resources\tasks.db (
    copy resources\tasks.db "%DB_BACKUP%\tasks.db" >nul
    del resources\tasks.db
    set /a BACKUP_COUNT+=1
)
if exist resources\config.json (
    copy resources\config.json "%DB_BACKUP%\config.json" >nul
    set /a BACKUP_COUNT+=1
)

:: Generate package database with pre-seeded demo data
echo Generating package database...
uv run python scripts/create_package_db.py
if %ERRORLEVEL% neq 0 (
    echo ERROR: Package database generation failed.
    if exist "%DB_BACKUP%\tadado.data" (
        copy "%DB_BACKUP%\tadado.data" resources\tadado.data >nul
    )
    if exist "%DB_BACKUP%\tasks.db" (
        copy "%DB_BACKUP%\tasks.db" resources\tasks.db >nul
    )
    rmdir /s /q "%DB_BACKUP%"
    exit /b 1
)

:: 同步 CHANGELOG 副本到 resources（打包内版本记录页面用）
copy /Y CHANGELOG.md resources\help\CHANGELOG.md >nul

:: 重写双 exe spec（spec 为 gitignore 文件，防止被命令行构建覆盖回单 exe）
uv run python scripts\write_dual_spec.py

:: Build with PyInstaller (spec-driven: Tadado.exe + tadado-cli.exe in one bundle)
uv run pyinstaller Tadado.spec --clean

:: Remove package database before restoring dev DB
if exist resources\tadado.data del resources\tadado.data
if exist resources\config.json del resources\config.json

:: Restore dev database files
if exist "%DB_BACKUP%\tadado.data" (
    copy "%DB_BACKUP%\tadado.data" resources\tadado.data >nul
)
if exist "%DB_BACKUP%\tasks.db" (
    copy "%DB_BACKUP%\tasks.db" resources\tasks.db >nul
)
if exist "%DB_BACKUP%\config.json" (
    copy "%DB_BACKUP%\config.json" resources\config.json >nul
)
rmdir /s /q "%DB_BACKUP%"

echo === Build complete: dist/Tadado/ ===
pause
