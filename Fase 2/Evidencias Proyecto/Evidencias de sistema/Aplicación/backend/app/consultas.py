"""
Consultas de solo lectura sobre lotes ya cargados/auditados, para las
pantallas del frontend (panel de lotes, detalle del lote, tabla de guías).

No recalculan nada: leen lo que dejó el motor de auditoría en cada Envio
(incumplio_sla, horas_atraso, monto_multa) y lo clasifican/agrupan.
"""
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.audit_engine import buscar_regla_sla_activa
from app.models import Envio, EstadoLote, LoteAuditoria, Transportista
from app.schemas import (
    Conteos, EnvioSalida, FilaTransportista, LoteDetalleSalida, LoteResumenSalida,
)

CUMPLIDO = "CUMPLIDO"
INCUMPLIDO = "INCUMPLIDO"
EN_TRANSITO = "EN_TRANSITO"
SIN_REGLA = "SIN_REGLA"
PENDIENTE = "PENDIENTE"


def lote_fue_auditado(lote: LoteAuditoria) -> bool:
    return lote.estado == EstadoLote.COMPLETADO


def clasificar_envio(envio: Envio, auditado: bool) -> str:
    """
    Misma lógica de categorías que ejecutar_auditoria_lote(), leída desde
    lo que quedó guardado:
      - lote sin auditar            -> PENDIENTE
      - sin fecha de entrega        -> EN_TRANSITO
      - incumplio_sla True / False  -> INCUMPLIDO / CUMPLIDO
      - entregada pero sin resultado-> SIN_REGLA (no había regla SLA activa)
    """
    if not auditado:
        return PENDIENTE
    if envio.fecha_entrega is None:
        return EN_TRANSITO
    if envio.incumplio_sla is True:
        return INCUMPLIDO
    if envio.incumplio_sla is False:
        return CUMPLIDO
    return SIN_REGLA


def _sumar(conteos: Conteos, resultado: str, monto_multa: float | None) -> None:
    conteos.total += 1
    if resultado == CUMPLIDO:
        conteos.cumplidos += 1
    elif resultado == INCUMPLIDO:
        conteos.incumplidos += 1
        conteos.monto_multa_total += monto_multa or 0.0
    elif resultado == EN_TRANSITO:
        conteos.en_transito += 1
    elif resultado == SIN_REGLA:
        conteos.sin_regla += 1
    else:
        conteos.pendientes += 1


def conteos_por_lote(db: Session, lotes: list[LoteAuditoria]) -> dict[str, Conteos]:
    """
    Conteos de todos los lotes en UNA consulta agrupada (para el listado,
    donde cargar cada Envio en memoria sería caro con lotes de 10.000+ guías).
    """
    if not lotes:
        return {}

    filas = (
        db.query(
            Envio.lote_auditoria_id,
            func.count(Envio.id),
            func.sum(case((Envio.fecha_entrega.is_(None), 1), else_=0)),
            func.sum(case((Envio.fecha_entrega.is_(None), 0), (Envio.incumplio_sla.is_(True), 1), else_=0)),
            func.sum(case((Envio.fecha_entrega.is_(None), 0), (Envio.incumplio_sla.is_(False), 1), else_=0)),
            func.sum(case(
                (Envio.fecha_entrega.is_(None), 0.0),
                (Envio.incumplio_sla.is_(True), func.coalesce(Envio.monto_multa, 0.0)),
                else_=0.0,
            )),
        )
        .filter(Envio.lote_auditoria_id.in_([lote.id for lote in lotes]))
        .group_by(Envio.lote_auditoria_id)
        .all()
    )
    crudos = {fila[0]: fila[1:] for fila in filas}

    resultado: dict[str, Conteos] = {}
    for lote in lotes:
        total, sin_entrega, incumplidos, cumplidos, multa = crudos.get(lote.id, (0, 0, 0, 0, 0.0))
        total, sin_entrega = int(total or 0), int(sin_entrega or 0)
        incumplidos, cumplidos = int(incumplidos or 0), int(cumplidos or 0)
        if lote_fue_auditado(lote):
            resultado[lote.id] = Conteos(
                total=total,
                cumplidos=cumplidos,
                incumplidos=incumplidos,
                en_transito=sin_entrega,
                sin_regla=total - cumplidos - incumplidos - sin_entrega,
                monto_multa_total=round(float(multa or 0.0), 2),
            )
        else:
            resultado[lote.id] = Conteos(total=total, pendientes=total)
    return resultado


