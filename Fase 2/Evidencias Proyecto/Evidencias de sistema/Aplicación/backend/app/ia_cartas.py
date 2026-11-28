"""
IA generativa de LogiSLA: redacción de la carta de reclamo al transportista.

Cómo funciona (en este orden):
  1. El motor de auditoría ya calculó qué guías llegaron fuera de plazo y
     cuánto es la multa. La IA NO calcula nada.
  2. Con esos resultados se arma un resumen agregado (cantidad de guías,
     montos, plazo, período). Solo ese resumen va a la IA: nunca números de
     guía, destinos ni datos de clientes.
  3. Gemini (IA principal) redacta el cuerpo de la carta. Si no
     está disponible (sin clave, sin cuota, sin respuesta), lo intenta
     Claude, si tiene clave (respaldo). Ver app/ia_proveedores.py.
  4. El sistema revisa cada respuesta: si no trae el monto total y la
     cantidad de guías exactos, o menciona un monto en pesos que el sistema
     no le entregó, se descarta y se prueba con el siguiente proveedor.
  5. Si ningún proveedor entrega un texto válido, se usa una plantilla fija.
     La carta se genera igual, y la respuesta indica de dónde salió el texto
     (origen "IA" con su proveedor, o "PLANTILLA") y por qué.
  6. Encabezado, firma y el anexo guía por guía siempre los arma el sistema
     con los datos de la base de datos.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from app import ia_proveedores
from app.ia_proveedores import ConfiguracionIA

registrador = logging.getLogger(__name__)


PLAZO_RESPUESTA_DIAS_HABILES = 10


ORIGEN_IA = "IA"
ORIGEN_PLANTILLA = "PLANTILLA"

MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


# ---------------------------------------------------------------------------
# Datos de la carta y formato
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GuiaIncumplida:
    """Una guía fuera de plazo, con los datos que van en el anexo de la carta."""

    numero_guia: str
    destino: Optional[str]
    fecha_despacho: datetime
    fecha_entrega: Optional[datetime]
    horas_atraso: Optional[float]
    monto_multa: Optional[float]


@dataclass(frozen=True)
class DatosCarta:
    """Todo lo necesario para armar la carta de reclamo de un transportista."""

    empresa_nombre: str
    empresa_rut: Optional[str]
    transportista: str
    nombre_archivo: str
    horas_habiles_maximas: Optional[int]
    multa_por_incumplimiento: Optional[float]
    guias_auditadas: int  # en plazo + fuera de plazo
    guias: list[GuiaIncumplida]  # solo las fuera de plazo
    fecha_emision: date

    @property
    def cantidad(self) -> int:
        """Cantidad de guías fuera de plazo."""
        return len(self.guias)

    @property
    def monto_total(self) -> float:
        """Suma de las multas de las guías fuera de plazo."""
        return round(sum(g.monto_multa or 0.0 for g in self.guias), 2)

    @property
    def periodo(self) -> tuple[date, date]:
        """Primera y última fecha de despacho de las guías fuera de plazo."""
        fechas = [g.fecha_despacho.date() for g in self.guias]
        return min(fechas), max(fechas)

    @property
    def porcentaje_cumplimiento(self) -> Optional[float]:
        """Porcentaje de guías auditadas que llegaron en plazo."""
        if self.guias_auditadas <= 0:
            return None
        return 100.0 * (self.guias_auditadas - self.cantidad) / self.guias_auditadas

    @property
    def atrasos(self) -> list[float]:
        """Horas de atraso de cada guía (las que tienen el dato)."""
        return [g.horas_atraso for g in self.guias if g.horas_atraso is not None]


def pesos(monto: Optional[float]) -> str:
    """15000 -> '$15.000' (formato chileno, sin decimales)."""
    return "$" + f"{round(monto or 0):,}".replace(",", ".")


def fecha_larga(d: date) -> str:
    """Fecha en palabras: date(2026, 11, 17) -> '17 de noviembre de 2026'."""
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _fecha_corta(d: Optional[datetime]) -> str:
    """Fecha y hora en formato dd-mm-aaaa hh:mm para el anexo."""
    return d.strftime("%d-%m-%Y %H:%M") if d else "-"


def _decimal(x: float) -> str:
    """Número con un decimal y coma: 10.5 -> '10,5'; 27.25 -> '27,3' (como la web)."""
    redondeado = Decimal(str(x)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{redondeado:.1f}".replace(".", ",")


def _cantidad_guias(n: int) -> str:
    """'1 guía' o 'N guías'."""
    return f"{n} guía" if n == 1 else f"{n} guías"


def _texto_plazo(datos: DatosCarta) -> str:
    """Frase con el plazo acordado (o una genérica si no hay regla)."""
    if datos.horas_habiles_maximas is None:
        return "el plazo acordado"
    return f"el plazo acordado de {datos.horas_habiles_maximas} horas hábiles"


def _texto_multa(datos: DatosCarta) -> str:
    """Frase con la multa pactada (o una genérica si no hay regla)."""
    if datos.multa_por_incumplimiento is None:
        return "la multa pactada por guía fuera de plazo"
    return f"la multa pactada de {pesos(datos.multa_por_incumplimiento)} por guía fuera de plazo"


# ---------------------------------------------------------------------------
# Prompt, revisión de la respuesta y plantilla
# ---------------------------------------------------------------------------


def construir_prompt(datos: DatosCarta) -> str:
    """Solo datos agregados: ningún número de guía, destino ni dato de clientes."""
    desde, hasta = datos.periodo
    pct = datos.porcentaje_cumplimiento
    atrasos = datos.atrasos
    lineas_datos = [
        (
            f"- Plazo acordado: {datos.horas_habiles_maximas} horas hábiles desde el despacho."
            if datos.horas_habiles_maximas is not None
            else "- Plazo acordado: según contrato."
        ),
        (
            f"- Multa pactada por guía fuera de plazo: {pesos(datos.multa_por_incumplimiento)}."
            if datos.multa_por_incumplimiento is not None
            else "- Multa pactada: según contrato."
        ),
        f"- Guías auditadas de este transportista: {datos.guias_auditadas}; "
        f"entregadas fuera de plazo: {datos.cantidad}"
        + (f"; cumplimiento del SLA: {_decimal(pct)} %." if pct is not None else "."),
        (
            f"- Período de despacho de las guías fuera de plazo: del {fecha_larga(desde)} al"
            f" {fecha_larga(hasta)}."
        ),
        f"- Monto total de multas a reclamar: {pesos(datos.monto_total)}.",
    ]
    if atrasos:
        lineas_datos.append(
            f"- Atraso promedio: {_decimal(sum(atrasos) / len(atrasos))} horas hábiles; "
            f"atraso máximo: {_decimal(max(atrasos))} horas hábiles."
        )
    lineas_datos.append(f"- Plazo para responder: {PLAZO_RESPUESTA_DIAS_HABILES} días hábiles.")

    return "\n".join(
        [
            (
                f"Eres el área de operaciones logísticas de la empresa {datos.empresa_nombre}."
                " Redacta en español de Chile, con tono formal, firme y cordial, el CUERPO de una"
                f" carta de reclamo dirigida al transportista {datos.transportista} por incumplir"
                " los plazos de entrega acordados (SLA)."
            ),
            "",
            (
                "Datos verificados por el sistema LogiSLA (úsalos tal cual, sin recalcular ni"
                " redondear):"
            ),
            *lineas_datos,
            "",
            "Reglas:",
            (
                '1. Escribe solo el cuerpo: empieza con "De nuestra consideración:" y termina con'
                " una frase de despedida. No escribas lugar, fecha, destinatario, referencia, firma"
                " ni anexo: el sistema los agrega."
            ),
            (
                f"2. Menciona la cantidad de guías fuera de plazo ({datos.cantidad}) y el monto"
                f" total ({pesos(datos.monto_total)}), escritos exactamente así."
            ),
            "3. Indica que el detalle guía por guía está en el anexo de la carta.",
            (
                "4. Solicita que el monto se descuente de la próxima factura o se emita una nota de"
                " crédito, y que respondan dentro del plazo indicado."
            ),
            (
                "5. No inventes nada: ni nombres de personas, ni números de contrato, ni cláusulas,"
                " ni leyes, ni montos distintos a los entregados."
            ),
            (
                "6. Entre 120 y 220 palabras, en 3 o 4 párrafos, en texto plano: sin markdown, sin"
                " viñetas y sin asteriscos."
            ),
        ]
    )


_MONTO_EN_PESOS = re.compile(r"\$\s?(\d{1,3}(?:[.,]\d{3})+|\d+)")


def revisar_respuesta_ia(texto: str, datos: DatosCarta) -> Optional[str]:
    """
    Devuelve None si el texto de la IA se puede usar, o el motivo para
    descartarlo. Es la "barrera" que impide que la IA cambie las cifras.
    """
    if len(texto) < 200:
        return "La respuesta de la IA fue demasiado corta."

    total = round(datos.monto_total)
    formas_total = {f"{total:,}".replace(",", "."), f"{total:,}", str(total)}
    if not any(
        re.search(rf"(?<![\d.,]){re.escape(f)}(?![\d]|[.,]\d)", texto) for f in formas_total
    ):
        return "La respuesta de la IA no incluyó el monto total exacto calculado por el sistema."

    if not re.search(rf"(?<![\d.,]){datos.cantidad}(?![\d]|[.,]\d)", texto):
        return "La respuesta de la IA no incluyó la cantidad exacta de guías fuera de plazo."

    permitidos = {total}
    if datos.multa_por_incumplimiento is not None:
        permitidos.add(round(datos.multa_por_incumplimiento))
    for encontrado in _MONTO_EN_PESOS.findall(texto):
        if int(re.sub(r"[.,]", "", encontrado)) not in permitidos:
            return (
                "La respuesta de la IA mencionó un monto que el sistema no calculó"
                f" (${encontrado})."
            )
    return None


def cuerpo_plantilla(datos: DatosCarta) -> str:
    """Cuerpo de la carta sin IA: plantilla fija con las cifras del sistema."""
    desde, hasta = datos.periodo
    if datos.cantidad == 1:
        hecho = f"1 guía entregada por {datos.transportista} superó {_texto_plazo(datos)}"
    else:
        hecho = (
            f"{datos.cantidad} guías entregadas por {datos.transportista} superaron"
            f" {_texto_plazo(datos)}"
        )
    pct = datos.porcentaje_cumplimiento
    cumplimiento = (
        f" De las {_cantidad_guias(datos.guias_auditadas)} auditadas de este transportista, "
        f"el cumplimiento del SLA fue de {_decimal(pct)} %."
        if pct is not None
        else ""
    )
    return "\n\n".join(
        [
            "De nuestra consideración:",
            (
                "Junto con saludar, les informamos que, tras auditar las guías despachadas entre"
                f" el {fecha_larga(desde)} y el {fecha_larga(hasta)}, {hecho}.{cumplimiento}"
            ),
            (
                f"De acuerdo con {_texto_multa(datos)}, el monto total a reclamar asciende a"
                f" {pesos(datos.monto_total)}. El detalle guía por guía, con sus fechas y horas"
                " hábiles de atraso, se encuentra en el anexo de esta carta."
            ),
            (
                "Solicitamos que este monto se descuente de la próxima factura o se emita la nota"
                " de crédito correspondiente, y que nos den respuesta dentro de"
                f" {PLAZO_RESPUESTA_DIAS_HABILES} días hábiles desde la recepción de esta carta."
            ),
            "Quedamos atentos a sus comentarios.\n\nSaludos cordiales.",
        ]
    )


def _anexo(datos: DatosCarta) -> str:
    """Tabla de texto con cada guía fuera de plazo, alineada en columnas."""
    encabezados = ["N° guía", "Destino", "Despacho", "Entrega", "Atraso (h háb.)", "Multa"]
    filas = [
        [
            g.numero_guia,
            g.destino or "-",
            _fecha_corta(g.fecha_despacho),
            _fecha_corta(g.fecha_entrega),
            _decimal(g.horas_atraso) if g.horas_atraso is not None else "-",
            pesos(g.monto_multa),
        ]
        for g in sorted(datos.guias, key=lambda g: (g.fecha_despacho, g.numero_guia))
    ]
    anchos = [max(len(str(f[i])) for f in [encabezados, *filas]) for i in range(len(encabezados))]
    derecha = {4, 5}  # columnas numéricas alineadas a la derecha

    def linea(celdas: list[str]) -> str:
        """Une las celdas de una fila del anexo con el ancho de cada columna."""
        return "  ".join(
            str(c).rjust(anchos[i]) if i in derecha else str(c).ljust(anchos[i])
            for i, c in enumerate(celdas)
        ).rstrip()

    return "\n".join(
        [
            f"ANEXO: guías de {datos.transportista} entregadas fuera de plazo",
            f"Archivo auditado: {datos.nombre_archivo}",
            "",
            linea(encabezados),
            linea(["-" * a for a in anchos]),
            *[linea(f) for f in filas],
            "",
            f"Total: {_cantidad_guias(datos.cantidad)}, {pesos(datos.monto_total)}",
        ]
    )


def componer_carta(datos: DatosCarta, cuerpo: str) -> str:
    """Encabezado, firma y anexo siempre los pone el sistema, no la IA."""
    firma = datos.empresa_nombre + (f"\nRUT {datos.empresa_rut}" if datos.empresa_rut else "")
    return (
        "\n\n".join(
            [
                fecha_larga(datos.fecha_emision),
                f"Señores\n{datos.transportista}\nPresente",
                (
                    f"Ref.: Reclamo por incumplimiento de SLA, {_cantidad_guias(datos.cantidad)}"
                    f" fuera de plazo por un total de {pesos(datos.monto_total)}"
                ),
                cuerpo.strip(),
                firma,
                "_" * 60,
                _anexo(datos),
            ]
        )
        + "\n"
    )


@dataclass(frozen=True)
class ResultadoCarta:
    """Carta generada y de dónde salió el texto (qué IA o la plantilla)."""

    texto: str
    origen: str  # ORIGEN_IA | ORIGEN_PLANTILLA
    proveedor: Optional[str]  # "Gemini" o "Claude" (solo si origen es IA)
    modelo: Optional[str]  # modelo usado (solo si origen es IA)
    motivo_plantilla: Optional[str]  # por qué se usó la plantilla (si aplica)
    aviso_respaldo: Optional[str] = None  # por qué no la redactó la IA principal


def generar_carta(
    datos: DatosCarta,
    usar_ia: bool = True,
    config: Optional[ConfiguracionIA] = None,
) -> ResultadoCarta:
    """Intenta con la IA principal y luego con la de respaldo; si no, usa la plantilla."""
    if not datos.guias:
        raise ValueError("No hay guías fuera de plazo: no hay nada que reclamar.")

    if not usar_ia:
        motivo = "Se pidió la carta con plantilla (sin IA)."
    else:
        redaccion = ia_proveedores.redactar(
            construir_prompt(datos),
            lambda texto: revisar_respuesta_ia(texto, datos),
            config,
        )
        if redaccion.texto is not None:
            return ResultadoCarta(
                texto=componer_carta(datos, redaccion.texto),
                origen=ORIGEN_IA,
                proveedor=redaccion.proveedor,
                modelo=redaccion.modelo,
                motivo_plantilla=None,
                aviso_respaldo=redaccion.motivo,
            )
        motivo = redaccion.motivo
        registrador.warning("Carta de reclamo generada con plantilla: %s", motivo)

    return ResultadoCarta(
        texto=componer_carta(datos, cuerpo_plantilla(datos)),
        origen=ORIGEN_PLANTILLA,
        proveedor=None,
        modelo=None,
        motivo_plantilla=motivo,
    )
