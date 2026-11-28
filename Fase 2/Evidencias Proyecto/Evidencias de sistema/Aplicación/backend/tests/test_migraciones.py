"""
Pruebas de las migraciones de Alembic (HU-21).

Corren sobre SQLite (un archivo temporal) o, si se define TEST_DATABASE_URL,
sobre PostgreSQL, igual que el resto de las pruebas. Revisan que:
  - las migraciones creen exactamente el esquema de app/models.py (si alguien
    cambia un modelo sin crear su migración, esta prueba falla);
  - se puedan revertir;
  - una base creada antes de usar Alembic se registre sin perder datos.
"""

import os
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.database import Base
from app.models import Empresa

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from migrar import configuracion_alembic, migrar  # noqa: E402

TABLAS = {"empresas", "transportistas", "reglas_sla", "lotes_auditoria", "envios"}


@pytest.fixture()
def url_base(tmp_path):
    """URL de una base vacía; al terminar la deja vacía otra vez."""
    url = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'migraciones.db'}"
    _vaciar(url)
    yield url
    _vaciar(url)


def _vaciar(url: str) -> None:
    motor = create_engine(url)
    try:
        Base.metadata.drop_all(bind=motor)
        with motor.begin() as conexion:
            conexion.execute(text("DROP TABLE IF EXISTS alembic_version"))
            if motor.dialect.name == "postgresql":
                conexion.execute(text("DROP TYPE IF EXISTS estadolote"))
    finally:
        motor.dispose()


def _tablas(url: str) -> set[str]:
    motor = create_engine(url)
    try:
        return set(inspect(motor).get_table_names())
    finally:
        motor.dispose()


def test_migraciones_crean_el_esquema_de_los_modelos(url_base):
    command.upgrade(configuracion_alembic(url_base), "head")

    assert TABLAS <= _tablas(url_base)
    motor = create_engine(url_base)
    try:
        with motor.connect() as conexion:
            version = conexion.execute(text("SELECT version_num FROM alembic_version")).scalar()
            # SQLite no tiene tipo UUID y lo informa como NUMERIC: allí se comparan
            # tablas y columnas; los tipos se comparan en PostgreSQL (CI).
            opciones = {"compare_type": motor.dialect.name != "sqlite"}
            contexto = MigrationContext.configure(conexion, opts=opciones)
            diferencias = compare_metadata(contexto, Base.metadata)
    finally:
        motor.dispose()
    assert version == "0002"
    assert diferencias == [], f"Los modelos y las migraciones no coinciden: {diferencias}"


def test_migraciones_se_pueden_revertir(url_base):
    config = configuracion_alembic(url_base)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    assert not (TABLAS & _tablas(url_base))


def test_migrar_registra_una_base_creada_antes_de_alembic(url_base):
    # Una base anterior a Alembic tiene el esquema de la versión 0001 y no
    # tiene la tabla alembic_version.
    command.upgrade(configuracion_alembic(url_base), "0001")
    motor = create_engine(url_base)
    try:
        with motor.begin() as conexion:
            conexion.execute(text("DROP TABLE alembic_version"))
            conexion.execute(
                Empresa.__table__.insert().values(
                    id="00000000-0000-0000-0000-000000000001", nombre="Empresa previa"
                )
            )
    finally:
        motor.dispose()

    mensaje = migrar(url_base)

    assert "registró como migrada" in mensaje
    motor = create_engine(url_base)
    try:
        with motor.connect() as conexion:
            assert (
                conexion.execute(text("SELECT nombre FROM empresas")).scalar() == "Empresa previa"
            )
            assert (
                conexion.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0002"
            )
    finally:
        motor.dispose()


def test_migrar_dos_veces_no_falla(url_base):
    assert "al día" in migrar(url_base)
    assert "al día" in migrar(url_base)
    assert TABLAS <= _tablas(url_base)


def test_migracion_0002_completa_el_resultado_de_lotes_ya_auditados(url_base):
    config = configuracion_alembic(url_base)
    command.upgrade(config, "0001")
    motor = create_engine(url_base)
    try:
        with motor.begin() as conexion:
            conexion.execute(
                text(
                    "INSERT INTO empresas (id, nombre)"
                    " VALUES ('00000000-0000-0000-0000-0000000000e1', 'Empresa')"
                )
            )
            conexion.execute(
                text(
                    "INSERT INTO lotes_auditoria (id, empresa_id, nombre_archivo, estado,"
                    " total_filas) VALUES ('00000000-0000-0000-0000-0000000000a1',"
                    " '00000000-0000-0000-0000-0000000000e1', 'a.csv', 'COMPLETADO', 3)"
                )
            )
            for guia, entrega, incumplio in (
                ("1", "2025-11-12 18:00", True),
                ("2", "2025-11-10 14:00", False),
                ("3", None, None),
            ):
                conexion.execute(
                    text(
                        "INSERT INTO envios (id, lote_auditoria_id, numero_guia, fecha_despacho,"
                        " fecha_entrega, incumplio_sla) VALUES"
                        " (:id, '00000000-0000-0000-0000-0000000000a1', :guia,"
                        " '2025-11-10 09:00', :entrega, :incumplio)"
                    ),
                    {
                        "id": f"00000000-0000-0000-0000-00000000000{guia}",
                        "guia": f"G{guia}",
                        "entrega": entrega,
                        "incumplio": incumplio,
                    },
                )
    finally:
        motor.dispose()

    command.upgrade(config, "head")

    motor = create_engine(url_base)
    try:
        with motor.connect() as conexion:
            filas = dict(
                conexion.execute(text("SELECT numero_guia, resultado FROM envios")).fetchall()
            )
    finally:
        motor.dispose()
    assert filas == {"G1": "INCUMPLIDO", "G2": "CUMPLIDO", "G3": "EN_TRANSITO"}
