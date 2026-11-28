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
- Fecha límite: para cada guía se calcula la fecha y hora exacta en que
  vence su plazo (despacho + horas hábiles de la regla SLA), para mostrar
  y justificar el resultado.
- Fecha de corte: la auditoría registra el momento en que se ejecutó
  (LoteAuditoria.fecha_corte). Una guía sin fecha de entrega se evalúa
  contra ese momento:
    * si su plazo aún no vence  -> EN_TRANSITO (dentro del plazo);
    * si su plazo ya venció     -> VENCIDA_SIN_ENTREGA: alerta para consultar
      al transportista, SIN multa, porque no hay prueba de cuándo (ni si)
      llegó. La multa solo se cobra con una entrega registrada fuera de plazo.
  Como la fecha de corte queda guardada, el resultado de un lote no cambia
  al consultarlo después; solo cambia si se vuelve a auditar.
- Control de datos: no se audita (ni se multa) una guía con datos que no
  permiten un resultado confiable -> DATOS_INVALIDOS, con su motivo:
    * entrega anterior al despacho;
    * despacho o entrega posterior a la fecha de corte (fecha futura);
    * número de guía repetido en el archivo (se audita una sola vez, para
      no cobrar dos veces la misma multa).
- Un Envio cuyo transportista no tiene una ReglaSLA activa no se audita
  (no hay contra qué comparar) -> SIN_REGLA, contado aparte para que el
  resumen del lote sea transparente sobre qué quedó sin auditar y por qué.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session
from workalendar.america import Chile

from app.models import LoteAuditoria, EstadoLote, Transportista, Envio, ReglaSLA

INICIO_JORNADA = time(9, 0)
FIN_JORNADA = time(18, 0)

_CALENDARIO_CL = Chile()

# Resultado final de cada guía (se guarda en Envio.resultado).
CUMPLIDO = "CUMPLIDO"  # entregada dentro del plazo
INCUMPLIDO = "INCUMPLIDO"  # entregada fuera del plazo: lleva multa
EN_TRANSITO = "EN_TRANSITO"  # sin entrega, pero su plazo aún no vence
VENCIDA_SIN_ENTREGA = "VENCIDA_SIN_ENTREGA"  # sin entrega y con el plazo vencido: alerta
SIN_REGLA = "SIN_REGLA"  # su transportista no tiene regla SLA activa
DATOS_INVALIDOS = "DATOS_INVALIDOS"  # sus datos no permiten auditarla (ver observacion)
PENDIENTE = "PENDIENTE"  # el lote todavía no se audita

# Nombres en español de los feriados que entrega workalendar (en inglés).
_FERIADOS_ES = {
    "New year": "Año Nuevo",
    "Good Friday": "Viernes Santo",
    "Easter Saturday": "Sábado Santo",
    "Labour Day": "Día del Trabajo",
    "Navy Day": "Día de las Glorias Navales",
    "Indigenous Peoples Day": "Día Nacional de los Pueblos Indígenas",
    "Saint Peter and Saint Paul": "San Pedro y San Pablo",
    "Our Lady of Mount Carmel": "Virgen del Carmen",
    "Assumption of Mary to Heaven": "Asunción de la Virgen",
    "National holiday": "Fiestas Patrias",
    "Independence Day": "Independencia Nacional",
    "Army holiday": "Día de las Glorias del Ejército",
    "Reformation Day": "Día de las Iglesias Evangélicas y Protestantes",
    "All Saints Day": "Día de Todos los Santos",
    "Immaculate Conception": "Inmaculada Concepción",
    "Christmas Day": "Navidad",
    "Banking Holiday": "Feriado bancario",
}


