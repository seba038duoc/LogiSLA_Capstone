"""Esquema inicial de LogiSLA: empresas, transportistas, reglas SLA, lotes y envíos.

Revision ID: 0001
Revises:
Create Date: 2026-11-15

Generada con `alembic revision --autogenerate` contra PostgreSQL 16 y
revisada a mano:
  - Las fechas por defecto usan sa.func.now(), que se traduce a now() en
    PostgreSQL y a CURRENT_TIMESTAMP en SQLite (now() no existe en SQLite).
  - downgrade() también borra el tipo enum estadolote de PostgreSQL.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ESTADO_LOTE = sa.Enum("PENDIENTE", "PROCESANDO", "COMPLETADO", "FALLIDO", name="estadolote")


def _fecha_creacion() -> sa.Column:
    """Columna fecha_creacion con la hora del servidor por defecto (se repite en varias tablas)."""
    return sa.Column(
        "fecha_creacion", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
    )


def upgrade() -> None:
    """Crea las cinco tablas de LogiSLA con sus claves e índices."""
    op.create_table(
        "empresas",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("rut", sa.String(length=20), nullable=True),
        _fecha_creacion(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rut"),
    )
    op.create_table(
        "transportistas",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        _fecha_creacion(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nombre"),
    )
    op.create_table(
        "lotes_auditoria",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("empresa_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("nombre_archivo", sa.String(length=500), nullable=False),
        sa.Column("estado", ESTADO_LOTE, nullable=False),
        sa.Column("total_filas", sa.Integer(), nullable=False),
        sa.Column("mapeo_columnas", sa.JSON(), nullable=True),
        sa.Column("advertencias_sin_mapear", sa.JSON(), nullable=True),
        sa.Column("mensaje_error", sa.Text(), nullable=True),
        _fecha_creacion(),
        sa.Column("fecha_procesado", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "reglas_sla",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("transportista_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("tipo_servicio", sa.String(length=100), nullable=True),
        sa.Column("horas_habiles_maximas", sa.Integer(), nullable=False),
        sa.Column("multa_por_incumplimiento", sa.Float(), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=True),
        _fecha_creacion(),
        sa.ForeignKeyConstraint(["transportista_id"], ["transportistas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "envios",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("lote_auditoria_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("transportista_id", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("nombre_transportista_original", sa.String(length=255), nullable=True),
        sa.Column("numero_guia", sa.String(length=100), nullable=False),
        sa.Column("fecha_despacho", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fecha_entrega", sa.DateTime(timezone=True), nullable=True),
        sa.Column("destino", sa.String(length=255), nullable=True),
        sa.Column("valor_declarado", sa.Float(), nullable=True),
        sa.Column("incumplio_sla", sa.Boolean(), nullable=True),
        sa.Column("horas_atraso", sa.Float(), nullable=True),
        sa.Column("monto_multa", sa.Float(), nullable=True),
        _fecha_creacion(),
        sa.ForeignKeyConstraint(["lote_auditoria_id"], ["lotes_auditoria.id"]),
        sa.ForeignKeyConstraint(["transportista_id"], ["transportistas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Elimina las tablas (en orden inverso por las claves foráneas) y el tipo enumerado."""
    op.drop_table("envios")
    op.drop_table("reglas_sla")
    op.drop_table("lotes_auditoria")
    op.drop_table("transportistas")
    op.drop_table("empresas")
    ESTADO_LOTE.drop(op.get_bind(), checkfirst=True)
