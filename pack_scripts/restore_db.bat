@echo off
cd /d "%~dp0.."

set DB_BACKUP=pack_scripts\.db_backup

if not exist "%DB_BACKUP%\tadado.data" (
    echo No dev DB backup found at %DB_BACKUP%\tadado.data
    exit /b 1
)

move /y "%DB_BACKUP%\tadado.data" resources\tadado.data >nul
if exist "%DB_BACKUP%\config.json" (
    move /y "%DB_BACKUP%\config.json" resources\config.json >nul
)
rmdir /s /q "%DB_BACKUP%" 2>nul
echo Dev database restored.
