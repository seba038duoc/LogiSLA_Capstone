@echo off
setlocal
title LogiSLA
cd /d "%~dp0"

REM Unico punto de entrada: doble clic aqui. Busca un Python estable y le
REM entrega el resto a iniciar.py (instalacion, puertos, backend, frontend y
REM navegador), que deja todo corriendo en ESTA misma ventana.

if not exist "%~dp0iniciar.py" (
    echo [ERROR] Falta iniciar.py junto a este archivo.
    pause
    exit /b 1
)

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
echo.
pause
exit /b 1

:py_listo
%PY_CMD% "%~dp0iniciar.py" %*
if errorlevel 1 (
    echo.
    echo LogiSLA no pudo arrancar. El motivo aparece arriba.
    pause
    exit /b 1
)
