"""
IA generativa de LogiSLA: resumen ejecutivo de un lote auditado (HU-17).

Sigue las mismas reglas que la carta de reclamo (ver app/ia_cartas.py):
  - Las cifras las calcula el motor de auditoría; la IA solo redacta.
  - A la IA solo va un resumen agregado por transportista: nunca números de
    guía, destinos ni datos de clientes.
  - Redacta Gemini (principal) y, si no está disponible, Claude (respaldo).
    Ver app/ia_proveedores.py.
  - El sistema revisa la respuesta: si no trae el monto total exacto o
    menciona un monto en pesos que el sistema no calculó, se descarta.
  - Si ninguna IA entrega un texto válido, se usa una plantilla y se informa el motivo.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from app import ia_proveedores
from app.ia_cartas import ORIGEN_IA, ORIGEN_PLANTILLA, _decimal, fecha_larga, pesos
from app.ia_proveedores import ConfiguracionIA

registrador = logging.getLogger(__name__)

_MONTO_EN_PESOS = re.compile(r"\$\s?(\d{1,3}(?:[.,]\d{3})+|\d+)")


@dataclass(frozen=True)
class ResultadoTransportista:
    """Resultado de un transportista dentro del lote, para el resumen ejecutivo."""

    nombre: str
    auditadas: int  # en plazo + fuera de plazo
    incumplidas: int
    monto: float
    multa_unitaria: Optional[float]
    sin_regla: int

    @property
    def cumplimiento(self) -> Optional[float]:
        """Porcentaje de guías auditadas que llegaron en plazo."""
        if self.auditadas <= 0:
            return None
        return 100.0 * (self.auditadas - self.incumplidas) / self.auditadas


@dataclass(frozen=True)
class DatosResumen:
    """Cifras del lote completo que usa el resumen ejecutivo."""

    empresa_nombre: str
    nombre_archivo: str
    total_guias: int
    cumplidas: int
    incumplidas: int
    en_transito: int  # sin entrega, dentro del plazo
    sin_regla: int
    monto_total: float
    periodo: Optional[tuple[date, date]]
    transportistas: list[ResultadoTransportista]  # ordenados de mayor a menor monto
    vencidas_sin_entrega: int = 0  # sin entrega y con el plazo vencido (sin multa)
    datos_invalidos: int = 0  # guías con datos que no permiten auditarlas

    @property
    def auditadas(self) -> int:
        """Guías auditadas (en plazo + fuera de plazo)."""
        return self.cumplidas + self.incumplidas

    @property
    def cumplimiento(self) -> Optional[float]:
        """Porcentaje de guías auditadas que llegaron en plazo."""
        if self.auditadas <= 0:
            return None
        return 100.0 * self.cumplidas / self.auditadas

    @property
    def con_multas(self) -> list[ResultadoTransportista]:
        """Transportistas que tienen al menos una guía fuera de plazo."""
        return [t for t in self.transportistas if t.incumplidas > 0]


@dataclass(frozen=True)
class ResultadoResumen:
    """Resumen generado y de dónde salió el texto (qué IA o la plantilla)."""

    texto: str
    origen: str  # ORIGEN_IA | ORIGEN_PLANTILLA
    proveedor: Optional[str]  # "Gemini" o "Claude" (solo si origen es IA)
    modelo: Optional[str]
    motivo_plantilla: Optional[str]
    aviso_respaldo: Optional[str] = None  # por qué no lo redactó la IA principal


def _porcentaje(valor: Optional[float]) -> str:
    """Porcentaje con un decimal, o 'sin datos'."""
    return "sin datos" if valor is None else f"{_decimal(valor)} %"


def _guias(n: int) -> str:
    """'1 guía' o 'N guías'."""
    return f"{n} guía" if n == 1 else f"{n} guías"


def _lista_natural(elementos: list[str]) -> str:
    """Une una lista en español: ['a', 'b', 'c'] -> 'a, b y c'."""
    if len(elementos) <= 1:
        return "".join(elementos)
    return ", ".join(elementos[:-1]) + " y " + elementos[-1]


def construir_prompt(datos: DatosResumen) -> str:
    """Instrucciones para la IA con solo cifras agregadas (sin guías ni destinos)."""
    lineas = [
        f"- Archivo auditado: {datos.nombre_archivo}.",
        (
            f"- Guías del lote: {datos.total_guias}; auditadas: {datos.auditadas}; "
            f"en plazo: {datos.cumplidas}; fuera de plazo: {datos.incumplidas}; "
            f"en tránsito dentro del plazo: {datos.en_transito}; "
            f"sin entrega y con el plazo vencido (sin multa): {datos.vencidas_sin_entrega}; "
            f"sin regla SLA: {datos.sin_regla}; con datos a revisar: {datos.datos_invalidos}."
        ),
        f"- Cumplimiento del SLA: {_porcentaje(datos.cumplimiento)}.",
        f"- Monto total de multas por reclamar: {pesos(datos.monto_total)}.",
    ]
    if datos.periodo:
        lineas.append(
            f"- Período de despacho: del {fecha_larga(datos.periodo[0])} "
            f"al {fecha_larga(datos.periodo[1])}."
        )
    lineas.append("- Resultado por transportista:")
    for t in datos.transportistas:
        if t.auditadas == 0:
            lineas.append(
                f"  * {t.nombre}: sin guías auditadas ({_guias(t.sin_regla)} sin regla SLA)."
            )
        else:
            lineas.append(
                f"  * {t.nombre}: {t.incumplidas} de {t.auditadas} fuera de plazo, "
                f"cumplimiento {_porcentaje(t.cumplimiento)}, multas {pesos(t.monto)}."
            )

    return "\n".join(
        [
            (
                f"Eres analista de operaciones logísticas de la empresa {datos.empresa_nombre}."
                " Redacta en español de Chile un RESUMEN EJECUTIVO para la gerencia sobre la"
                " auditoría de cumplimiento de plazos (SLA) de los transportistas."
            ),
            "",
            (
                "Datos verificados por el sistema LogiSLA (úsalos tal cual, sin recalcular ni"
                " redondear):"
            ),
            *lineas,
            "",
            "Reglas:",
            (
                "1. Tres párrafos breves: resultado general; qué transportistas concentran las"
                " multas; y una recomendación concreta (por ejemplo, enviar las cartas de reclamo y"
                " revisar el servicio del transportista con más atrasos)."
            ),
            (
                f"2. Menciona el monto total ({pesos(datos.monto_total)}) y el cumplimiento "
                f"({_porcentaje(datos.cumplimiento)}), escritos exactamente así."
            ),
            (
                "3. No inventes nada: ni nombres de personas, ni cifras distintas a las entregadas,"
                " ni causas de los atrasos."
            ),
            (
                "4. Entre 90 y 170 palabras, en texto plano: sin markdown, sin títulos, sin viñetas"
                " y sin asteriscos."
            ),
        ]
    )


def revisar_respuesta_ia(texto: str, datos: DatosResumen) -> Optional[str]:
    """None si el texto de la IA se puede usar; si no, el motivo para descartarlo."""
    if len(texto) < 200:
        return "La respuesta de la IA fue demasiado corta."

    total = round(datos.monto_total)
    formas = {f"{total:,}".replace(",", "."), f"{total:,}", str(total)}
    if not any(re.search(rf"(?<![\d.,]){re.escape(f)}(?![\d]|[.,]\d)", texto) for f in formas):
        return "La respuesta de la IA no incluyó el monto total exacto calculado por el sistema."

    permitidos = {total}
    for t in datos.transportistas:
        permitidos.add(round(t.monto))
        if t.multa_unitaria is not None:
            permitidos.add(round(t.multa_unitaria))
    for encontrado in _MONTO_EN_PESOS.findall(texto):
        if int(re.sub(r"[.,]", "", encontrado)) not in permitidos:
            return (
                "La respuesta de la IA mencionó un monto que el sistema no calculó"
                f" (${encontrado})."
            )
    return None


def resumen_plantilla(datos: DatosResumen) -> str:
    """Resumen sin IA: plantilla fija con las cifras del sistema."""
    periodo = (
        f" despachadas entre el {fecha_larga(datos.periodo[0])} y el"
        f" {fecha_larga(datos.periodo[1])}"
        if datos.periodo
        else ""
    )
    pendientes = []
    if datos.vencidas_sin_entrega:
        pendientes.append(
            f"{_guias(datos.vencidas_sin_entrega)} sin registro de entrega y con el plazo vencido"
        )
    if datos.en_transito:
        pendientes.append(f"{_guias(datos.en_transito)} en tránsito dentro del plazo")
    if datos.sin_regla:
        pendientes.append(f"{_guias(datos.sin_regla)} sin regla SLA")
    if datos.datos_invalidos:
        pendientes.append(f"{_guias(datos.datos_invalidos)} con datos a revisar")
    nota = f" Quedaron fuera de la auditoría {_lista_natural(pendientes)}." if pendientes else ""

    parrafo1 = (
        f"Se auditaron {datos.auditadas} de las {datos.total_guias} guías del archivo "
        f"{datos.nombre_archivo}{periodo}. El cumplimiento del SLA fue de "
        f"{_porcentaje(datos.cumplimiento)}: {datos.cumplidas} guías llegaron en plazo y "
        f"{datos.incumplidas} fuera de plazo.{nota}"
    )

    con_multas = datos.con_multas
    if not con_multas:
        parrafo2 = "Ningún transportista registró entregas fuera de plazo en este lote."
        parrafo3 = (
            "No hay multas que reclamar. Se recomienda mantener el monitoreo en los próximos"
            " períodos."
        )
    else:
        detalle = _lista_natural(
            [f"{t.nombre} ({_guias(t.incumplidas)}, {pesos(t.monto)})" for t in con_multas]
        )
        parrafo2 = (
            f"El monto total de multas por reclamar asciende a {pesos(datos.monto_total)}, "
            f"repartido entre {detalle}."
        )
        peor = min(
            (t for t in con_multas if t.cumplimiento is not None),
            key=lambda t: t.cumplimiento,
            default=con_multas[0],
        )
        parrafo3 = (
            "Se recomienda enviar las cartas de reclamo a cada transportista con multas y revisar "
            f"el servicio de {peor.nombre}, que tuvo el menor cumplimiento del lote "
            f"({_porcentaje(peor.cumplimiento)})."
        )
    if datos.vencidas_sin_entrega:
        parrafo3 += (
            f" Además, conviene consultar a los transportistas por las"
            f" {_guias(datos.vencidas_sin_entrega)} sin registro de entrega cuyo plazo ya venció."
        )
    return "\n\n".join([parrafo1, parrafo2, parrafo3])


def generar_resumen(
    datos: DatosResumen,
    usar_ia: bool = True,
    config: Optional[ConfiguracionIA] = None,
) -> ResultadoResumen:
    """Intenta con la IA principal y luego con la de respaldo; si no, usa la plantilla."""
    if not usar_ia:
        motivo = "Se pidió el resumen con plantilla (sin IA)."
    else:
        redaccion = ia_proveedores.redactar(
            construir_prompt(datos),
            lambda texto: revisar_respuesta_ia(texto, datos),
            config,
        )
        if redaccion.texto is not None:
            return ResultadoResumen(
                texto=redaccion.texto,
                origen=ORIGEN_IA,
                proveedor=redaccion.proveedor,
                modelo=redaccion.modelo,
                motivo_plantilla=None,
                aviso_respaldo=redaccion.motivo,
            )
        motivo = redaccion.motivo
        registrador.warning("Resumen ejecutivo generado con plantilla: %s", motivo)
    return ResultadoResumen(
        texto=resumen_plantilla(datos),
        origen=ORIGEN_PLANTILLA,
        proveedor=None,
        modelo=None,
        motivo_plantilla=motivo,
    )
