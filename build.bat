@echo off
echo === Tadado PyInstaller Build ===

:: Clean old build artifacts
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist *.spec del *.spec

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

:: Build with PyInstaller
uv run pyinstaller ^
    --noconsole ^
    --name=Tadado ^
    --add-data="resources;resources" ^
    --icon=resources/icons/app.ico ^
    --hidden-import=PySide6.QtSvg ^
    --clean ^
    main.py

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
