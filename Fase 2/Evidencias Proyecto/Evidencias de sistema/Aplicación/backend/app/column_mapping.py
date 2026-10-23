"""
Mapeo automático de columnas para archivos de envíos subidos por el usuario.

El objetivo Sprint 1 es: "Implementar la ingesta y el mapeo automático de
columnas para archivos CSV/Excel de envíos masivos". Las empresas no van a
subir archivos con nombres de columna estandarizados (una dice "N° Guía",
otra "numero_guia", otra "Tracking"), así que esta función intenta
reconocer las columnas requeridas por similitud de nombre.

Es una función pura (no toca la BD ni el archivo) para que sea fácil de
testear con muchos casos de headers reales sin necesitar pandas ni un
archivo físico.
"""
import re
from dataclasses import dataclass, field

# Campos que el modelo de datos necesita sí o sí para poder auditar el envío.
CAMPOS_OBLIGATORIOS = ["numero_guia", "nombre_transportista", "fecha_despacho"]

# Campos que enriquecen la auditoría pero no son obligatorios para ingestar.
CAMPOS_OPCIONALES = ["fecha_entrega", "destino", "valor_declarado"]

# Sinónimos conocidos por campo. Todo en minúsculas y sin acentos/espacios
# raros — la normalización pasa el header por _normalizar() antes de
# comparar. Los valores son texto tal como podría venir en un archivo real
# (mezcla de español/inglés porque así son los exports reales), así que
# estos strings NO se traducen: son datos, no identificadores del código.
SINONIMOS = {
    "numero_guia": [
        "guia", "nguia", "numeroguia", "nrodeguia", "tracking",
        "trackingnumber", "numeroenvio", "nenvio", "codigoenvio", "guide",
        "waybill", "ordennumero",
    ],
    "nombre_transportista": [
        "transportista", "carrier", "courier", "empresadetransporte",
        "operadorlogistico", "operador",
    ],
    "fecha_despacho": [
        "fechadespacho", "fechaenvio", "fechasalida", "dispatchdate",
        "shipdate", "fecharetiro",
    ],
    "fecha_entrega": [
        "fechaentrega", "deliverydate", "fecharecepcion", "fecharecibido",
        "fechacierre",
    ],
    "destino": [
        "destino", "destination", "ciudaddestino", "comunadestino",
        "direcciondestino",
    ],
    "valor_declarado": [
        "valordeclarado", "declaredvalue", "montoenvio", "valorenvio",
        "montodeclarado",
    ],
}

TODOS_LOS_CAMPOS = CAMPOS_OBLIGATORIOS + CAMPOS_OPCIONALES


_PALABRAS_VACIAS = {"de", "del", "la", "el", "los", "las", "n"}


def _normalizar(header: str) -> str:
    """
    'Numero de Guia' -> 'numeroguia'. Minúsculas, sin acentos, sin
    conectores ("de", "del"...) y sin caracteres no alfanuméricos, para
    que headers redactados de forma distinta pero equivalentes matcheen
    igual (ej. "N° de Guía" y "Numero Guia").
    """
    h = header.strip().lower()
    acentos = str.maketrans("áéíóúñ", "aeioun")
    h = h.translate(acentos)
    palabras = re.findall(r"[a-z0-9]+", h)
    palabras = [p for p in palabras if p not in _PALABRAS_VACIAS]
    return "".join(palabras)


@dataclass
class ResultadoMapeo:
    mapeo: dict = field(default_factory=dict)                # {campo_interno: header_original}
    obligatorios_sin_mapear: list = field(default_factory=list)  # campos obligatorios sin match
    ambiguos: dict = field(default_factory=dict)              # campo: [headers candidatos] si hubo >1 match

    @property
    def es_valido(self) -> bool:
        """True si se pudo mapear todo lo obligatorio para poder ingestar el archivo."""
        return len(self.obligatorios_sin_mapear) == 0


def mapear_columnas(headers: list[str]) -> ResultadoMapeo:
    """
    Dada la lista de headers tal como vienen en el archivo, devuelve el
    mapeo campo_interno -> header_original, más advertencias de lo que no
    se pudo mapear automáticamente.
    """
    resultado = ResultadoMapeo()
    headers_normalizados = {_normalizar(h): h for h in headers}

    for nombre_campo in TODOS_LOS_CAMPOS:
        # match directo por nombre de campo (ej. header ya viene como "numero_guia")
        if nombre_campo in headers_normalizados:
            candidatos = [headers_normalizados[nombre_campo]]
        else:
            candidatos = [
                headers_normalizados[norm]
                for sinonimo in SINONIMOS.get(nombre_campo, [])
                for norm in [_normalizar(sinonimo)]
                if norm in headers_normalizados
            ]
            # dedup preservando orden
            vistos = set()
            candidatos = [c for c in candidatos if not (c in vistos or vistos.add(c))]

        if len(candidatos) == 1:
            resultado.mapeo[nombre_campo] = candidatos[0]
        elif len(candidatos) > 1:
            resultado.ambiguos[nombre_campo] = candidatos
            # usamos el primero como mejor esfuerzo, pero queda registrado como ambiguo
            resultado.mapeo[nombre_campo] = candidatos[0]
        elif nombre_campo in CAMPOS_OBLIGATORIOS:
            resultado.obligatorios_sin_mapear.append(nombre_campo)

    return resultado
