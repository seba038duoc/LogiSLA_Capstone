"""
Prueba del patrón de orígenes permitidos (ALLOWED_ORIGIN_REGEX), que se usa
en la nube para autorizar el dominio del frontend.
"""

import os
import subprocess
import sys
from pathlib import Path

CARPETA_BACKEND = Path(__file__).resolve().parent.parent

CODIGO = """
from fastapi.testclient import TestClient
from app.main import app

cliente = TestClient(app)
for origen in ("https://logisla-frontend.onrender.com", "https://otro-sitio.com"):
    r = cliente.get("/health", headers={"Origin": origen})
    print(origen, r.headers.get("access-control-allow-origin"))
"""


def test_patron_de_origenes_autoriza_solo_al_frontend():
    entorno = dict(os.environ)
    entorno["ALLOWED_ORIGIN_REGEX"] = r"https://logisla-frontend[a-z0-9-]*\.onrender\.com"
    entorno["DATABASE_URL"] = "sqlite://"
    # Proceso aparte: la configuración de CORS se lee al importar app.main.
    salida = subprocess.run(
        [sys.executable, "-c", CODIGO],
        cwd=CARPETA_BACKEND,
        env=entorno,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "https://logisla-frontend.onrender.com https://logisla-frontend.onrender.com" in salida
    assert "https://otro-sitio.com None" in salida
