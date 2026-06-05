@echo off
echo === DeskTodoSeq Nuitka Build ===

:: Clean old build artifacts
if exist dist\main.dist rmdir /s /q dist\main.dist
if exist dist\main.build rmdir /s /q dist\main.build

:: Backup dev database files so the release ships clean
set DB_BACKUP=%TEMP%\desktodoseq_db_backup
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
    :: Restore dev DB before exiting
    if exist "%DB_BACKUP%\desktodoseq.data" (
        copy "%DB_BACKUP%\desktodoseq.data" resources\desktodoseq.data >nul
    )
    if exist "%DB_BACKUP%\tasks.db" (
        copy "%DB_BACKUP%\tasks.db" resources\tasks.db >nul
    )
    rmdir /s /q "%DB_BACKUP%"
    exit /b 1
)

:: Compile with Nuitka
uv run python -m nuitka --standalone ^
    --windows-console-mode=disable ^
    --enable-plugin=pyside6 ^
    --include-data-dir=resources=resources ^
    --output-dir=dist ^
    --output-filename=DeskTodoSeq.exe ^
    --windows-icon-from-ico=resources/icons/app.ico ^
    --assume-yes-for-downloads ^
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

echo === Build complete: dist/main.dist/ ===
pause
