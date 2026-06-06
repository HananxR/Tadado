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
if exist resources\desktodoseq.data (
    copy resources\desktodoseq.data "%DB_BACKUP%\desktodoseq.data" >nul
    del resources\desktodoseq.data
    set /a BACKUP_COUNT+=1
)
if exist resources\tasks.db (
    copy resources\tasks.db "%DB_BACKUP%\tasks.db" >nul
    del resources\tasks.db
    set /a BACKUP_COUNT+=1
)

:: Generate package database with pre-seeded demo data
echo Generating package database...
uv run python scripts/create_package_db.py
if %ERRORLEVEL% neq 0 (
    echo ERROR: Package database generation failed.
    if exist "%DB_BACKUP%\desktodoseq.data" (
        copy "%DB_BACKUP%\desktodoseq.data" resources\desktodoseq.data >nul
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
    --clean ^
    main.py

:: Remove package database before restoring dev DB
if exist resources\desktodoseq.data del resources\desktodoseq.data

:: Restore dev database files
if exist "%DB_BACKUP%\desktodoseq.data" (
    copy "%DB_BACKUP%\desktodoseq.data" resources\desktodoseq.data >nul
)
if exist "%DB_BACKUP%\tasks.db" (
    copy "%DB_BACKUP%\tasks.db" resources\tasks.db >nul
)
rmdir /s /q "%DB_BACKUP%"

echo === Build complete: dist/Tadado/ ===
pause
