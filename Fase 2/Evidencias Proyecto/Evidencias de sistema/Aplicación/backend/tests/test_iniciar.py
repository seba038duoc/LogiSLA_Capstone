"""
Pruebas del lanzador iniciar.py (el que ejecuta iniciar.bat): las funciones
que deciden la base de datos, los puertos y la configuración, sin encender
servidores de verdad.
"""

import importlib.util
import json
import socket
import subprocess
from pathlib import Path

import pytest

RUTA_INICIAR = Path(__file__).resolve().parents[2] / "iniciar.py"


@pytest.fixture()
def iniciar(monkeypatch, tmp_path):
    """El módulo iniciar.py, con sus carpetas apuntando a una carpeta temporal."""
    especificacion = importlib.util.spec_from_file_location("iniciar", RUTA_INICIAR)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend").mkdir()
    monkeypatch.setattr(modulo, "RAIZ", tmp_path)
    monkeypatch.setattr(modulo, "BACKEND", tmp_path / "backend")
    monkeypatch.setattr(modulo, "FRONTEND", tmp_path / "frontend")
    monkeypatch.setattr(modulo, "CARPETA_POSTGRES", tmp_path / "LogiSLA")
    monkeypatch.delenv("LOGISLA_DATABASE_URL", raising=False)
    return modulo


def test_revisar_carpeta_detecta_un_proyecto_incompleto(iniciar, tmp_path):
    with pytest.raises(iniciar.ErrorArranque, match="no es el proyecto LogiSLA completo"):
        iniciar.revisar_carpeta()

    (tmp_path / "backend" / "app").mkdir()
    (tmp_path / "backend" / "app" / "main.py").write_text("")
    (tmp_path / "backend" / "requirements.txt").write_text("")
    (tmp_path / "frontend" / "package.json").write_text("{}")
    iniciar.revisar_carpeta()  # completo: no reclama


def test_huella_cambia_solo_si_cambian_las_dependencias(iniciar, tmp_path):
    requisitos = tmp_path / "requirements.txt"
    requisitos.write_text("fastapi\n")
    primera = iniciar.huella(requisitos, tmp_path / "no-existe.txt")
    assert iniciar.huella(requisitos) == primera
    requisitos.write_text("fastapi\npandas\n")
    assert iniciar.huella(requisitos) != primera


def test_puerto_libre_usa_el_preferido_o_busca_otro(iniciar):
    with socket.socket() as libre:
        libre.bind(("127.0.0.1", 0))
        puerto = libre.getsockname()[1]
    assert iniciar.puerto_libre(puerto) == puerto

    with socket.socket() as ocupado:
        ocupado.bind(("127.0.0.1", 0))
        ocupado.listen()
        puerto_ocupado = ocupado.getsockname()[1]
        otro = iniciar.puerto_libre(puerto_ocupado)
    assert otro != puerto_ocupado and otro > 0


def test_url_configurada_lee_backend_env(iniciar, tmp_path, monkeypatch):
    env = tmp_path / "backend" / ".env"
    assert iniciar.url_configurada() is None

    env.write_text("# DATABASE_URL=comentada\nGEMINI_API_KEY=x\n", encoding="utf-8")
    assert iniciar.url_configurada() is None  # una línea comentada no cuenta

    env.write_text(
        '﻿DATABASE_URL="postgresql+psycopg2://u:c@localhost:5432/logisla"\n', encoding="utf-8"
    )
    assert iniciar.url_configurada() == "postgresql+psycopg2://u:c@localhost:5432/logisla"

    # la variable de entorno tiene prioridad sobre el archivo
    monkeypatch.setenv("LOGISLA_DATABASE_URL", "sqlite:///otra.db")
    assert iniciar.url_configurada() == "sqlite:///otra.db"