def horas_habiles_entre(inicio: datetime, fin: datetime) -> float:
    """
    Horas hábiles entre `inicio` y `fin`, considerando jornada 09:00-18:00
    de lunes a viernes y feriados chilenos (fines de semana y feriados
    aportan 0 horas, sin importar cuántos días de calendario abarquen).

    Si alguna fecha cae fuera del horario hábil (antes de las 9 o después
    de las 18), se recorta al horario de ese día en vez de contarla como
    tiempo hábil. Devuelve 0.0 si `fin` no es posterior a `inicio`.
    """
    if inicio is None or fin is None:
        return 0.0

    # Los timestamps pueden venir con tz (columnas DateTime(timezone=True));
    # se normalizan a "naive" para poder combinarlos con time() sin que
    # Python reviente comparando aware vs naive.
    if inicio.tzinfo is not None:
        inicio = inicio.replace(tzinfo=None)
    if fin.tzinfo is not None:
        fin = fin.replace(tzinfo=None)
    if fin <= inicio:
        return 0.0

    segundos_totales = 0.0
    fecha_actual = inicio.date()  # solo la fecha (sin hora) del despacho
    fecha_fin = fin.date()  # solo la fecha (sin hora) de la entrega
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
            limite_inferior = (
                max(ventana_inicio, inicio) if fecha_actual == inicio.date() else ventana_inicio
            )

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


def _sin_zona(fecha: datetime | None) -> datetime | None:
    """Quita la zona horaria (las fechas se comparan como hora local de Chile)."""
    if fecha is not None and fecha.tzinfo is not None:
        return fecha.replace(tzinfo=None)
    return fecha


def sumar_horas_habiles(inicio: datetime, horas: float) -> datetime:
    """
    Fecha y hora en que se cumplen `horas` hábiles contadas desde `inicio`
    (la fecha límite del SLA). Usa la misma jornada que horas_habiles_entre():
    09:00 a 18:00, de lunes a viernes, sin feriados chilenos. Si el despacho
    fue fuera de horario, el plazo empieza a correr en la apertura siguiente.
    Ejemplo: despacho el viernes a las 16:00 con 24 horas hábiles de plazo
    -> 2 h el viernes, 9 h el lunes, 9 h el martes y 4 h el miércoles:
    vence el miércoles a las 13:00.
    """
    actual = _sin_zona(inicio)
    restante = timedelta(hours=horas)
    if restante <= timedelta(0):
        return actual

    while True:
        dia = actual.date()
        apertura = datetime.combine(dia, INICIO_JORNADA)
        cierre = datetime.combine(dia, FIN_JORNADA)
        if not _CALENDARIO_CL.is_working_day(dia) or actual >= cierre:
            # Día no hábil, o ya cerró la jornada: se pasa a la apertura del día siguiente.
            actual = datetime.combine(dia + timedelta(days=1), INICIO_JORNADA)
            continue
        if actual < apertura:
            actual = apertura
        disponible = cierre - actual
        if restante <= disponible:
            return actual + restante
        restante -= disponible
        actual = datetime.combine(dia + timedelta(days=1), INICIO_JORNADA)


def nombre_feriado(dia: date, nombre: str) -> str:
    """Nombre en español de un feriado de workalendar (si no está traducido, el original)."""
    if nombre == "Columbus Day":
        # workalendar usa este nombre para dos feriados chilenos distintos.
        return "Encuentro de Dos Mundos" if dia.month == 10 else "San Pedro y San Pablo"
    return _FERIADOS_ES.get(nombre, nombre)


def feriados_entre(desde: date, hasta: date) -> list[tuple[date, str]]:
    """Feriados chilenos entre dos fechas (ambas incluidas), con su nombre en español."""
    feriados = []
    for anio in range(desde.year, hasta.year + 1):
        for dia, nombre in _CALENDARIO_CL.holidays(anio):
            if desde <= dia <= hasta:
                feriados.append((dia, nombre_feriado(dia, nombre)))
    return sorted(feriados)


def dias_no_habiles(inicio: datetime, fin: datetime) -> tuple[int, list[tuple[date, str]]]:
    """
    Días que no cuentan para el plazo entre dos fechas (ambas incluidas):
    cantidad de días de fin de semana y lista de feriados (fecha, nombre).
    Sirve para justificar por qué las horas hábiles son menos que las de
    calendario.
    """
    inicio, fin = _sin_zona(inicio), _sin_zona(fin)
    if inicio is None or fin is None or fin < inicio:
        return 0, []
    feriados = [f for f in feriados_entre(inicio.date(), fin.date()) if f[0].weekday() < 5]
    fines_de_semana = 0
    dia = inicio.date()
    while dia <= fin.date():
        if dia.weekday() >= 5:
            fines_de_semana += 1
        dia += timedelta(days=1)
    return fines_de_semana, feriados


def _clave_guia(numero_guia: str) -> str:
    """Número de guía normalizado para detectar repetidos (sin espacios ni mayúsculas)."""
    return (numero_guia or "").strip().upper()


