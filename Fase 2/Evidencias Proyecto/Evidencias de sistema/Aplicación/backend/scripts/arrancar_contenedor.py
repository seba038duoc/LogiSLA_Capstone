"""
Arranque del backend dentro de un contenedor (Docker o Google Cloud Run).

Hace, en orden:
  1. Aplica las migraciones de Alembic (crea o actualiza las tablas).
  2. Si CARGAR_DATOS_PRUEBA=1, carga los transportistas con sus reglas SLA y
     la empresa piloto (son idempotentes: no duplican si ya existen).
  3. Levanta la API con uvicorn en el puerto de la variable PORT (Cloud Run
     la define; en Docker local se usa 8000).

Está en Python y no en un script de shell para que funcione igual aunque Git
en Windows cambie los saltos de línea de los archivos.
"""

import os
import subprocess
import sys
from pathlib import Path

CARPETA_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CARPETA_BACKEND))  # para importar app/ y scripts/

from migrar import migrar  # noqa: E402


def ejecutar_script(*argumentos: str) -> None:
    """Ejecuta un script de backend/scripts y detiene el arranque si falla."""
    entorno = dict(os.environ)
    # Los scripts importan app/: la carpeta backend tiene que estar en PYTHONPATH.
    entorno["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(CARPETA_BACKEND), entorno.get("PYTHONPATH", "")) if p
    )
    subprocess.run([sys.executable, *argumentos], cwd=CARPETA_BACKEND, env=entorno, check=True)


if __name__ == "__main__":
    print(migrar(), flush=True)

    if os.getenv("CARGAR_DATOS_PRUEBA", "0") == "1":
        ejecutar_script("scripts/seed_carriers_and_rules.py")
        ejecutar_script(
            "scripts/seed_pilot_company.py",
            os.getenv("EMPRESA_PILOTO", "Retail Piloto SpA"),
            os.getenv("RUT_EMPRESA_PILOTO", "76.987.654-3"),
        )
        print("Datos de prueba listos.", flush=True)

    puerto = os.getenv("PORT", "8000")
    # exec: uvicorn reemplaza a este proceso y recibe directamente las señales de apagado.
    os.execvp(
        sys.executable,
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", puerto],
    )
