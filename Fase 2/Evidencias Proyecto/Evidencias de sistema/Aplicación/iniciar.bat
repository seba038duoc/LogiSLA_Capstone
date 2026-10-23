@echo off
setlocal
cd /d "%~dp0"
set "TRACE=%~dp0debug_trace.txt"
echo ===== nueva corrida %DATE% %TIME% ===== > "%TRACE%"

echo ============================================
echo   LogiSLA - levantando backend + frontend
echo ============================================
echo.
echo Requisitos: Python 3.10 a 3.14 (version estable) y Node.js 18+ instalados en Windows,
echo con la casilla "Add to PATH" marcada durante la instalacion.
echo.

REM --- Elegir un Python ESTABLE (3.10 a 3.14) ---
REM Con versiones alfa/beta (por ejemplo 3.15.0a3) pandas y pydantic no
REM tienen instaladores listos: pip intenta compilarlos y se queda pegado.
set "PY_CMD="
for %%V in (3.13 3.12 3.14 3.11 3.10) do (
    if not defined PY_CMD (
        py -%%V -c "import sys" >nul 2>nul && set "PY_CMD=py -%%V"
    )
)
if defined PY_CMD goto py_listo
python -c "import sys; v=sys.version_info; sys.exit(0 if v.releaselevel=='final' and (3,10)<=v[:2]<=(3,14) else 1)" >nul 2>nul
if not errorlevel 1 set "PY_CMD=python"
if defined PY_CMD goto py_listo

echo [ERROR] No se encontro una version ESTABLE de Python entre 3.10 y 3.14.
echo Versiones de Python instaladas en este equipo:
py -0 2>nul
python --version 2>nul
echo.
echo Instala Python 3.13 desde https://www.python.org/downloads/
echo ^(marca "Add python.exe to PATH"^) y vuelve a ejecutar iniciar.bat.
echo Las versiones alfa o beta ^(como 3.15.0a3^) NO sirven.
echo.
pause
exit /b 1

:py_listo
echo Usando: %PY_CMD%
%PY_CMD% --version
echo.

where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] No se encontro "node" en el PATH de Windows.
    echo Instalalo desde https://nodejs.org/ ^(version LTS^).
    echo.
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] No se encontro "npm" en el PATH de Windows ^(viene con Node.js^).
    echo Reinstala Node.js desde https://nodejs.org/ ^(version LTS^).
    echo.
    pause
    exit /b 1
)

echo TRACE: checks de python/node/npm OK >> "%TRACE%"

REM --- Backend ---
cd backend
echo TRACE: entre a backend >> "%TRACE%"

REM Si ya existe un .venv creado con una version no soportada, se rehace.
if not exist .venv\Scripts\python.exe goto crear_venv
.venv\Scripts\python.exe -c "import sys; v=sys.version_info; sys.exit(0 if v.releaselevel=='final' and (3,10)<=v[:2]<=(3,14) else 1)" >nul 2>nul
if not errorlevel 1 goto venv_listo
echo El entorno virtual existente usa una version de Python no soportada. Se vuelve a crear...
rmdir /s /q .venv

:crear_venv
echo Creando entorno virtual de Python...
%PY_CMD% -m venv .venv

:venv_listo

if not exist .venv\Scripts\python.exe (
    echo [ERROR] No se pudo crear el entorno virtual ^(.venv^).
    echo Revisa que Python este bien instalado y volve a intentar.
    echo.
    pause
    exit /b 1
)

set "VENV_PY=%~dp0backend\.venv\Scripts\python.exe"

echo Instalando dependencias del backend (puede tardar un par de minutos la primera vez)...
echo Si algo falla, el detalle queda guardado en backend\install.log
"%VENV_PY%" -m pip install -r requirements.txt > install.log 2>&1
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias del backend.
    echo Abri el archivo backend\install.log para ver el detalle,
    echo o pegaselo a Claude para que te ayude a interpretarlo.
    echo.
    pause
    exit /b 1
)
echo Listo.
echo TRACE: pip install OK >> "%TRACE%"

set DATABASE_URL=sqlite:///./logisla.db
set "PYTHONPATH=%~dp0backend"

if exist company_id.txt (
    for %%A in (company_id.txt) do if %%~zA==0 del company_id.txt
)
if not exist company_id.txt (
    echo Creando empresa de prueba...
    "%VENV_PY%" scripts\seed_pilot_company.py "Retail Piloto SpA" "76.987.654-3" > company_id.txt
)
for %%A in (company_id.txt) do if %%~zA==0 (
    echo [ATENCION] No se pudo crear la empresa de prueba automaticamente.
    echo Podes intentarlo a mano mas tarde, parado en la carpeta backend:
    echo   set DATABASE_URL=sqlite:///./logisla.db
    echo   set PYTHONPATH=%%cd%%
    echo   .venv\Scripts\python.exe scripts\seed_pilot_company.py "Retail Piloto SpA" "76.987.654-3"
    echo.
)
echo TRACE: company_id OK >> "%TRACE%"

REM Reglas SLA de los transportistas (idempotente). Sin esto el motor de
REM auditoria no tiene plazos contra los cuales comparar y todas las
REM guias quedan como "sin regla SLA".
echo Cargando transportistas y reglas SLA de prueba...
"%VENV_PY%" scripts\seed_carriers_and_rules.py > seed_reglas.log 2>&1
if errorlevel 1 (
    echo [ATENCION] No se pudieron cargar las reglas SLA. Detalle en backend\seed_reglas.log
    echo.
)
echo TRACE: reglas SLA OK >> "%TRACE%"

echo Levantando el backend en una ventana nueva (puerto 8000)...
echo TRACE: por lanzar backend >> "%TRACE%"
start "LogiSLA - Backend" cmd /k ""%~dp0backend\_run_backend.bat""
echo TRACE: backend lanzado >> "%TRACE%"

cd ..
echo TRACE: volvi a la raiz >> "%TRACE%"

REM --- Frontend ---
cd frontend
echo TRACE: entre a frontend >> "%TRACE%"

if not exist node_modules (
    echo TRACE: node_modules no existe, voy a instalar >> "%TRACE%"
    echo Instalando dependencias del frontend (puede tardar unos minutos la primera vez)...
    echo Si algo falla, el detalle queda guardado en frontend\install.log
    call npm install > install.log 2>&1
    echo TRACE: npm install termino con errorlevel %errorlevel% >> "%TRACE%"
    if errorlevel 1 (
        echo [ERROR] Fallo "npm install".
        echo Abri el archivo frontend\install.log para ver el detalle,
        echo o pegaselo a Claude para que te ayude a interpretarlo.
        echo.
        pause
        exit /b 1
    )
    echo Listo.
)
if not exist .env.local (
    copy .env.local.example .env.local >nul
)
echo TRACE: por lanzar frontend >> "%TRACE%"

echo Levantando el frontend en una ventana nueva (puerto 3000)...
start "LogiSLA - Frontend" cmd /k ""%~dp0frontend\_run_frontend.bat""
echo TRACE: frontend lanzado >> "%TRACE%"

cd ..

echo.
echo Esperando a que ambos servidores arranquen...
timeout /t 12 /nobreak >nul

echo Abriendo el navegador...
start http://localhost:3000

echo.
echo ============================================
echo   LogiSLA esta listo en http://localhost:3000
echo   La empresa de prueba ya aparece elegida en la pagina.
echo ============================================
echo.
echo Dejaste dos ventanas nuevas abiertas (Backend y Frontend) - no las cierres
echo mientras uses la pagina. Cuando termines, simplemente cerralas.
echo.
echo TRACE: fin del script, esperando pause >> "%TRACE%"
pause
