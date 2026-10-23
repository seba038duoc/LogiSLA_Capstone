@echo off
cd /d "%~dp0"
set DATABASE_URL=sqlite:///./logisla.db
set "PYTHONPATH=%~dp0"
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload
