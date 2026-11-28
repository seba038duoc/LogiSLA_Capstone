"""
Proveedores de IA generativa de LogiSLA: Google Gemini y Claude (Anthropic).

La carta de reclamo (app/ia_cartas.py) y el resumen ejecutivo
(app/ia_resumen.py) piden el texto a este módulo con redactar(). El orden,
por defecto, es:

  1. Google Gemini, la IA principal (nivel gratuito cuando Google lo ofrece a
     la cuenta). Si no hay clave, se agotó su cuota, no responde o su texto no pasa la revisión de
     cifras, se pasa a la siguiente.
  2. Claude (Anthropic), modelo claude-haiku-5-5, de respaldo. Solo se usa si
     tiene clave (requiere créditos prepagados). Mismas reglas.
  3. Si ninguna entrega un texto válido, quien llama usa su plantilla fija.

Con IA_PRINCIPAL=claude en backend/.env el orden se invierte (Claude primero
y Gemini de respaldo), por ejemplo si más adelante cargan créditos a Claude.

Cada proveedor que falla deja su motivo, y la respuesta final dice cuál
redactó el texto (o por qué se usó la plantilla).

Configuración (variables de entorno o archivo backend/.env, que está en
.gitignore y nunca se sube a GitHub):
  IA_PRINCIPAL       opcional; "gemini" (por defecto) o "claude"
  ANTHROPIC_API_KEY  clave de https://platform.claude.com (créditos prepagados)
  CLAUDE_MODEL       opcional; por defecto claude-haiku-5-5 (el más económico)
  CLAUDE_TIMEOUT_S   opcional; segundos de espera, por defecto 30
  GEMINI_API_KEY     clave de https://aistudio.google.com
  GEMINI_MODEL       opcional; por defecto gemini-3.5-flash-lite
  GEMINI_TIMEOUT_S   opcional; segundos de espera, por defecto 25

Las llamadas usan la biblioteca estándar de Python (urllib), sin
dependencias nuevas. La única función que sale a internet es _abrir_url(),
que las pruebas reemplazan por una simulación.
"""

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

registrador = logging.getLogger(__name__)

# backend/.env (este archivo está en backend/app/)
RUTA_ENV = Path(__file__).resolve().parent.parent / ".env"

CLAUDE = "Claude"
GEMINI = "Gemini"

CLAUDE_MODELO_POR_DEFECTO = "claude-haiku-5-5"
CLAUDE_URL_POR_DEFECTO = "https://api.anthropic.com/v1"
CLAUDE_TIEMPO_POR_DEFECTO_S = 30.0
# Versión de la API de Anthropic (header obligatorio). 2026-10-21 es la más
# reciente; la solicitud de LogiSLA no usa ningún parámetro que haya cambiado.
CLAUDE_VERSION_API = "2026-10-21"
# Tope de tokens de salida por llamada: una carta o un resumen usan bastante
# menos. Limita el gasto máximo de cada llamada.
CLAUDE_MAX_TOKENS = 2000

GEMINI_MODELO_POR_DEFECTO = "gemini-3.5-flash-lite"
GEMINI_URL_POR_DEFECTO = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_TIEMPO_POR_DEFECTO_S = 25.0


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfiguracionProveedor:
    """Configuración de un proveedor: nombre, clave, modelo, dirección de la API y espera."""

    nombre: str  # CLAUDE | GEMINI
    api_key: Optional[str]
    modelo: str
    url_api: str
    tiempo_espera_s: float

    @property
    def configurada(self) -> bool:
        """True si este proveedor tiene clave."""
        return bool(self.api_key)


@dataclass(frozen=True)
class ConfiguracionIA:
    """Los dos proveedores y cuál es el principal (por defecto, Gemini)."""

    claude: ConfiguracionProveedor
    gemini: ConfiguracionProveedor
    principal: str = GEMINI  # GEMINI | CLAUDE

    @property
    def en_orden(self) -> list[ConfiguracionProveedor]:
        """Proveedores en el orden en que se intentan: el principal primero."""
        if self.principal == CLAUDE:
            return [self.claude, self.gemini]
        return [self.gemini, self.claude]

    @property
    def configurada(self) -> bool:
        """True si al menos un proveedor tiene clave."""
        return any(p.configurada for p in self.en_orden)


