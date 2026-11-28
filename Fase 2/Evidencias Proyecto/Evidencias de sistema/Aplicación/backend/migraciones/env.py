"""
Entorno de Alembic para LogiSLA.

Usa la misma URL que la aplicación (DATABASE_URL, ver app/config.py) y los
modelos de app/models.py como referencia para --autogenerate. Funciona con
PostgreSQL y con SQLite (en SQLite las alteraciones de tablas se hacen en
modo "batch", porque SQLite no soporta ALTER TABLE completo).
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app import models  # noqa: F401  (registra las tablas en Base.metadata)
from app.config import URL_BASE_DATOS
from app.database import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Una URL pasada por código (scripts/migrar.py o pruebas) tiene prioridad.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", URL_BASE_DATOS.replace("%", "%%"))

target_metadata = Base.metadata


def _es_sqlite() -> bool:
    """True si la base configurada es SQLite (requiere modo batch para alterar tablas)."""
    return config.get_main_option("sqlalchemy.url", "").startswith("sqlite")


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse (alembic upgrade head --sql)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_es_sqlite(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica las migraciones conectándose a la base de datos (uso normal)."""
    conectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with conectable.connect() as conexion:
        context.configure(
            connection=conexion,
            target_metadata=target_metadata,
            render_as_batch=_es_sqlite(),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