def _resumen(lote: LoteAuditoria, conteos: Conteos) -> dict:
    return dict(
        id=lote.id,
        nombre_archivo=lote.nombre_archivo,
        estado=lote.estado.value,
        total_filas=lote.total_filas,
        fecha_creacion=lote.fecha_creacion,
        fecha_procesado=lote.fecha_procesado,
        conteos=conteos,
    )


def listar_lotes(db: Session, empresa_id: str) -> list[LoteResumenSalida]:
    lotes = (
        db.query(LoteAuditoria)
        .filter(LoteAuditoria.empresa_id == empresa_id)
        .order_by(LoteAuditoria.fecha_creacion.desc(), LoteAuditoria.id)
        .all()
    )
    conteos = conteos_por_lote(db, lotes)
    return [LoteResumenSalida(**_resumen(lote, conteos[lote.id])) for lote in lotes]


def _envios_con_transportista(db: Session, lote_id: str):
    return (
        db.query(Envio, Transportista)
        .outerjoin(Transportista, Envio.transportista_id == Transportista.id)
        .filter(Envio.lote_auditoria_id == lote_id)
        .order_by(Envio.numero_guia)
        .all()
    )


def _nombre_transportista(envio: Envio, transportista: Transportista | None) -> str | None:
    if transportista is not None:
        return transportista.nombre
    return envio.nombre_transportista_original


def detalle_lote(db: Session, lote: LoteAuditoria) -> LoteDetalleSalida:
    auditado = lote_fue_auditado(lote)
    totales = Conteos()
    # clave normalizada -> [nombre a mostrar, Conteos, Transportista | None]
    grupos: dict[str, list] = {}

    for envio, transportista in _envios_con_transportista(db, lote.id):
        resultado = clasificar_envio(envio, auditado)
        _sumar(totales, resultado, envio.monto_multa)

        nombre = _nombre_transportista(envio, transportista) or "Sin transportista"
        clave = nombre.strip().lower()
        if clave not in grupos:
            grupos[clave] = [nombre.strip(), Conteos(), transportista]
        grupo = grupos[clave]
        if grupo[2] is None and transportista is not None:
            grupo[2] = transportista
        _sumar(grupo[1], resultado, envio.monto_multa)

    filas = []
    for clave, (nombre, conteos, transportista) in grupos.items():
        # Antes de auditar los Envio todavía no están vinculados a un
        # Transportista: lo buscamos por nombre para poder mostrar su SLA.
        if transportista is None:
            transportista = (
                db.query(Transportista).filter(func.lower(Transportista.nombre) == clave).first()
            )
        regla = buscar_regla_sla_activa(db, transportista.id) if transportista else None
        conteos.monto_multa_total = round(conteos.monto_multa_total, 2)
        filas.append(FilaTransportista(
            nombre=nombre,
            horas_habiles_maximas=regla.horas_habiles_maximas if regla else None,
            multa_por_incumplimiento=regla.multa_por_incumplimiento if regla else None,
            conteos=conteos,
        ))

    # Primero los que más plata deben, después los de más volumen.
    filas.sort(key=lambda f: (-f.conteos.monto_multa_total, -f.conteos.total, f.nombre.lower()))
    totales.monto_multa_total = round(totales.monto_multa_total, 2)
    return LoteDetalleSalida(**_resumen(lote, totales), por_transportista=filas)


def listar_envios(db: Session, lote: LoteAuditoria) -> list[EnvioSalida]:
    auditado = lote_fue_auditado(lote)
    salida = []
    for envio, transportista in _envios_con_transportista(db, lote.id):
        resultado = clasificar_envio(envio, auditado)
        con_resultado = resultado in (CUMPLIDO, INCUMPLIDO)
        salida.append(EnvioSalida(
            id=envio.id,
            numero_guia=envio.numero_guia,
            transportista=_nombre_transportista(envio, transportista),
            fecha_despacho=envio.fecha_despacho,
            fecha_entrega=envio.fecha_entrega,
            destino=envio.destino,
            valor_declarado=envio.valor_declarado,
            resultado=resultado,
            horas_atraso=envio.horas_atraso if con_resultado else None,
            monto_multa=envio.monto_multa if con_resultado else None,
        ))
    return salida