def test_describir_base_no_muestra_la_contrasena(iniciar):
    texto = iniciar.describir_base("postgresql+psycopg2://logisla:secreta@127.0.0.1:5433/logisla")
    assert texto == "PostgreSQL (127.0.0.1:5433/logisla)"
    assert "secreta" not in texto
    assert iniciar.describir_base("sqlite:///./logisla.db").startswith("SQLite")


def test_elegir_base_en_modo_emergencia_usa_sqlite(iniciar):
    url, descripcion, postgres = iniciar.elegir_base(sqlite_forzado=True)
    assert url == iniciar.SQLITE
    assert "emergencia" in descripcion
    assert postgres is None


def test_buscar_postgres_encuentra_la_carpeta_extra_del_zip(iniciar, tmp_path, monkeypatch):
    # "Extraer todo" de Windows crea una carpeta con el nombre del zip
    binarios = tmp_path / "LogiSLA" / "postgresql-16.16-1-windows-x64-binaries" / "pgsql" / "bin"
    binarios.mkdir(parents=True)
    for programa in ("pg_ctl", "initdb", "pg_ctl.exe", "initdb.exe"):
        (binarios / programa).write_text("")
    assert iniciar.buscar_postgres() == binarios


def test_version_de_postgres_se_lee_de_pg_ctl(iniciar, monkeypatch):
    salida = subprocess.CompletedProcess([], 0, stdout="pg_ctl (PostgreSQL) 16.16\n", stderr="")
    monkeypatch.setattr(iniciar.subprocess, "run", lambda *a, **k: salida)
    assert iniciar.PostgresIntegrado(Path("bin")).version() == "16.16"


def test_numero_de_version_para_elegir_el_postgres_mas_nuevo(iniciar):
    assert iniciar._numero_version(Path("PostgreSQL/16/bin")) == 16.0
    assert iniciar._numero_version(Path("PostgreSQL/sin-numero/bin")) == 0.0


def test_entorno_del_backend(iniciar, tmp_path):
    env = iniciar.entorno_backend(["http://localhost:3000", "http://127.0.0.1:3000"], "sqlite://")
    assert env["DATABASE_URL"] == "sqlite://"
    assert env["ALLOWED_ORIGINS"] == "http://localhost:3000,http://127.0.0.1:3000"
    assert env["PYTHONPATH"] == str(tmp_path / "backend")
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_escribir_env_local_conserva_las_otras_variables(iniciar, tmp_path):
    archivo = tmp_path / "frontend" / ".env.local"
    archivo.write_text("OTRA=1\nNEXT_PUBLIC_API_URL=http://viejo:8000\n", encoding="utf-8")
    iniciar.escribir_env_local("http://127.0.0.1:8123")
    assert (
        archivo.read_text(encoding="utf-8") == "OTRA=1\nNEXT_PUBLIC_API_URL=http://127.0.0.1:8123\n"
    )


class _Respuesta:
    """Respuesta HTTP simulada para estado_ia()."""

    def __init__(self, datos):
        self.datos = json.dumps(datos).encode()

    def read(self):
        return self.datos

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_estado_ia_resume_los_proveedores(iniciar, monkeypatch):
    datos = {
        "configurada": True,
        "proveedores": [
            {"nombre": "Gemini", "papel": "principal", "configurado": True},
            {"nombre": "Claude", "papel": "respaldo", "configurado": False},
        ],
    }
    monkeypatch.setattr(iniciar.urllib.request, "urlopen", lambda *a, **k: _Respuesta(datos))
    assert iniciar.estado_ia("http://x") == "Gemini (principal) activa, Claude (respaldo) sin clave"

    monkeypatch.setattr(
        iniciar.urllib.request, "urlopen", lambda *a, **k: _Respuesta({"configurada": False})
    )
    assert "plantilla de respaldo" in iniciar.estado_ia("http://x")

    def sin_backend(*args, **kwargs):
        raise OSError("apagado")

    monkeypatch.setattr(iniciar.urllib.request, "urlopen", sin_backend)
    assert iniciar.estado_ia("http://x") == "no se pudo consultar"
