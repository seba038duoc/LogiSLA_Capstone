"""Schemas Pydantic: forma de las respuestas de la API (no de los modelos de BD)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class RespuestaCarga(BaseModel):
    """Respuesta de POST /api/v1/lotes-auditoria/cargar (ingesta, Sprint 1)."""
    lote_id: str
    nombre_archivo: str
    estado: str
    total_filas: int
    mapeo_columnas: dict
    advertencias_ambiguas: dict[str, list[str]]
    mensaje: str


class LoteAuditoriaSalida(BaseModel):
    """Respuesta de GET /api/v1/lotes-auditoria/{lote_id}."""
    id: str
    nombre_archivo: str
    estado: str
    total_filas: int
    fecha_creacion: datetime
    fecha_procesado: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ResultadoAuditoria(BaseModel):
    """Respuesta de POST /api/v1/lotes-auditoria/{lote_id}/auditar (Sprint 2)."""
    lote_id: str
    estado: str
    total_envios: int
    envios_auditados: int
    envios_incumplidos: int
    envios_cumplidos: int
    omitidos_sin_regla: int
    omitidos_sin_fecha_entrega: int
    monto_multa_total: float
    mensaje: str


# ---------------------------------------------------------------------------
# Consultas para el frontend (panel de lotes, detalle y tabla de guías)
# ---------------------------------------------------------------------------

class EmpresaSalida(BaseModel):
    """Item de GET /api/v1/empresas (selector de empresa del frontend)."""
    id: str
    nombre: str
    rut: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class Conteos(BaseModel):
    """
    Cómo se reparten las guías de un lote (o de un transportista dentro
    del lote). Cada guía cae en exactamente una categoría, así que
    cumplidos + incumplidos + en_transito + sin_regla + pendientes == total.
    """
    total: int = 0
    cumplidos: int = 0
    incumplidos: int = 0
    en_transito: int = 0   # sin fecha de entrega todavía
    sin_regla: int = 0     # entregada, pero su transportista no tiene regla SLA activa
    pendientes: int = 0    # el lote aún no pasó por el motor de auditoría
    monto_multa_total: float = 0.0


class LoteResumenSalida(BaseModel):
    """Item de GET /api/v1/lotes-auditoria?empresa_id=..."""
    id: str
    nombre_archivo: str
    estado: str
    total_filas: int
    fecha_creacion: datetime
    fecha_procesado: Optional[datetime] = None
    conteos: Conteos


class FilaTransportista(BaseModel):
    nombre: str
    horas_habiles_maximas: Optional[int] = None       # None = sin regla SLA activa
    multa_por_incumplimiento: Optional[float] = None
    conteos: Conteos


class LoteDetalleSalida(LoteResumenSalida):
    """Respuesta de GET /api/v1/lotes-auditoria/{lote_id}/resumen."""
    por_transportista: list[FilaTransportista]


class EnvioSalida(BaseModel):
    """Item de GET /api/v1/lotes-auditoria/{lote_id}/envios."""
    id: str
    numero_guia: str
    transportista: Optional[str] = None
    fecha_despacho: datetime
    fecha_entrega: Optional[datetime] = None
    destino: Optional[str] = None
    valor_declarado: Optional[float] = None
    resultado: str   # CUMPLIDO | INCUMPLIDO | EN_TRANSITO | SIN_REGLA | PENDIENTE
    horas_atraso: Optional[float] = None
    monto_multa: Optional[float] = None