def problemas_de_datos(envios: list[Envio], fecha_corte: datetime) -> dict[str, str]:
    """
    Guías cuyos datos no permiten auditarlas, con el motivo en palabras.
    Devuelve {id del envío: motivo}. Revisa:
      - entrega anterior al despacho;
      - despacho o entrega posterior a la fecha de corte (fecha futura);
      - número de guía repetido: se audita una sola vez (la de despacho más
        antiguo) y las demás se marcan, para no cobrar dos veces la multa.
    """
    corte = _sin_zona(fecha_corte)
    problemas: dict[str, str] = {}

    for envio in envios:
        despacho, entrega = _sin_zona(envio.fecha_despacho), _sin_zona(envio.fecha_entrega)
        if entrega is not None and entrega < despacho:
            problemas[envio.id] = (
                f"La fecha de entrega ({entrega:%d-%m-%Y %H:%M}) es anterior a la de despacho "
                f"({despacho:%d-%m-%Y %H:%M}). Hay que corregir el dato en el archivo."
            )
        elif despacho > corte:
            problemas[envio.id] = (
                f"La fecha de despacho ({despacho:%d-%m-%Y %H:%M}) es posterior a la fecha de "
                "corte de la auditoría (fecha futura)."
            )
        elif entrega is not None and entrega > corte:
            problemas[envio.id] = (
                f"La fecha de entrega ({entrega:%d-%m-%Y %H:%M}) es posterior a la fecha de "
                "corte de la auditoría (fecha futura)."
            )

    por_guia: dict[str, list[Envio]] = {}
    for envio in envios:
        por_guia.setdefault(_clave_guia(envio.numero_guia), []).append(envio)
    for repetidas in por_guia.values():
        if len(repetidas) < 2:
            continue
        repetidas.sort(
            key=lambda e: (
                _sin_zona(e.fecha_despacho),
                _sin_zona(e.fecha_entrega) or datetime.max,
                e.id,
            )
        )
        for envio in repetidas[1:]:
            problemas.setdefault(
                envio.id,
                f"El número de guía aparece {len(repetidas)} veces en el archivo: se auditó solo "
                "una vez para no cobrar dos veces la misma multa.",
            )
    return problemas


@dataclass
class ResultadoAuditoriaEnvio:
    """Resultado de auditar una guía: si incumplió, horas de atraso y multa."""

    incumplio_sla: bool
    horas_atraso: float
    monto_multa: float


@dataclass
class ResumenAuditoriaLote:
    """Totales de la auditoría de un lote: guías procesadas, incumplidas y monto de multas."""

    lote_id: str
    total_envios: int
    envios_auditados: int
    envios_incumplidos: int
    envios_cumplidos: int
    omitidos_sin_regla: int
    omitidos_sin_fecha_entrega: int  # en tránsito + vencidas sin entrega
    monto_multa_total: float
    vencidas_sin_entrega: int = 0
    datos_invalidos: int = 0


def obtener_o_crear_transportista(
    db: Session, nombre_transportista_original: str | None
) -> Transportista | None:
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
    transportista = (
        db.query(Transportista).filter(func.lower(Transportista.nombre) == nombre.lower()).first()
    )
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


