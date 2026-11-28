"""
Consultas de solo lectura sobre lotes ya cargados/auditados, para las
pantallas del frontend (panel de lotes, detalle del lote, tabla de guías).

No recalculan el resultado: leen lo que dejó el motor de auditoría en cada
Envio (resultado, fecha límite, horas, multa) y lo agrupan. Lo único que se
arma aquí es la justificación en palabras de cada guía, a partir de esos
datos y del calendario de feriados.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.audit_engine import (
    CUMPLIDO,
    DATOS_INVALIDOS,
    EN_TRANSITO,
    FIN_JORNADA,
    INCUMPLIDO,
    INICIO_JORNADA,
    PENDIENTE,
    SIN_REGLA,
    VENCIDA_SIN_ENTREGA,
    buscar_regla_sla_activa,
    dias_no_habiles,
    feriados_entre,
)
from app.models import Envio, EstadoLote, LoteAuditoria, ReglaSLA, Transportista
from app.schemas import (
    Conteos,
    CriteriosAuditoria,
    EnvioSalida,
    Feriado,
    FilaTransportista,
    LoteDetalleSalida,
    LoteResumenSalida,
)

# Campo de Conteos que corresponde a cada resultado.
CAMPO_CONTEO = {
    CUMPLIDO: "cumplidos",
    INCUMPLIDO: "incumplidos",
    EN_TRANSITO: "en_transito",
    VENCIDA_SIN_ENTREGA: "vencidas_sin_entrega",
    SIN_REGLA: "sin_regla",
    DATOS_INVALIDOS: "datos_invalidos",
    PENDIENTE: "pendientes",
}


def lote_fue_auditado(lote: LoteAuditoria) -> bool:
    """Indica si el motor de auditoría ya procesó el lote (estado COMPLETADO)."""
    return lote.estado == EstadoLote.COMPLETADO


def clasificar_envio(envio: Envio, auditado: bool) -> str:
    """
    Resultado de una guía: el que guardó el motor (Envio.resultado). Para
    lotes auditados antes de la migración 0002 se deduce como se hacía
    entonces (sin entrega -> EN_TRANSITO; con resultado -> INCUMPLIDO o
    CUMPLIDO; si no -> SIN_REGLA). Un lote sin auditar -> PENDIENTE.
    """
    if not auditado:
        return PENDIENTE
    if envio.resultado:
        return envio.resultado
    if envio.fecha_entrega is None:
        return EN_TRANSITO
    if envio.incumplio_sla is True:
        return INCUMPLIDO
    if envio.incumplio_sla is False:
        return CUMPLIDO
    return SIN_REGLA


def _sumar(conteos: Conteos, resultado: str, monto_multa: float | None) -> None:
    """Suma una guía a los conteos según su resultado (y su multa, si llegó fuera de plazo)."""
    conteos.total += 1
    campo = CAMPO_CONTEO.get(resultado, "pendientes")
    setattr(conteos, campo, getattr(conteos, campo) + 1)
    if resultado == INCUMPLIDO:
        conteos.monto_multa_total += monto_multa or 0.0


def conteos_por_lote(db: Session, lotes: list[LoteAuditoria]) -> dict[str, Conteos]:
    """
    Conteos de todos los lotes en UNA consulta agrupada por lote y resultado
    (para el listado, donde cargar cada Envio en memoria sería caro con
    lotes de 10.000+ guías).
    """
    if not lotes:
        return {}

    # Resultado guardado, o el criterio anterior a la migración 0002 si falta.
    resultado_sql = func.coalesce(
        Envio.resultado,
        case(
            (Envio.fecha_entrega.is_(None), EN_TRANSITO),
            (Envio.incumplio_sla.is_(True), INCUMPLIDO),
            (Envio.incumplio_sla.is_(False), CUMPLIDO),
            else_=SIN_REGLA,
        ),
    )
    filas = (
        db.query(
            Envio.lote_auditoria_id,
            resultado_sql,
            func.count(Envio.id),
            func.sum(func.coalesce(Envio.monto_multa, 0.0)),
        )
        .filter(Envio.lote_auditoria_id.in_([lote.id for lote in lotes]))
        .group_by(Envio.lote_auditoria_id, resultado_sql)
        .all()
    )

    por_lote: dict[str, list] = {}
    for lote_id, resultado, cantidad, multa in filas:
        por_lote.setdefault(lote_id, []).append((resultado, int(cantidad or 0), multa))

    salida: dict[str, Conteos] = {}
    for lote in lotes:
        conteos = Conteos()
        for resultado, cantidad, multa in por_lote.get(lote.id, []):
            conteos.total += cantidad
            if not lote_fue_auditado(lote):
                conteos.pendientes += cantidad
                continue
            campo = CAMPO_CONTEO.get(resultado, "pendientes")
            setattr(conteos, campo, getattr(conteos, campo) + cantidad)
            if resultado == INCUMPLIDO:
                conteos.monto_multa_total += float(multa or 0.0)
        conteos.monto_multa_total = round(conteos.monto_multa_total, 2)
        salida[lote.id] = conteos
    return salida


def _resumen(lote: LoteAuditoria, conteos: Conteos) -> dict:
    """Arma el diccionario con los datos de un lote para las respuestas de la API."""
    return dict(
        id=lote.id,
        nombre_archivo=lote.nombre_archivo,
        estado=lote.estado.value,
        total_filas=lote.total_filas,
        fecha_creacion=lote.fecha_creacion,
        fecha_procesado=lote.fecha_procesado,
        fecha_corte=lote.fecha_corte,
        conteos=conteos,
    )


def listar_lotes(db: Session, empresa_id: str) -> list[LoteResumenSalida]:
    """Lotes de una empresa, del más reciente al más antiguo, con sus conteos."""
    lotes = (
        db.query(LoteAuditoria)
        .filter(LoteAuditoria.empresa_id == empresa_id)
        .order_by(LoteAuditoria.fecha_creacion.desc(), LoteAuditoria.id)
        .all()
    )
    conteos = conteos_por_lote(db, lotes)
    return [LoteResumenSalida(**_resumen(lote, conteos[lote.id])) for lote in lotes]


def _envios_con_transportista(db: Session, lote_id: str):
    """Guías de un lote junto con su transportista registrado (si lo tiene)."""
    return (
        db.query(Envio, Transportista)
        .outerjoin(Transportista, Envio.transportista_id == Transportista.id)
        .filter(Envio.lote_auditoria_id == lote_id)
        .order_by(Envio.numero_guia)
        .all()
    )


def _nombre_transportista(envio: Envio, transportista: Transportista | None) -> str | None:
    """Nombre del transportista: el registrado o, si no existe, el escrito en el archivo."""
    if transportista is not None:
        return transportista.nombre
    return envio.nombre_transportista_original


def detalle_lote(db: Session, lote: LoteAuditoria) -> LoteDetalleSalida:
    """Detalle de un lote: conteos totales y desglose por transportista con su regla SLA."""
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
        filas.append(
            FilaTransportista(
                nombre=nombre,
                horas_habiles_maximas=regla.horas_habiles_maximas if regla else None,
                multa_por_incumplimiento=regla.multa_por_incumplimiento if regla else None,
                conteos=conteos,
            )
        )

    # Primero los que más plata deben, después los de más volumen.
    filas.sort(key=lambda f: (-f.conteos.monto_multa_total, -f.conteos.total, f.nombre.lower()))
    totales.monto_multa_total = round(totales.monto_multa_total, 2)
    return LoteDetalleSalida(
        **_resumen(lote, totales),
        empresa_nombre=lote.empresa.nombre,
        empresa_rut=lote.empresa.rut,
        por_transportista=filas,
        criterios=criterios_auditoria(db, lote),
    )


def criterios_auditoria(db: Session, lote: LoteAuditoria) -> CriteriosAuditoria:
    """
    Metodología de la auditoría del lote: jornada hábil, calendario de
    feriados, período de despacho del archivo, feriados que cayeron en ese
    período y los criterios con que se clasificó cada guía.
    """
    desde, hasta_despacho, hasta_entrega = (
        db.query(
            func.min(Envio.fecha_despacho),
            func.max(Envio.fecha_despacho),
            func.max(Envio.fecha_entrega),
        )
        .filter(Envio.lote_auditoria_id == lote.id)
        .one()
    )
    feriados = []
    if desde is not None:
        # El período auditado llega hasta la última entrega o, si hay guías
        # sin entrega, hasta la fecha de corte.
        candidatos = [f for f in (hasta_despacho, hasta_entrega, lote.fecha_corte) if f]
        hasta = max(_local(f) for f in candidatos)
        feriados = [
            Feriado(fecha=dia, nombre=nombre)
            for dia, nombre in feriados_entre(_local(desde).date(), hasta.date())
            if dia.weekday() < 5  # un feriado en fin de semana no cambia nada
        ]
    return CriteriosAuditoria(
        jornada=f"{INICIO_JORNADA:%H:%M} a {FIN_JORNADA:%H:%M}, de lunes a viernes",
        calendario="Feriados legales de Chile (biblioteca Workalendar)",
        despacho_desde=desde,
        despacho_hasta=hasta_despacho,
        feriados=feriados,
        reglas=[
            "El plazo de cada guía se cuenta en horas hábiles desde su despacho, según la regla"
            " SLA vigente de su transportista; noches, fines de semana y feriados no cuentan.",
            "Entregada dentro del plazo: en plazo. Entregada después de la fecha límite: fuera de"
            " plazo, con la multa fija por guía de la regla SLA.",
            "Sin fecha de entrega: se compara contra la fecha de corte de la auditoría. Si el"
            " plazo ya venció, queda como «vencida sin entrega»: alerta para consultar al"
            " transportista, sin multa, porque no hay registro de cuándo llegó.",
            "No se auditan las guías con datos inconsistentes (entrega antes del despacho,"
            " fechas posteriores al corte o número de guía repetido), ni las de transportistas"
            " sin regla SLA activa; se informan aparte.",
        ],
    )


# ---------------------------------------------------------------------------
# Justificación por guía
# ---------------------------------------------------------------------------


def _local(fecha: datetime) -> datetime:
    """Fecha sin zona horaria (las fechas del archivo son hora local de Chile)."""
    return fecha.replace(tzinfo=None) if fecha.tzinfo is not None else fecha


def _fecha(fecha: datetime | None) -> str:
    """Fecha y hora en formato dd-mm-aaaa hh:mm."""
    return _local(fecha).strftime("%d-%m-%Y %H:%M") if fecha else "sin fecha"


def _horas(horas: float | None) -> str:
    """Horas con un decimal y coma: 10.5 -> '10,5'; 24.0 -> '24'."""
    if horas is None:
        return "?"
    # Redondeo "hacia arriba" en el medio (27,25 -> 27,3), igual que la tabla de
    # guías del frontend; con f"{x:.1f}" Python daría 27,2 y no calzarían.
    redondeado = Decimal(str(horas)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    texto = f"{redondeado:.1f}".replace(".", ",")
    return texto[:-2] if texto.endswith(",0") else texto


def _pesos(monto: float | None) -> str:
    """Monto en pesos chilenos: 15000 -> '$15.000'."""
    return f"${round(monto or 0):,}".replace(",", ".")


def _texto_dias_no_habiles(fines_de_semana: int, feriados: list[tuple]) -> str:
    """Frase con los días que no se contaron (o vacía si no hubo)."""
    partes = []
    if fines_de_semana:
        partes.append(
            f"{fines_de_semana} día{'s' if fines_de_semana != 1 else ''} de fin de semana"
        )
    if feriados:
        lista = ", ".join(f"{dia:%d-%m} {nombre}" for dia, nombre in feriados)
        partes.append(f"{len(feriados)} feriado{'s' if len(feriados) != 1 else ''} ({lista})")
    if not partes:
        return ""
    return " No se contaron " + " y ".join(partes) + "."


def justificar(
    resultado: str,
    envio: Envio,
    regla: ReglaSLA | None,
    transportista: str | None,
    fecha_corte: datetime | None,
    fines_de_semana: int,
    feriados: list[tuple],
) -> str:
    """Explicación en palabras de por qué la guía quedó con ese resultado."""
    dias = _texto_dias_no_habiles(fines_de_semana, feriados)
    usadas = _horas(envio.horas_habiles_transcurridas)
    plazo = regla.horas_habiles_maximas if regla else None

    if resultado == PENDIENTE:
        return "El lote todavía no se audita."
    if resultado == DATOS_INVALIDOS:
        return f"No se auditó. {envio.observacion or 'Los datos de la guía no son consistentes.'}"
    if resultado == SIN_REGLA:
        return (
            f"No se auditó: el transportista {transportista or '(sin nombre)'} no tiene una regla"
            " SLA activa, así que no hay un plazo contra el cual comparar."
        )
    if envio.fecha_limite is None:  # lote auditado antes de la migración 0002
        estado = {CUMPLIDO: "Entregada en plazo", INCUMPLIDO: "Entregada fuera de plazo"}.get(
            resultado, "El archivo no registra entrega"
        )
        return f"{estado}. Vuelva a auditar el lote para ver la fecha límite y el cálculo."
    if resultado == CUMPLIDO:
        return (
            f"Entregada el {_fecha(envio.fecha_entrega)}, antes de la fecha límite"
            f" ({_fecha(envio.fecha_limite)}). Usó {usadas} de las {plazo} horas hábiles"
            f" permitidas.{dias}"
        )
    if resultado == INCUMPLIDO:
        return (
            f"Entregada el {_fecha(envio.fecha_entrega)}, después de la fecha límite"
            f" ({_fecha(envio.fecha_limite)}). Usó {usadas} horas hábiles de {plazo} permitidas:"
            f" {_horas(envio.horas_atraso)} horas hábiles de atraso. Multa según la regla SLA:"
            f" {_pesos(envio.monto_multa)}.{dias}"
        )
    if resultado == VENCIDA_SIN_ENTREGA:
        return (
            f"El archivo no registra entrega. El plazo venció el {_fecha(envio.fecha_limite)};"
            f" a la fecha de corte ({_fecha(fecha_corte)}) llevaba {usadas} horas hábiles,"
            f" {_horas(envio.horas_atraso)} más de las {plazo} permitidas. No se aplica multa"
            " porque no hay registro de entrega: corresponde consultar al transportista si la"
            f" encomienda llegó.{dias}"
        )
    # EN_TRANSITO
    return (
        f"El archivo no registra entrega, pero el plazo aún no vence: a la fecha de corte"
        f" ({_fecha(fecha_corte)}) llevaba {usadas} de {plazo} horas hábiles. Vence el"
        f" {_fecha(envio.fecha_limite)}.{dias}"
    )


def listar_envios(db: Session, lote: LoteAuditoria) -> list[EnvioSalida]:
    """Todas las guías de un lote con su resultado y la justificación del cálculo."""
    auditado = lote_fue_auditado(lote)
    reglas: dict[str | None, ReglaSLA | None] = {}  # una consulta por transportista
    salida = []
    for envio, transportista in _envios_con_transportista(db, lote.id):
        resultado = clasificar_envio(envio, auditado)
        nombre = _nombre_transportista(envio, transportista)
        if envio.transportista_id not in reglas:
            reglas[envio.transportista_id] = (
                buscar_regla_sla_activa(db, envio.transportista_id)
                if envio.transportista_id
                else None
            )
        regla = reglas[envio.transportista_id] if resultado != PENDIENTE else None

        # Días que no se contaron: hasta la entrega o, si no hay, hasta el corte.
        fin = envio.fecha_entrega or (lote.fecha_corte if resultado != PENDIENTE else None)
        fines_de_semana, feriados = (
            dias_no_habiles(envio.fecha_despacho, fin)
            if fin and resultado not in (DATOS_INVALIDOS, SIN_REGLA)
            else (0, [])
        )
        con_atraso = resultado in (CUMPLIDO, INCUMPLIDO, VENCIDA_SIN_ENTREGA)
        salida.append(
            EnvioSalida(
                id=envio.id,
                numero_guia=envio.numero_guia,
                transportista=nombre,
                fecha_despacho=envio.fecha_despacho,
                fecha_entrega=envio.fecha_entrega,
                destino=envio.destino,
                valor_declarado=envio.valor_declarado,
                resultado=resultado,
                horas_atraso=envio.horas_atraso if con_atraso else None,
                monto_multa=envio.monto_multa if resultado in (CUMPLIDO, INCUMPLIDO) else None,
                entregada=envio.fecha_entrega is not None,
                fecha_limite=envio.fecha_limite,
                horas_habiles_permitidas=regla.horas_habiles_maximas if regla else None,
                horas_habiles_transcurridas=envio.horas_habiles_transcurridas,
                dias_fin_de_semana=fines_de_semana,
                feriados=[Feriado(fecha=dia, nombre=n) for dia, n in feriados],
                justificacion=justificar(
                    resultado, envio, regla, nombre, lote.fecha_corte, fines_de_semana, feriados
                ),
            )
        )
    return salida
