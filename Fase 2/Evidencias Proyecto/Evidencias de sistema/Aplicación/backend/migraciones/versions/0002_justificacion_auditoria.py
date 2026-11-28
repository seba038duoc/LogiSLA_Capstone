"""Justificación de la auditoría: resultado por guía, fecha límite y fecha de corte.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-15

Agrega lo necesario para que cada guía quede auditada y justificada:
  - envios.resultado: categoría final de la guía (CUMPLIDO, INCUMPLIDO,
    EN_TRANSITO, VENCIDA_SIN_ENTREGA, SIN_REGLA o DATOS_INVALIDOS).
  - envios.fecha_limite: fecha y hora en que vencía el plazo SLA.
  - envios.horas_habiles_transcurridas: horas hábiles desde el despacho
    hasta la entrega (o hasta la fecha de corte, si no hay entrega).
  - envios.observacion: motivo cuando los datos de la guía no permiten
    auditarla (por ejemplo, entrega anterior al despacho).
  - lotes_auditoria.fecha_corte: fecha y hora a la que se hizo la auditoría.

Los lotes que ya estaban auditados reciben su resultado con la misma regla
que se usaba antes; al volver a auditarlos se completa el resto.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Agrega las columnas nuevas y completa el resultado de los lotes ya auditados."""
    with op.batch_alter_table("envios") as tabla:
        tabla.add_column(sa.Column("resultado", sa.String(length=30), nullable=True))
        tabla.add_column(sa.Column("fecha_limite", sa.DateTime(timezone=True), nullable=True))
        tabla.add_column(sa.Column("horas_habiles_transcurridas", sa.Float(), nullable=True))
        tabla.add_column(sa.Column("observacion", sa.Text(), nullable=True))
    with op.batch_alter_table("lotes_auditoria") as tabla:
        tabla.add_column(sa.Column("fecha_corte", sa.DateTime(timezone=True), nullable=True))

    # Mismo criterio que se usaba antes de esta versión.
    op.execute("""
        UPDATE envios SET resultado = CASE
            WHEN fecha_entrega IS NULL THEN 'EN_TRANSITO'
            WHEN incumplio_sla IS TRUE THEN 'INCUMPLIDO'
            WHEN incumplio_sla IS FALSE THEN 'CUMPLIDO'
            ELSE 'SIN_REGLA'
        END
        WHERE lote_auditoria_id IN (
            SELECT id FROM lotes_auditoria WHERE estado = 'COMPLETADO'
        )
        """)


def downgrade() -> None:
    """Quita las columnas agregadas."""
    with op.batch_alter_table("lotes_auditoria") as tabla:
        tabla.drop_column("fecha_corte")
    with op.batch_alter_table("envios") as tabla:
        tabla.drop_column("observacion")
        tabla.drop_column("horas_habiles_transcurridas")
        tabla.drop_column("fecha_limite")
        tabla.drop_column("resultado")
