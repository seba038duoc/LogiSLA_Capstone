"""Schemas Pydantic: forma de las respuestas de la API (no de los modelos de BD)."""

from datetime import date, datetime
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
    omitidos_sin_fecha_entrega: int  # en tránsito + vencidas sin entrega
    vencidas_sin_entrega: int = 0  # sin entrega y con el plazo vencido a la fecha de corte
    datos_invalidos: int = 0  # guías con datos que no permiten auditarlas
    monto_multa_total: float
    fecha_corte: Optional[datetime] = None
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
    la suma de todas las categorías (sin contar el monto) es igual a total.
    """

    total: int = 0
    cumplidos: int = 0  # entregadas dentro del plazo
    incumplidos: int = 0  # entregadas fuera del plazo (llevan multa)
    en_transito: int = 0  # sin entrega, pero su plazo aún no vence
    vencidas_sin_entrega: int = 0  # sin entrega y con el plazo vencido (alerta, sin multa)
    sin_regla: int = 0  # su transportista no tiene regla SLA activa
    datos_invalidos: int = 0  # sus datos no permiten auditarlas (ver observación)
    pendientes: int = 0  # el lote aún no pasó por el motor de auditoría
    monto_multa_total: float = 0.0


class LoteResumenSalida(BaseModel):
    """Item de GET /api/v1/lotes-auditoria?empresa_id=..."""

    id: str
    nombre_archivo: str
    estado: str
    total_filas: int
    fecha_creacion: datetime
    fecha_procesado: Optional[datetime] = None
    fecha_corte: Optional[datetime] = None  # momento (hora de Chile) en que se auditó
    conteos: Conteos


class FilaTransportista(BaseModel):
    """Una fila del desglose por transportista: regla SLA y conteos."""

    nombre: str
    horas_habiles_maximas: Optional[int] = None  # None = sin regla SLA activa
    multa_por_incumplimiento: Optional[float] = None
    conteos: Conteos


class Feriado(BaseModel):
    """Un feriado chileno que no se contó como día hábil."""

    fecha: date
    nombre: str


class CriteriosAuditoria(BaseModel):
    """Metodología con que se auditó el lote, para mostrarla y justificar los resultados."""

    jornada: str  # ej. "09:00 a 18:00, de lunes a viernes"
    calendario: str  # origen de los feriados
    despacho_desde: Optional[datetime] = None  # período de despacho del archivo
    despacho_hasta: Optional[datetime] = None
    feriados: list[Feriado]  # feriados en días hábiles dentro del período auditado
    reglas: list[str]  # una línea por criterio de clasificación


class LoteDetalleSalida(LoteResumenSalida):
    """Respuesta de GET /api/v1/lotes-auditoria/{lote_id}/resumen."""

    empresa_nombre: str  # para el encabezado del informe de auditoría
    empresa_rut: Optional[str] = None
    por_transportista: list[FilaTransportista]
    criterios: CriteriosAuditoria


class EnvioSalida(BaseModel):
    """Item de GET /api/v1/lotes-auditoria/{lote_id}/envios."""

    id: str
    numero_guia: str
    transportista: Optional[str] = None
    fecha_despacho: datetime
    fecha_entrega: Optional[datetime] = None
    destino: Optional[str] = None
    valor_declarado: Optional[float] = None
    # CUMPLIDO | INCUMPLIDO | EN_TRANSITO | VENCIDA_SIN_ENTREGA | SIN_REGLA |
    # DATOS_INVALIDOS | PENDIENTE
    resultado: str
    horas_atraso: Optional[float] = None
    monto_multa: Optional[float] = None
    # Justificación de la auditoría de esta guía
    entregada: bool  # True si el archivo trae fecha de entrega
    fecha_limite: Optional[datetime] = None  # cuándo vencía el plazo SLA
    horas_habiles_permitidas: Optional[int] = None  # plazo de la regla SLA
    horas_habiles_transcurridas: Optional[float] = None  # hasta la entrega o el corte
    dias_fin_de_semana: int = 0  # días de fin de semana que no se contaron
    feriados: list[Feriado] = []  # feriados que no se contaron
    justificacion: str  # explicación en palabras del resultado


# ---------------------------------------------------------------------------
# IA generativa: carta de reclamo (Sprint 5)
# ---------------------------------------------------------------------------


class CartaReclamoSalida(BaseModel):
    """Respuesta de POST /api/v1/lotes-auditoria/{lote_id}/carta."""

    lote_id: str
    transportista: str
    origen: str  # "IA" (redactada por Gemini o Claude) | "PLANTILLA"
    proveedor: Optional[str] = None  # "Gemini" o "Claude", si origen es "IA"
    modelo: Optional[str] = None  # modelo usado, si origen es "IA"
    motivo_plantilla: Optional[str] = None  # por qué se usó la plantilla, si aplica
    aviso_respaldo: Optional[str] = None  # por qué no la redactó la IA principal
    guias_incumplidas: int
    monto_total: float
    texto: str


class EstadoProveedorIA(BaseModel):
    """Estado de un proveedor de IA dentro de GET /api/v1/ia/estado."""

    nombre: str  # "Gemini" | "Claude"
    papel: str  # "principal" | "respaldo"
    configurado: bool  # True si tiene clave (la clave nunca se devuelve)
    modelo: str


class EstadoIASalida(BaseModel):
    """Respuesta de GET /api/v1/ia/estado. Nunca incluye las claves."""

    configurada: bool  # True si al menos un proveedor tiene clave
    proveedor: Optional[str] = None  # el que se intentará primero ("Gemini" o "Claude")
    modelo: Optional[str] = None  # modelo de ese proveedor
    proveedores: list[EstadoProveedorIA]


class ResumenEjecutivoSalida(BaseModel):
    """Respuesta de POST /api/v1/lotes-auditoria/{lote_id}/resumen-ejecutivo."""

    lote_id: str
    origen: str  # "IA" (redactado por Gemini o Claude) | "PLANTILLA"
    proveedor: Optional[str] = None  # "Gemini" o "Claude", si origen es "IA"
    modelo: Optional[str] = None
    motivo_plantilla: Optional[str] = None
    aviso_respaldo: Optional[str] = None  # por qué no lo redactó la IA principal
    texto: str
