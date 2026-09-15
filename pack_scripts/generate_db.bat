@echo off
if "%~1"=="" (
    echo Usage: generate_db.bat v0.2.1
    exit /b 1
)
set TAG=%1
set VER=%TAG:~1%

cd /d "%~dp0.."

:: 0. Ensure project venv is fully synced
uv sync --link-mode=copy
if %ERRORLEVEL% neq 0 (
    echo ERROR: uv sync --link-mode=copy failed.
    exit /b 1
)

:: 1. Update __version__ in src/_version_data.py
uv run python pack_scripts/update_version.py %VER%
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to update version.
    exit /b 1
)

:: 2. Extract release highlights from CHANGELOG.md into _version_data.py (replaces entire block)
uv run python scripts/update_highlights.py %VER%
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to extract highlights from CHANGELOG.md for %VER%
    echo   Make sure the version entry exists in CHANGELOG.md
    exit /b 1
)
echo [OK] Highlights synced from CHANGELOG.md

:: 3. Backup dev DB to pack_scripts\.db_backup\, generate clean package DB
set DB_BACKUP=pack_scripts\.db_backup
if not exist "%DB_BACKUP%" mkdir "%DB_BACKUP%"
if exist resources\tadado.data (
    move resources\tadado.data "%DB_BACKUP%\tadado.data" >nul
    echo [OK] Dev DB backed up to %DB_BACKUP%\tadado.data
)
if exist resources\config.json (
    move resources\config.json "%DB_BACKUP%\config.json" >nul
    echo [OK] Dev config backed up to %DB_BACKUP%\config.json
)

uv run python scripts/create_package_db.py
if %ERRORLEVEL% neq 0 (
    echo ERROR: Package DB generation failed.
    if exist "%DB_BACKUP%\tadado.data" (
        move /y "%DB_BACKUP%\tadado.data" resources\tadado.data >nul
    )
    if exist "%DB_BACKUP%\config.json" (
        move /y "%DB_BACKUP%\config.json" resources\config.json >nul
    )
    rmdir /s /q "%DB_BACKUP%" 2>nul
    pause
    exit /b 1
)
echo [OK] Package DB ready: resources\tadado.data
echo   After release, restore dev DB: pack_scripts\restore_db.bat