def ejecutar_auditoria_lote(
    db: Session, lote: LoteAuditoria, fecha_corte: datetime | None = None
) -> ResumenAuditoriaLote:
    """
    Corre el motor sobre todos los Envio de un LoteAuditoria y deja cada
    guía con su resultado justificado:
      1. resuelve (o crea) el Transportista a partir del nombre del archivo;
      2. revisa los datos (problemas_de_datos) -> DATOS_INVALIDOS;
      3. busca la ReglaSLA activa -> SIN_REGLA si no hay;
      4. calcula la fecha límite del plazo;
      5. con entrega: compara horas hábiles reales vs permitidas
         -> CUMPLIDO o INCUMPLIDO (con multa);
      6. sin entrega: compara contra la fecha de corte
         -> EN_TRANSITO o VENCIDA_SIN_ENTREGA (sin multa).

    `fecha_corte` es el momento de la auditoría (por defecto, ahora, en la
    hora local del computador que corre el backend). Se puede volver a
    correr sobre el mismo lote (ej. si cambiaron las reglas SLA): siempre
    recalcula todo desde cero.
    """
    fecha_corte = _sin_zona(fecha_corte) or datetime.now().replace(microsecond=0)
    envios = db.query(Envio).filter(Envio.lote_auditoria_id == lote.id).all()
    problemas = problemas_de_datos(envios, fecha_corte)

    # Contadores para el resumen final: cada guía cae en exactamente una categoría.
    conteo = {
        CUMPLIDO: 0,
        INCUMPLIDO: 0,
        EN_TRANSITO: 0,
        VENCIDA_SIN_ENTREGA: 0,
        SIN_REGLA: 0,
        DATOS_INVALIDOS: 0,
    }
    multa_total = 0.0
    reglas: dict[str, ReglaSLA | None] = {}  # una consulta por transportista, no por guía

    for envio in envios:
        # Se parte de cero: una corrida anterior no debe dejar restos.
        envio.incumplio_sla = None
        envio.horas_atraso = None
        envio.monto_multa = None
        envio.fecha_limite = None
        envio.horas_habiles_transcurridas = None
        envio.observacion = None

        # Paso 1: asegurar el Transportista (ej. "chilexpress" o "CHILEXPRESS").
        if envio.transportista_id is None:
            transportista = obtener_o_crear_transportista(db, envio.nombre_transportista_original)
            envio.transportista_id = transportista.id if transportista else None

        # Paso 2: datos que no permiten un resultado confiable.
        if envio.id in problemas:
            envio.resultado = DATOS_INVALIDOS
            envio.observacion = problemas[envio.id]
            conteo[DATOS_INVALIDOS] += 1
            continue

        # Paso 3: sin regla SLA activa no hay plazo contra el cual comparar.
        if envio.transportista_id not in reglas:
            reglas[envio.transportista_id] = (
                buscar_regla_sla_activa(db, envio.transportista_id)
                if envio.transportista_id
                else None
            )
        regla_sla = reglas[envio.transportista_id]
        if regla_sla is None:
            envio.resultado = SIN_REGLA
            conteo[SIN_REGLA] += 1
            continue

        # Paso 4: fecha límite del plazo (para mostrarla y justificar).
        maximo = regla_sla.horas_habiles_maximas
        envio.fecha_limite = sumar_horas_habiles(envio.fecha_despacho, maximo)

        if envio.fecha_entrega is not None:
            # Paso 5: entregada -> se compara contra el plazo; si se pasó, lleva multa.
            resultado = auditar_envio(envio, regla_sla)
            envio.horas_habiles_transcurridas = horas_habiles_entre(
                envio.fecha_despacho, envio.fecha_entrega
            )
            envio.incumplio_sla = resultado.incumplio_sla
            envio.horas_atraso = resultado.horas_atraso
            envio.monto_multa = resultado.monto_multa
            envio.resultado = INCUMPLIDO if resultado.incumplio_sla else CUMPLIDO
            multa_total += resultado.monto_multa
        else:
            # Paso 6: sin entrega -> se compara contra la fecha de corte, sin multa.
            horas = horas_habiles_entre(envio.fecha_despacho, fecha_corte)
            envio.horas_habiles_transcurridas = horas
            if horas > maximo:
                envio.resultado = VENCIDA_SIN_ENTREGA
                envio.horas_atraso = round(horas - maximo, 2)
            else:
                envio.resultado = EN_TRANSITO
        conteo[envio.resultado] += 1

    # Un solo commit al final graba todas las guías y el lote juntos.
    lote.estado = EstadoLote.COMPLETADO
    lote.fecha_procesado = datetime.utcnow()
    lote.fecha_corte = fecha_corte
    db.commit()

    return ResumenAuditoriaLote(
        lote_id=lote.id,
        total_envios=len(envios),
        envios_auditados=conteo[CUMPLIDO] + conteo[INCUMPLIDO],
        envios_incumplidos=conteo[INCUMPLIDO],
        envios_cumplidos=conteo[CUMPLIDO],
        omitidos_sin_regla=conteo[SIN_REGLA],
        omitidos_sin_fecha_entrega=conteo[EN_TRANSITO] + conteo[VENCIDA_SIN_ENTREGA],
        monto_multa_total=round(multa_total, 2),
        vencidas_sin_entrega=conteo[VENCIDA_SIN_ENTREGA],
        datos_invalidos=conteo[DATOS_INVALIDOS],
    )
