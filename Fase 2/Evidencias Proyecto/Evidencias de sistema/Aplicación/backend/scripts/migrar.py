"""
Deja la base de datos con el esquema al día usando las migraciones de Alembic.

Lo ejecuta iniciar.bat antes de levantar el backend. También se puede correr
a mano desde la carpeta backend:
    .venv\\Scripts\\python.exe scripts\\migrar.py

Funciona con la base indicada en DATABASE_URL (SQLite o PostgreSQL). Si la
base ya tenía las tablas porque se creó antes de usar Alembic (versiones
anteriores de LogiSLA), la marca como migrada en vez de intentar crearlas
de nuevo, sin tocar los datos.
"""

import sys
from pathlib import Path

CARPETA_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CARPETA_BACKEND))  # para poder importar app/

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, inspect  # noqa: E402

from app.config import URL_BASE_DATOS  # noqa: E402

# Versión que corresponde al esquema creado antes de usar Alembic.
VERSION_INICIAL = "0001"


def configuracion_alembic(url: str) -> Config:
    """Configuración de Alembic apuntando a la base indicada."""
    config = Config(str(CARPETA_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(CARPETA_BACKEND / "migraciones"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def migrar(url: str = URL_BASE_DATOS) -> str:
    """Aplica las migraciones pendientes y devuelve una descripción de lo que hizo."""
    config = configuracion_alembic(url)
    motor = create_engine(url)
    try:
        tablas = set(inspect(motor).get_table_names())
    finally:
        motor.dispose()

    if "alembic_version" not in tablas and "empresas" in tablas:
        # Una base creada antes de usar Alembic tiene el esquema de la
        # versión 0001: se registra como tal y después se aplican las
        # migraciones posteriores (las columnas nuevas), sin tocar los datos.
        command.stamp(config, VERSION_INICIAL)
        command.upgrade(config, "head")
        return "La base ya tenía las tablas: se registró como migrada y se actualizó."
    command.upgrade(config, "head")
    return "Esquema al día (migraciones de Alembic aplicadas)."


if __name__ == "__main__":
    try:
        print(migrar())
    except Exception as exc:  # mensaje corto y claro para la ventana de iniciar.bat
        primera_linea = (str(exc).strip().splitlines() or [""])[0]
        print(f"ERROR: {type(exc).__name__}: {primera_linea}")
        sys.exit(1)
