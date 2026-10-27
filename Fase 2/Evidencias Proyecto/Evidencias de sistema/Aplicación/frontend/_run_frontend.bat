@echo off
cd /d "%~dp0"
title LogiSLA - Frontend
if not exist node_modules (
    echo Instalando dependencias del frontend, puede tardar unos minutos...
    call npm install
    if errorlevel 1 (
        echo.
        echo [ERROR] Fallo "npm install". Revisa el mensaje de arriba.
        pause
        exit /b 1
    )
)
if not exist .env.local copy .env.local.example .env.local >nul
call npm run dev
echo.
echo El frontend se detuvo. Si hubo un error, aparece arriba.
pause
