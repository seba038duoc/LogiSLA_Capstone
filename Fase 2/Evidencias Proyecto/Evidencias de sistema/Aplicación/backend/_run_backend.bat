@echo off
cd /d "%~dp0"
title LogiSLA - Backend
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] No existe el entorno de Python ^(.venv^). Ejecuta primero iniciar.bat.
    pause
    exit /b 1
)
set DATABASE_URL=sqlite:///./logisla.db
set "PYTHONPATH=%~dp0"
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload
echo.
echo El backend se detuvo. Si hubo un error, aparece arriba.
pause