def _leer_archivo_env(ruta: Optional[Path] = None) -> dict[str, str]:
    """
    Lee líneas CLAVE=valor de backend/.env. Ignora comentarios (#) y líneas
    vacías, quita comillas, y acepta el BOM que agrega el Bloc de notas.
    Si el archivo no existe, devuelve un diccionario vacío.
    """
    ruta = ruta or RUTA_ENV
    valores: dict[str, str] = {}
    try:
        texto = ruta.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return valores
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave = clave.strip()
        if clave.startswith("export "):
            clave = clave[len("export ") :].strip()
        valores[clave] = valor.strip().strip('"').strip("'").strip()
    return valores


def obtener_configuracion() -> ConfiguracionIA:
    """
    Lee la configuración en cada llamada, para que un cambio en backend/.env
    se note sin reiniciar el backend. Una variable de entorno tiene prioridad
    sobre el archivo .env.
    """
    archivo = _leer_archivo_env()

    def valor(clave: str, por_defecto: str = "") -> str:
        """Valor de una variable: primero el entorno, luego backend/.env, luego el defecto."""
        return (os.getenv(clave) or archivo.get(clave) or por_defecto).strip()

    def segundos(clave: str, por_defecto: float) -> float:
        """Tiempo de espera en segundos; si el valor no es un número positivo, el defecto."""
        try:
            numero = float(valor(clave, str(por_defecto)))
        except ValueError:
            return por_defecto
        return numero if numero > 0 else por_defecto

    # IA principal: "claude" o "gemini" (por defecto, y ante un valor desconocido).
    principal = CLAUDE if valor("IA_PRINCIPAL").lower() == "claude" else GEMINI

    return ConfiguracionIA(
        principal=principal,
        claude=ConfiguracionProveedor(
            nombre=CLAUDE,
            api_key=valor("ANTHROPIC_API_KEY") or None,
            modelo=valor("CLAUDE_MODEL", CLAUDE_MODELO_POR_DEFECTO),
            url_api=valor("CLAUDE_API_URL", CLAUDE_URL_POR_DEFECTO),
            tiempo_espera_s=segundos("CLAUDE_TIMEOUT_S", CLAUDE_TIEMPO_POR_DEFECTO_S),
        ),
        gemini=ConfiguracionProveedor(
            nombre=GEMINI,
            api_key=valor("GEMINI_API_KEY") or None,
            modelo=valor("GEMINI_MODEL", GEMINI_MODELO_POR_DEFECTO),
            url_api=valor("GEMINI_API_URL", GEMINI_URL_POR_DEFECTO),
            tiempo_espera_s=segundos("GEMINI_TIMEOUT_S", GEMINI_TIEMPO_POR_DEFECTO_S),
        ),
    )


# ---------------------------------------------------------------------------
# Llamadas HTTP
# ---------------------------------------------------------------------------


class ErrorIA(Exception):
    """Falla al usar un proveedor de IA. El mensaje se puede mostrar y nunca incluye la clave."""


def _abrir_url(solicitud: urllib.request.Request, tiempo_espera_s: float) -> bytes:
    """Única función que sale a internet (las pruebas la reemplazan por una simulación)."""
    with urllib.request.urlopen(solicitud, timeout=tiempo_espera_s) as respuesta:
        return respuesta.read()


def _mensaje_del_proveedor(exc: urllib.error.HTTPError) -> str:
    """Extrae el texto de error que manda el proveedor ({"error": {"message": ...}}), acortado."""
    try:
        cuerpo = json.loads(exc.read().decode("utf-8"))
        mensaje = str(cuerpo.get("error", {}).get("message", "")).strip()
    except Exception:
        return ""
    return mensaje[:200]


