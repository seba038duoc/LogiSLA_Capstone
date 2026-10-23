"""
Endpoints de ingesta y auditoría de LogiSLA.

POST /api/v1/lotes-auditoria/cargar
    Recibe un CSV/Excel, detecta la empresa (por ahora vía query param
    empresa_id — el login/auth de empresas es de otro sprint), mapea
    columnas automáticamente, y crea el LoteAuditoria y los Envio en
    estado "sin auditar" (a la espera del motor del Sprint 2).

    Si el mapeo automático no logra ubicar las columnas obligatorias, la
    carga se rechaza con un error 400 (sin tocar la base de datos) — no
    hay un formulario de mapeo manual: las empresas ya tienen sus
    documentos de envíos bien estructurados, así que si un archivo no se
    puede leer automáticamente, lo correcto es que quien lo sube corrija
    el archivo (nombres de columna esperados) en vez de mapear a mano.

GET /api/v1/lotes-auditoria/{lote_id}
    Consulta de estado de un lote ya cargado.

GET /api/v1/lotes-auditoria?empresa_id=...
    Lotes de una empresa (del más nuevo al más antiguo) con sus conteos.

GET /api/v1/lotes-auditoria/{lote_id}/resumen
    Detalle del lote: conteos totales y desglose por transportista.

GET /api/v1/lotes-auditoria/{lote_id}/envios
    Todas las guías del lote con su resultado de auditoría.

POST /api/v1/lotes-auditoria/{lote_id}/auditar
    Motor de auditoría (Sprint 2). Corre sobre todos los Envio del lote:
    resuelve/crea el Transportista de cada envío, busca su ReglaSLA
    activa y, si ya tiene fecha de entrega, calcula si incumplió el SLA
    y la multa correspondiente. Se puede volver a llamar sobre el mismo
    lote (ej. si se actualizaron las reglas SLA) sin problema.
"""
import io

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import consultas
from app.audit_engine import ejecutar_auditoria_lote
from app.database import obtener_bd
from app.column_mapping import mapear_columnas, CAMPOS_OBLIGATORIOS
from app.models import LoteAuditoria, Envio, EstadoLote, Empresa
from app.schemas import (
    RespuestaCarga, LoteAuditoriaSalida, ResultadoAuditoria,
    LoteResumenSalida, LoteDetalleSalida, EnvioSalida,
)

router = APIRouter(prefix="/api/v1/lotes-auditoria", tags=["lotes-auditoria"])

EXTENSIONES_ACEPTADAS = (".csv", ".xlsx", ".xls")


def _leer_dataframe(nombre_archivo: str, contenido: bytes) -> pd.DataFrame:
    if nombre_archivo.lower().endswith(".csv"):
        # sep=None + engine="python" detecta automáticamente , vs ; (común en
        # exports de Excel en configuración regional chilena).
        return pd.read_csv(io.BytesIO(contenido), sep=None, engine="python")
    return pd.read_excel(io.BytesIO(contenido))


def _obtener_empresa_o_404(db: Session, empresa_id: str) -> Empresa:
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="empresa_id no existe")
    return empresa


def _cargar_archivo_o_400(nombre_archivo: str, contenido: bytes) -> pd.DataFrame:
    if not nombre_archivo.lower().endswith(EXTENSIONES_ACEPTADAS):
        raise HTTPException(status_code=400, detail=f"Formato no soportado. Usa {EXTENSIONES_ACEPTADAS}")
    try:
        df = _leer_dataframe(nombre_archivo, contenido)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo: {exc}")
    if df.empty:
        raise HTTPException(status_code=400, detail="El archivo no tiene filas de datos")
    return df


def _persistir_lote(
    db: Session,
    empresa_id: str,
    nombre_archivo: str,
    df: pd.DataFrame,
    mapeo: dict,
) -> LoteAuditoria:
    """
    Crea el LoteAuditoria y sus Envio a partir de un mapeo ya validado.
    """
    lote = LoteAuditoria(
        empresa_id=empresa_id,
        nombre_archivo=nombre_archivo,
        estado=EstadoLote.PENDIENTE,
        total_filas=len(df),
        mapeo_columnas=mapeo,
    )
    db.add(lote)
    db.flush()  # para tener lote.id antes del commit

    envios = []
    for _, fila in df.iterrows():
        envios.append(Envio(
            lote_auditoria_id=lote.id,
            nombre_transportista_original=str(fila.get(mapeo.get("nombre_transportista"), "")).strip() or None,
            numero_guia=str(fila[mapeo["numero_guia"]]).strip(),
            fecha_despacho=pd.to_datetime(fila[mapeo["fecha_despacho"]]),
            fecha_entrega=(
                pd.to_datetime(fila[mapeo["fecha_entrega"]])
                if "fecha_entrega" in mapeo and pd.notna(fila.get(mapeo["fecha_entrega"]))
                else None
            ),
            destino=(
                str(fila.get(mapeo["destino"], "")).strip() or None
                if "destino" in mapeo else None
            ),
            valor_declarado=(
                float(fila[mapeo["valor_declarado"]])
                if "valor_declarado" in mapeo and pd.notna(fila.get(mapeo["valor_declarado"]))
                else None
            ),
        ))
    db.bulk_save_objects(envios)
    db.commit()
    db.refresh(lote)
    return lote


