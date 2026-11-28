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

POST /api/v1/lotes-auditoria/{lote_id}/carta?transportista=...
    IA generativa (Sprint 5). Arma la carta de reclamo para un
    transportista con guías fuera de plazo en un lote ya auditado. Gemini
    (o Claude como respaldo) redacta el cuerpo a partir de un resumen
    agregado; si ninguna IA está disponible se usa una plantilla. Los montos
    y el anexo guía por guía salen siempre del motor de auditoría (ver
    app/ia_cartas.py y app/ia_proveedores.py).

POST /api/v1/lotes-auditoria/{lote_id}/resumen-ejecutivo
    IA generativa (HU-17). Resumen ejecutivo del lote para la gerencia, con
    las mismas reglas que la carta: cifras del motor, revisión de montos y
    plantilla de respaldo (ver app/ia_resumen.py).
"""

import io
import uuid
from datetime import date

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import consultas, ia_cartas, ia_resumen
from app.ia_cartas import pesos
from app.audit_engine import ejecutar_auditoria_lote
from app.database import obtener_bd
from app.column_mapping import mapear_columnas, CAMPOS_OBLIGATORIOS
from app.models import LoteAuditoria, Envio, EstadoLote, Empresa
from app.schemas import (
    RespuestaCarga,
    LoteAuditoriaSalida,
    ResultadoAuditoria,
    LoteResumenSalida,
    LoteDetalleSalida,
    EnvioSalida,
    CartaReclamoSalida,
    ResumenEjecutivoSalida,
)

router = APIRouter(prefix="/api/v1/lotes-auditoria", tags=["lotes-auditoria"])

EXTENSIONES_ACEPTADAS = (".csv", ".xlsx", ".xls")


def _leer_dataframe(nombre_archivo: str, contenido: bytes) -> pd.DataFrame:
    """Lee el archivo subido (CSV o Excel) como tabla de Pandas."""
    if nombre_archivo.lower().endswith(".csv"):
        # sep=None + engine="python" detecta automáticamente , vs ; (común en
        # exports de Excel en configuración regional chilena).
        return pd.read_csv(io.BytesIO(contenido), sep=None, engine="python")
    return pd.read_excel(io.BytesIO(contenido))


def _es_uuid(valor: str) -> bool:
    """
    Los id son UUID. PostgreSQL rechaza con error (500) un texto que no lo es,
    así que se valida antes de consultar y se responde 404 como en SQLite.
    """
    try:
        uuid.UUID(str(valor))
    except ValueError:
        return False
    return True


def _obtener_empresa_o_404(db: Session, empresa_id: str) -> Empresa:
    """Busca la empresa o responde 404 si no existe."""
    if not _es_uuid(empresa_id):
        raise HTTPException(status_code=404, detail="empresa_id no existe")
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="empresa_id no existe")
    return empresa


def _cargar_archivo_o_400(nombre_archivo: str, contenido: bytes) -> pd.DataFrame:
    """Valida el formato y lee el archivo; si no se puede, responde 400 con el motivo."""
    if not nombre_archivo.lower().endswith(EXTENSIONES_ACEPTADAS):
        raise HTTPException(
            status_code=400, detail=f"Formato no soportado. Usa {EXTENSIONES_ACEPTADAS}"
        )
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
        envios.append(
            Envio(
                lote_auditoria_id=lote.id,
                nombre_transportista_original=str(
                    fila.get(mapeo.get("nombre_transportista"), "")
                ).strip()
                or None,
                numero_guia=str(fila[mapeo["numero_guia"]]).strip(),
                fecha_despacho=pd.to_datetime(fila[mapeo["fecha_despacho"]]),
                fecha_entrega=(
                    pd.to_datetime(fila[mapeo["fecha_entrega"]])
                    if "fecha_entrega" in mapeo and pd.notna(fila.get(mapeo["fecha_entrega"]))
                    else None
                ),
                destino=(
                    str(fila.get(mapeo["destino"], "")).strip() or None
                    if "destino" in mapeo
                    else None
                ),
                valor_declarado=(
                    float(fila[mapeo["valor_declarado"]])
                    if "valor_declarado" in mapeo and pd.notna(fila.get(mapeo["valor_declarado"]))
                    else None
                ),
            )
        )
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
    """POST /api/v1/lotes-auditoria/cargar: sube un archivo de envíos.

    Recibe el archivo, reconoce sus columnas y guarda las guías como un lote nuevo.
    """
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
    """Busca el lote o responde 404 si no existe."""
    if not _es_uuid(lote_id):
        raise HTTPException(status_code=404, detail="Lote no encontrado")
    lote = db.query(LoteAuditoria).filter(LoteAuditoria.id == lote_id).first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado")
    return lote


@router.get("", response_model=list[LoteResumenSalida])
def listar_lotes_auditoria(
    empresa_id: str = Query(..., description="ID de la empresa dueña de los lotes"),
    db: Session = Depends(obtener_bd),
):
    """GET /api/v1/lotes-auditoria?empresa_id=...: lotes de una empresa."""
    _obtener_empresa_o_404(db, empresa_id)
    return consultas.listar_lotes(db, empresa_id)


@router.get("/{lote_id}", response_model=LoteAuditoriaSalida)
def obtener_lote_auditoria(lote_id: str, db: Session = Depends(obtener_bd)):
    """GET /api/v1/lotes-auditoria/{lote_id}: datos básicos de un lote."""
    return _obtener_lote_o_404(db, lote_id)


@router.get("/{lote_id}/resumen", response_model=LoteDetalleSalida)
def obtener_resumen_lote(lote_id: str, db: Session = Depends(obtener_bd)):
    """GET /api/v1/lotes-auditoria/{lote_id}/resumen: conteos y desglose por transportista."""
    return consultas.detalle_lote(db, _obtener_lote_o_404(db, lote_id))


@router.get("/{lote_id}/envios", response_model=list[EnvioSalida])
def listar_envios_lote(lote_id: str, db: Session = Depends(obtener_bd)):
    """GET /api/v1/lotes-auditoria/{lote_id}/envios: guías del lote con su resultado."""
    return consultas.listar_envios(db, _obtener_lote_o_404(db, lote_id))


@router.post("/{lote_id}/auditar", response_model=ResultadoAuditoria)
def auditar_lote(lote_id: str, db: Session = Depends(obtener_bd)):
    """POST /api/v1/lotes-auditoria/{lote_id}/auditar: ejecuta el motor de auditoría."""
    lote = _obtener_lote_o_404(db, lote_id)

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
        vencidas_sin_entrega=resumen.vencidas_sin_entrega,
        datos_invalidos=resumen.datos_invalidos,
        monto_multa_total=resumen.monto_multa_total,
        fecha_corte=lote.fecha_corte,
        mensaje=(
            f"Auditoría completada: {resumen.envios_incumplidos} de "
            f"{resumen.envios_auditados} guías entregadas llegaron fuera de plazo "
            f"(multa total {pesos(resumen.monto_multa_total)}). "
            f"{resumen.omitidos_sin_fecha_entrega} sin fecha de entrega "
            f"({resumen.vencidas_sin_entrega} con el plazo vencido), "
            f"{resumen.omitidos_sin_regla} sin regla SLA y "
            f"{resumen.datos_invalidos} con datos a revisar."
        ),
    )


@router.post("/{lote_id}/carta", response_model=CartaReclamoSalida)
def generar_carta_reclamo(
    lote_id: str,
    transportista: str = Query(
        ..., min_length=1, description="Nombre del transportista, tal como aparece en el lote"
    ),
    usar_ia: bool = Query(
        True, description="false = usar directamente la plantilla, sin llamar a la IA"
    ),
    db: Session = Depends(obtener_bd),
):
    """POST .../{lote_id}/carta: carta de reclamo para un transportista (IA o plantilla)."""
    lote = _obtener_lote_o_404(db, lote_id)
    if not consultas.lote_fue_auditado(lote):
        raise HTTPException(
            status_code=409,
            detail="Primero audita el lote: la carta se arma con los resultados de la auditoría.",
        )

    clave = transportista.strip().lower()
    detalle = consultas.detalle_lote(db, lote)
    fila = next((f for f in detalle.por_transportista if f.nombre.strip().lower() == clave), None)
    if fila is None:
        raise HTTPException(
            status_code=404,
            detail=f"El transportista '{transportista.strip()}' no tiene guías en este lote.",
        )

    incumplidas = [
        e
        for e in consultas.listar_envios(db, lote)
        if e.resultado == consultas.INCUMPLIDO and (e.transportista or "").strip().lower() == clave
    ]
    if not incumplidas:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{fila.nombre} no tiene guías fuera de plazo en este lote: no hay nada que"
                " reclamar."
            ),
        )

    datos = ia_cartas.DatosCarta(
        empresa_nombre=lote.empresa.nombre,
        empresa_rut=lote.empresa.rut,
        transportista=fila.nombre,
        nombre_archivo=lote.nombre_archivo,
        horas_habiles_maximas=fila.horas_habiles_maximas,
        multa_por_incumplimiento=fila.multa_por_incumplimiento,
        guias_auditadas=fila.conteos.cumplidos + fila.conteos.incumplidos,
        guias=[
            ia_cartas.GuiaIncumplida(
                numero_guia=e.numero_guia,
                destino=e.destino,
                fecha_despacho=e.fecha_despacho,
                fecha_entrega=e.fecha_entrega,
                horas_atraso=e.horas_atraso,
                monto_multa=e.monto_multa,
            )
            for e in incumplidas
        ],
        fecha_emision=date.today(),
    )
    resultado = ia_cartas.generar_carta(datos, usar_ia=usar_ia)

    return CartaReclamoSalida(
        lote_id=lote.id,
        transportista=fila.nombre,
        origen=resultado.origen,
        proveedor=resultado.proveedor,
        modelo=resultado.modelo,
        motivo_plantilla=resultado.motivo_plantilla,
        aviso_respaldo=resultado.aviso_respaldo,
        guias_incumplidas=datos.cantidad,
        monto_total=datos.monto_total,
        texto=resultado.texto,
    )


@router.post("/{lote_id}/resumen-ejecutivo", response_model=ResumenEjecutivoSalida)
def generar_resumen_ejecutivo(
    lote_id: str,
    usar_ia: bool = Query(True, description="false = usar directamente la plantilla, sin IA"),
    db: Session = Depends(obtener_bd),
):
    """POST .../{lote_id}/resumen-ejecutivo: resumen del lote para la gerencia."""
    lote = _obtener_lote_o_404(db, lote_id)
    if not consultas.lote_fue_auditado(lote):
        raise HTTPException(
            status_code=409,
            detail="Primero audita el lote: el resumen se arma con los resultados de la auditoría.",
        )

    detalle = consultas.detalle_lote(db, lote)
    envios = consultas.listar_envios(db, lote)
    fechas = [e.fecha_despacho.date() for e in envios if e.fecha_despacho]
    c = detalle.conteos
    datos = ia_resumen.DatosResumen(
        empresa_nombre=lote.empresa.nombre,
        nombre_archivo=lote.nombre_archivo,
        total_guias=c.total,
        cumplidas=c.cumplidos,
        incumplidas=c.incumplidos,
        en_transito=c.en_transito,
        vencidas_sin_entrega=c.vencidas_sin_entrega,
        datos_invalidos=c.datos_invalidos,
        sin_regla=c.sin_regla,
        monto_total=c.monto_multa_total,
        periodo=(min(fechas), max(fechas)) if fechas else None,
        transportistas=[
            ia_resumen.ResultadoTransportista(
                nombre=f.nombre,
                auditadas=f.conteos.cumplidos + f.conteos.incumplidos,
                incumplidas=f.conteos.incumplidos,
                monto=f.conteos.monto_multa_total,
                multa_unitaria=f.multa_por_incumplimiento,
                sin_regla=f.conteos.sin_regla,
            )
            for f in detalle.por_transportista
        ],
    )
    resultado = ia_resumen.generar_resumen(datos, usar_ia=usar_ia)
    return ResumenEjecutivoSalida(
        lote_id=lote.id,
        origen=resultado.origen,
        proveedor=resultado.proveedor,
        modelo=resultado.modelo,
        motivo_plantilla=resultado.motivo_plantilla,
        aviso_respaldo=resultado.aviso_respaldo,
        texto=resultado.texto,
    )