def _enviar(solicitud: urllib.request.Request, config: ConfiguracionProveedor, dominio: str):
    """
    Envía la solicitud y devuelve el JSON de la respuesta. Los errores de red
    se convierten en ErrorIA; los HTTPError se dejan pasar para que cada
    proveedor los explique a su manera.
    """
    nombre = config.nombre
    try:
        datos = _abrir_url(solicitud, config.tiempo_espera_s)
    except urllib.error.HTTPError:
        raise
    except TimeoutError:
        raise ErrorIA(f"{nombre} no respondió en {config.tiempo_espera_s:.0f} segundos.") from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise ErrorIA(
                f"{nombre} no respondió en {config.tiempo_espera_s:.0f} segundos."
            ) from None
        raise ErrorIA(
            f"No hay conexión con {nombre} (sin internet o la red bloquea {dominio})."
        ) from None
    except OSError as exc:
        raise ErrorIA(f"No hay conexión con {nombre} ({type(exc).__name__}).") from None

    try:
        respuesta = json.loads(datos.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ErrorIA(f"{nombre} devolvió una respuesta que no se pudo leer.") from None
    if not isinstance(respuesta, dict):
        raise ErrorIA(f"{nombre} devolvió una respuesta con un formato inesperado.")
    return respuesta


def llamar_claude(prompt: str, config: ConfiguracionProveedor) -> str:
    """
    Envía el prompt a Claude (POST .../messages, API de mensajes de Anthropic)
    y devuelve el texto generado. Cualquier problema se convierte en ErrorIA.
    """
    if not config.api_key:
        raise ErrorIA("No hay clave de Claude (falta ANTHROPIC_API_KEY en backend/.env).")

    solicitud_json = {
        "model": config.modelo,
        "max_tokens": CLAUDE_MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    if "haiku" in config.modelo:
        # Haiku 5.5 "piensa" antes de responder por defecto. Para redactar una
        # carta no hace falta, y apagarlo ahorra tokens (y créditos). Otros
        # modelos (Opus 5.5) no aceptan apagarlo, por eso solo se envía a Haiku.
        solicitud_json["thinking"] = {"type": "disabled"}
    cuerpo = json.dumps(solicitud_json).encode("utf-8")
    solicitud = urllib.request.Request(
        f"{config.url_api.rstrip('/')}/messages",
        data=cuerpo,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-api-key": config.api_key,
            "anthropic-version": CLAUDE_VERSION_API,
        },
    )

    try:
        respuesta = _enviar(solicitud, config, "api.anthropic.com")
    except urllib.error.HTTPError as exc:
        detalle = _mensaje_del_proveedor(exc)
        sufijo = f" Detalle de Anthropic: {detalle}" if detalle else ""
        # Sin saldo, Anthropic responde 400 con "credit balance is too low".
        if "credit balance" in detalle.lower() or exc.code == 402:
            raise ErrorIA(
                "Claude no tiene saldo (se acabaron los créditos prepagados)." + sufijo
            ) from None
        if exc.code in (401, 403):
            raise ErrorIA(
                f"Claude rechazó la clave (HTTP {exc.code}). Revisa que ANTHROPIC_API_KEY "
                "esté bien copiada en backend/.env." + sufijo
            ) from None
        if exc.code == 404:
            raise ErrorIA(
                f"El modelo '{config.modelo}' no existe o no está disponible. Revisa CLAUDE_MODEL."
                + sufijo
            ) from None
        if exc.code == 429:
            raise ErrorIA("Se alcanzó el límite de uso de Claude por minuto." + sufijo) from None
        if exc.code in (500, 529):
            raise ErrorIA(
                f"Claude está con problemas o sobrecargado (HTTP {exc.code})." + sufijo
            ) from None
        raise ErrorIA(f"Claude respondió con un error (HTTP {exc.code})." + sufijo) from None

    if respuesta.get("stop_reason") == "refusal":
        raise ErrorIA("Claude se negó a redactar el texto.")
    if respuesta.get("stop_reason") == "max_tokens":
        raise ErrorIA("La respuesta de Claude quedó cortada (superó el tope de tokens).")
    # La respuesta es una lista de bloques: se toman solo los de tipo "text".
    bloques = respuesta.get("content") or []
    texto = "".join(
        str(b.get("text", "")) for b in bloques if isinstance(b, dict) and b.get("type") == "text"
    ).strip()
    if not texto:
        raise ErrorIA("Claude devolvió una respuesta vacía.")
    return texto


def llamar_gemini(prompt: str, config: ConfiguracionProveedor) -> str:
    """
    Envía el prompt a Gemini (POST .../models/{modelo}:generateContent) y
    devuelve el texto generado. Cualquier problema se convierte en ErrorIA.
    """
    if not config.api_key:
        raise ErrorIA("No hay clave de Gemini (falta GEMINI_API_KEY en backend/.env).")

    modelo = urllib.parse.quote(config.modelo, safe="-._")
    cuerpo = json.dumps({"contents": [{"role": "user", "parts": [{"text": prompt}]}]}).encode(
        "utf-8"
    )
    solicitud = urllib.request.Request(
        f"{config.url_api.rstrip('/')}/models/{modelo}:generateContent",
        data=cuerpo,
        method="POST",
        # La clave va en un header y no en la URL, para que no quede en logs.
        headers={"Content-Type": "application/json", "x-goog-api-key": config.api_key},
    )

    try:
        respuesta = _enviar(solicitud, config, "generativelanguage.googleapis.com")
    except urllib.error.HTTPError as exc:
        detalle = _mensaje_del_proveedor(exc)
        sufijo = f" Detalle de Google: {detalle}" if detalle else ""
        if exc.code == 429:
            raise ErrorIA(
                "Se alcanzó el límite gratuito de Gemini (por minuto o por día). "
                "Espera un minuto y vuelve a intentarlo." + sufijo
            ) from None
        if exc.code in (400, 401, 403):
            raise ErrorIA(
                f"Gemini rechazó la solicitud (HTTP {exc.code}). Revisa que GEMINI_API_KEY "
                "esté bien copiada en backend/.env." + sufijo
            ) from None
        if exc.code == 404:
            raise ErrorIA(
                f"El modelo '{config.modelo}' no existe o no está disponible. Revisa GEMINI_MODEL."
                + sufijo
            ) from None
        raise ErrorIA(f"Gemini respondió con un error (HTTP {exc.code})." + sufijo) from None

    candidatos = respuesta.get("candidates") or []
    if not candidatos or not isinstance(candidatos[0], dict):
        bloqueo = (respuesta.get("promptFeedback") or {}).get("blockReason")
        raise ErrorIA("Gemini no generó texto" + (f" (bloqueado: {bloqueo})." if bloqueo else "."))

    partes = (candidatos[0].get("content") or {}).get("parts") or []
    texto = "".join(
        str(p.get("text", "")) for p in partes if isinstance(p, dict) and not p.get("thought")
    ).strip()
    if not texto:
        fin = candidatos[0].get("finishReason")
        raise ErrorIA("Gemini devolvió una respuesta vacía" + (f" ({fin})." if fin else "."))
    return texto


# Función que llama a cada proveedor según su nombre.
LLAMADAS: dict[str, Callable[[str, ConfiguracionProveedor], str]] = {
    CLAUDE: llamar_claude,
    GEMINI: llamar_gemini,
}


# ---------------------------------------------------------------------------
# Redacción con respaldo automático
# ---------------------------------------------------------------------------


def limpiar(texto: str) -> str:
    """Quita marcas de markdown que a veces agrega el modelo (negritas y títulos)."""
    texto = texto.replace("**", "").replace("__", "")
    lineas = [re.sub(r"^\s*#+\s*", "", linea).rstrip() for linea in texto.strip().splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()


@dataclass(frozen=True)
class Redaccion:
    """
    Resultado de redactar(). Si `texto` es None, ningún proveedor sirvió y
    `motivo` explica por qué (quien llama usa su plantilla). Si hay texto,
    `motivo` explica por qué no lo redactó la IA principal (o es None).
    """

    texto: Optional[str]
    proveedor: Optional[str]  # CLAUDE | GEMINI, o None
    modelo: Optional[str]
    motivo: Optional[str]


def redactar(
    prompt: str,
    revisar: Callable[[str], Optional[str]],
    config: Optional[ConfiguracionIA] = None,
) -> Redaccion:
    """
    Pide el texto a cada proveedor configurado, en orden (el principal
    primero). `revisar` recibe el texto ya limpio y devuelve None si sirve o
    el motivo por el que se descarta. Devuelve el primer texto válido.
    """
    config = config or obtener_configuracion()
    motivos: list[str] = []
    for proveedor in config.en_orden:
        if not proveedor.configurada:
            continue
        try:
            texto = limpiar(LLAMADAS[proveedor.nombre](prompt, proveedor))
            problema = revisar(texto)
        except ErrorIA as exc:
            problema = str(exc)
        except Exception:  # pragma: no cover - red de seguridad: se prueba el siguiente
            registrador.exception("Error inesperado al usar %s", proveedor.nombre)
            problema = f"Error inesperado al usar {proveedor.nombre}."
        if problema is None:
            return Redaccion(texto, proveedor.nombre, proveedor.modelo, " ".join(motivos) or None)
        registrador.warning("%s no sirvió: %s", proveedor.nombre, problema)
        # Los errores ya nombran al proveedor; los de la revisión de cifras no.
        if proveedor.nombre not in problema:
            problema = f"{proveedor.nombre}: {problema}"
        motivos.append(problema)

    if not motivos:
        motivos.append(
            "No hay claves de IA configuradas (faltan ANTHROPIC_API_KEY y GEMINI_API_KEY en "
            "backend/.env)."
        )
    return Redaccion(None, None, None, " ".join(motivos))