@router.post("/cargar", response_model=RespuestaCarga)
async def cargar_lote_auditoria(
    empresa_id: str = Query(..., description="ID de la empresa dueña del lote"),
    file: UploadFile = File(...),
    db: Session = Depends(obtener_bd),
):
    _obtener_empresa_o_404(db, empresa_id)
    contenido = await file.read()
    df = _cargar_archivo_o_400(file.filename, contenido)

    resultado_mapeo = mapear_columnas(list(df.columns))

    if not resultado_mapeo.es_valido:
        # No tocamos la BD: se rechaza la carga con el detalle de qué
        # columnas obligatorias no se pudieron reconocer, para que quien
        # subió el archivo lo corrija y lo vuelva a intentar.
        faltantes = ", ".join(resultado_mapeo.obligatorios_sin_mapear)
        raise HTTPException(
            status_code=400,
            detail=(
                f"No se pudieron reconocer automáticamente las columnas obligatorias: {faltantes}. "
                f"Encabezados encontrados en el archivo: {list(df.columns)}. "
                f"Revisa que el archivo tenga columnas para: {', '.join(CAMPOS_OBLIGATORIOS)}."
            ),
        )

    lote = _persistir_lote(db, empresa_id, file.filename, df, resultado_mapeo.mapeo)

    return RespuestaCarga(
        lote_id=lote.id,
        nombre_archivo=lote.nombre_archivo,
        estado=lote.estado.value,
        total_filas=lote.total_filas,
        mapeo_columnas=resultado_mapeo.mapeo,
        advertencias_ambiguas=resultado_mapeo.ambiguos,
        mensaje=f"Lote creado con {lote.total_filas} guías. Pendiente de auditoría.",
    )


def _obtener_lote_o_404(db: Session, lote_id: str) -> LoteAuditoria:
    lote = db.query(LoteAuditoria).filter(LoteAuditoria.id == lote_id).first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado")
    return lote


@router.get("", response_model=list[LoteResumenSalida])
def listar_lotes_auditoria(
    empresa_id: str = Query(..., description="ID de la empresa dueña de los lotes"),
    db: Session = Depends(obtener_bd),
):
    _obtener_empresa_o_404(db, empresa_id)
    return consultas.listar_lotes(db, empresa_id)


@router.get("/{lote_id}", response_model=LoteAuditoriaSalida)
def obtener_lote_auditoria(lote_id: str, db: Session = Depends(obtener_bd)):
    return _obtener_lote_o_404(db, lote_id)


@router.get("/{lote_id}/resumen", response_model=LoteDetalleSalida)
def obtener_resumen_lote(lote_id: str, db: Session = Depends(obtener_bd)):
    return consultas.detalle_lote(db, _obtener_lote_o_404(db, lote_id))


@router.get("/{lote_id}/envios", response_model=list[EnvioSalida])
def listar_envios_lote(lote_id: str, db: Session = Depends(obtener_bd)):
    return consultas.listar_envios(db, _obtener_lote_o_404(db, lote_id))


@router.post("/{lote_id}/auditar", response_model=ResultadoAuditoria)
def auditar_lote(lote_id: str, db: Session = Depends(obtener_bd)):
    lote = db.query(LoteAuditoria).filter(LoteAuditoria.id == lote_id).first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado")

    resumen = ejecutar_auditoria_lote(db, lote)

    return ResultadoAuditoria(
        lote_id=resumen.lote_id,
        estado=lote.estado.value,
        total_envios=resumen.total_envios,
        envios_auditados=resumen.envios_auditados,
        envios_incumplidos=resumen.envios_incumplidos,
        envios_cumplidos=resumen.envios_cumplidos,
        omitidos_sin_regla=resumen.omitidos_sin_regla,
        omitidos_sin_fecha_entrega=resumen.omitidos_sin_fecha_entrega,
        monto_multa_total=resumen.monto_multa_total,
        mensaje=(
            f"Auditoría completada: {resumen.envios_incumplidos} de "
            f"{resumen.envios_auditados} guías auditadas incumplieron su SLA "
            f"(multa total ${resumen.monto_multa_total:,.0f}). "
            f"{resumen.omitidos_sin_fecha_entrega} sin fecha de entrega aún, "
            f"{resumen.omitidos_sin_regla} sin regla SLA para su transportista."
        ),
    )
