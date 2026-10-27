"""
Motor de auditoría (Sprint 2: "Motor de Auditoría Core y Pruebas Unitarias").

Toma los Envio que Sprint 1 dejó cargados con incumplio_sla=NULL y
calcula, para cada uno, si el transportista incumplió su SLA y cuánto le
corresponde pagar. Es 100% determinístico (Pandas ya se usó en la ingesta;
acá usamos workalendar para el calendario chileno) — sin llamadas a
ninguna API de IA, tal como quedó documentado en el argumento académico
del proyecto (ver LogiSLA_Propuesta_IA): el cálculo de negocio es de
autoría propia, la IA (Sprint 4) sólo redactará texto a partir de estos
resultados ya calculados.

Decisiones de diseño:
- Horario hábil: 09:00 a 18:00 (9 horas hábiles por día), de lunes a
  viernes, excluyendo feriados chilenos (workalendar.america.Chile).
  No hay un horario definido en las bases del proyecto, así que se fijó
  este estándar razonable para jornada laboral en Chile.
- `horas_atraso` es el atraso *por sobre* el límite del SLA (horas
  hábiles reales - horas hábiles permitidas), no el tránsito total. Un
  envío a tiempo queda en 0.0, nunca negativo.
- `monto_multa` se calcula como monto fijo por incumplimiento
  (ReglaSLA.multa_por_incumplimiento), no como porcentaje del valor
  declarado: `valor_declarado` es un campo opcional que muchos envíos no
  traen, así que un cálculo porcentual dejaría la multa en 0 o indefinida
  para una parte importante de los datos reales.
- Un Envio sin fecha_entrega (todavía en tránsito) no se audita: se deja
  tal cual (incumplio_sla=NULL) hasta que se sepa cuándo llegó, en vez de
  compararlo contra la hora actual — así el resultado de un lote no
  cambia según el momento en que se ejecuta la auditoría.
- Un Envio cuyo transportista no tiene una ReglaSLA activa tampoco se
  audita (no hay contra qué comparar) — se cuenta aparte para que el
  resumen del lote sea transparente sobre qué quedó sin auditar y por qué.
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session
from workalendar.america import Chile

from app.models import LoteAuditoria, EstadoLote, Transportista, Envio, ReglaSLA

INICIO_JORNADA = time(9, 0)
FIN_JORNADA = time(18, 0)

_CALENDARIO_CL = Chile()


def horas_habiles_entre(inicio: datetime, fin: datetime) -> float:
    """
    Horas hábiles entre `inicio` y `fin`, considerando jornada 09:00-18:00
    de lunes a viernes y feriados chilenos (fines de semana y feriados
    aportan 0 horas, sin importar cuántos días de calendario abarquen).

    Si alguna fecha cae fuera del horario hábil (antes de las 9 o después
    de las 18), se recorta al horario de ese día en vez de contarla como
    tiempo hábil. Devuelve 0.0 si `fin` no es posterior a `inicio`.
    """
    if inicio is None or fin is None or fin <= inicio:
        return 0.0

    # Los timestamps pueden venir con tz (columnas DateTime(timezone=True));
    # se normalizan a "naive" para poder combinarlos con time() sin que
    # Python reviente comparando aware vs naive.
    if inicio.tzinfo is not None:
        inicio = inicio.replace(tzinfo=None)
    if fin.tzinfo is not None:
        fin = fin.replace(tzinfo=None)

    segundos_totales = 0.0
    fecha_actual = inicio.date()   # solo la fecha (sin hora) del despacho
    fecha_fin = fin.date()         # solo la fecha (sin hora) de la entrega
    un_dia = timedelta(days=1)

    # La idea central: recorremos día por día desde el día del despacho
    # hasta el día de la entrega (inclusive). Por cada día que SÍ es
    # hábil, sumamos cuántas horas de la "ventana hábil" de ese día
    # (09:00-18:00) quedan realmente cubiertas por el envío. Un envío que
    # dura varios días solo aporta horas en los tramos hábiles de cada
    # día — las noches, fines de semana y feriados nunca suman.
    while fecha_actual <= fecha_fin:
        if _CALENDARIO_CL.is_working_day(fecha_actual):
            # Ventana hábil completa de este día en particular, como
            # datetime (ej. 2025-11-10 09:00 y 2025-11-10 18:00).
            ventana_inicio = datetime.combine(fecha_actual, INICIO_JORNADA)
            ventana_fin = datetime.combine(fecha_actual, FIN_JORNADA)

            # ¿Cuál es el límite inferior real para ESTE día?
            # - Si este es el día del despacho, no puede ser antes de la
            #   hora exacta de despacho (`inicio`) — por eso max(...).
            #   Ej: si despachó a las 16:00, la ventana de ese día
            #   empieza a las 16:00, no a las 09:00.
            # - Para cualquier día intermedio (no es el día de despacho),
            #   el límite inferior es simplemente la apertura (09:00),
            #   porque el envío ya estaba "en curso" desde antes.
            limite_inferior = max(ventana_inicio, inicio) if fecha_actual == inicio.date() else ventana_inicio

            # Mismo razonamiento para el límite superior, pero con la
            # entrega: si este es el día de la entrega, no puede pasar de
            # la hora exacta de entrega (`fin`); si es un día intermedio,
            # llega hasta el cierre (18:00) porque el envío sigue en curso.
            limite_superior = min(ventana_fin, fin) if fecha_actual == fecha_fin else ventana_fin

            # Si tras recortar el límite superior quedó por delante del
            # inferior, ese día aporta horas; si no (ej. el despacho fue
            # a las 20:00, después del cierre, y max() lo dejó en 20:00
            # mientras el límite superior quedó en 18:00), ese día aporta 0.
            if limite_superior > limite_inferior:
                segundos_totales += (limite_superior - limite_inferior).total_seconds()
        fecha_actual += un_dia  # pasamos al día calendario siguiente

    return round(segundos_totales / 3600, 2)


@dataclass
class ResultadoAuditoriaEnvio:
    incumplio_sla: bool
    horas_atraso: float
    monto_multa: float


@dataclass
class ResumenAuditoriaLote:
    lote_id: str
    total_envios: int
    envios_auditados: int
    envios_incumplidos: int
    envios_cumplidos: int
    omitidos_sin_regla: int
    omitidos_sin_fecha_entrega: int
    monto_multa_total: float


def obtener_o_crear_transportista(db: Session, nombre_transportista_original: str | None) -> Transportista | None:
    """
    Busca el Transportista por nombre (case-insensitive) o lo crea si es
    la primera vez que aparece ese transportista en un archivo cargado.
    Devuelve None si no hay nombre de transportista (no debería pasar:
    nombre_transportista es un campo obligatorio en la ingesta, pero se
    cubre el caso igual para no reventar la auditoría por una fila rara).
    """
    if not nombre_transportista_original or not nombre_transportista_original.strip():
        return None

    nombre = nombre_transportista_original.strip()
    transportista = db.query(Transportista).filter(func.lower(Transportista.nombre) == nombre.lower()).first()
    if transportista:
        return transportista

    transportista = Transportista(nombre=nombre)
    db.add(transportista)
    db.flush()  # para tener transportista.id disponible antes del commit del lote
    return transportista


def buscar_regla_sla_activa(db: Session, transportista_id: str) -> ReglaSLA | None:
    """
    Regla SLA activa a usar para un Transportista. Envio no guarda
    tipo_servicio (ver models.py), así que se prioriza la regla genérica
    (tipo_servicio is NULL) cuando el transportista tiene más de una
    regla activa; si no existe una genérica, se usa la primera regla
    activa que haya.
    """
    if not transportista_id:
        return None
    return (
        db.query(ReglaSLA)
        .filter(ReglaSLA.transportista_id == transportista_id, ReglaSLA.activa.is_(True))
        .order_by(ReglaSLA.tipo_servicio.isnot(None))
        .first()
    )


def auditar_envio(envio: Envio, regla_sla: ReglaSLA) -> ResultadoAuditoriaEnvio:
    """
    Compara las horas hábiles reales de tránsito (fecha_despacho ->
    fecha_entrega) contra el límite de la regla SLA del transportista.
    Requiere que envio.fecha_entrega no sea None (se valida antes de
    llamar a esta función, en ejecutar_auditoria_lote).
    """
    horas_reales = horas_habiles_entre(envio.fecha_despacho, envio.fecha_entrega)

    if horas_reales > regla_sla.horas_habiles_maximas:
        atraso = round(horas_reales - regla_sla.horas_habiles_maximas, 2)
        return ResultadoAuditoriaEnvio(
            incumplio_sla=True,
            horas_atraso=atraso,
            monto_multa=regla_sla.multa_por_incumplimiento,
        )

    return ResultadoAuditoriaEnvio(incumplio_sla=False, horas_atraso=0.0, monto_multa=0.0)


def ejecutar_auditoria_lote(db: Session, lote: LoteAuditoria) -> ResumenAuditoriaLote:
    """
    Corre el motor sobre todos los Envio de un LoteAuditoria: resuelve
    (o crea) el Transportista de cada envío a partir de
    nombre_transportista_original, busca su ReglaSLA activa, y si hay
    fecha de entrega calcula el incumplimiento y la multa. Deja el lote
    en estado COMPLETADO al final, con fecha_procesado seteada. Se puede
    volver a correr sobre el mismo lote (ej. si cambiaron las reglas SLA)
    — es idempotente, siempre recalcula todo desde cero.
    """
    envios = db.query(Envio).filter(Envio.lote_auditoria_id == lote.id).all()

    # Contadores para el resumen final. Cada Envio del lote cae en
    # exactamente una de estas categorías al terminar el for.
    auditados = incumplidos = cumplidos = 0
    omitidos_sin_regla = omitidos_sin_entrega = 0
    multa_total = 0.0

    for envio in envios:
        # Paso 1: asegurar el Transportista. Si el envío ya viene
        # vinculado (transportista_id no nulo, ej. de una corrida
        # anterior) no lo tocamos; si no, lo resolvemos/creamos a partir
        # del texto libre que dejó la ingesta (nombre_transportista_original,
        # ej. "chilexpress" o "CHILEXPRESS").
        if envio.transportista_id is None:
            transportista = obtener_o_crear_transportista(db, envio.nombre_transportista_original)
            envio.transportista_id = transportista.id if transportista else None

        # Paso 2: sin fecha de entrega no hay nada que calcular todavía
        # (el envío sigue en tránsito) — se deja para la próxima corrida.
        if envio.fecha_entrega is None:
            omitidos_sin_entrega += 1
            continue

        # Paso 3: sin una ReglaSLA activa para el transportista no hay
        # límite contra el cual comparar, así que tampoco se audita.
        regla_sla = buscar_regla_sla_activa(db, envio.transportista_id) if envio.transportista_id else None
        if regla_sla is None:
            omitidos_sin_regla += 1
            continue

        # Paso 4: ya hay transportista + regla + fecha de entrega -> se
        # puede auditar de verdad. auditar_envio() hace el cálculo puro
        # (sin tocar la BD) y acá se escribe el resultado en el Envio.
        resultado = auditar_envio(envio, regla_sla)
        envio.incumplio_sla = resultado.incumplio_sla
        envio.horas_atraso = resultado.horas_atraso
        envio.monto_multa = resultado.monto_multa

        auditados += 1
        if resultado.incumplio_sla:
            incumplidos += 1
            multa_total += resultado.monto_multa
        else:
            cumplidos += 1

    # Todos los Envio ya quedaron actualizados en memoria (SQLAlchemy los
    # sigue trackeando desde el db.query() de arriba); un solo commit al
    # final graba todo junto, incluido el lote.
    lote.estado = EstadoLote.COMPLETADO
    lote.fecha_procesado = datetime.utcnow()
    db.commit()

    return ResumenAuditoriaLote(
        lote_id=lote.id,
        total_envios=len(envios),
        envios_auditados=auditados,
        envios_incumplidos=incumplidos,
        envios_cumplidos=cumplidos,
        omitidos_sin_regla=omitidos_sin_regla,
        omitidos_sin_fecha_entrega=omitidos_sin_entrega,
        monto_multa_total=round(multa_total, 2),
    )
