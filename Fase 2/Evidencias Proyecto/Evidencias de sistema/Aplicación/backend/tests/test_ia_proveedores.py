"""
Pruebas del respaldo automático entre proveedores de IA (app/ia_proveedores.py).

Por defecto Gemini es la IA principal y Claude el respaldo. La mayoría de
las pruebas usan el orden inverso (IA_PRINCIPAL=claude), que es el que más
casos de error de Claude tiene que manejar; las pruebas del orden por
defecto están en su propia sección.

Las dos IA se SIMULAN: ninguna prueba sale a internet ni gasta créditos.
Se reemplaza ia_proveedores._abrir_url y la simulación responde según la
dirección de la solicitud (claude.invalid o gemini.invalid).
"""

import io
import json
import urllib.error
from datetime import date, datetime

import pytest

from app import ia_cartas, ia_proveedores
from app.models import ReglaSLA, Transportista

URL_CLAUDE = "https://claude.invalid/v1"
URL_GEMINI = "https://gemini.invalid/v1beta"

CLAUDE = ia_proveedores.ConfiguracionProveedor(
    ia_proveedores.CLAUDE, "clave-claude", "claude-de-prueba", URL_CLAUDE, 5
)
GEMINI = ia_proveedores.ConfiguracionProveedor(
    ia_proveedores.GEMINI, "clave-gemini", "gemini-de-prueba", URL_GEMINI, 5
)
# Claude primero (IA_PRINCIPAL=claude) y Gemini de respaldo.
AMBAS = ia_proveedores.ConfiguracionIA(claude=CLAUDE, gemini=GEMINI, principal="Claude")
# Orden por defecto: Gemini primero y Claude de respaldo.
POR_DEFECTO = ia_proveedores.ConfiguracionIA(claude=CLAUDE, gemini=GEMINI)

# La función real, guardada antes de que la fixture la reemplace por la simulada.
_OBTENER_REAL = ia_proveedores.obtener_configuracion

CUERPO_VALIDO = (
    "De nuestra consideración:\n\n"
    "Por medio de la presente, les informamos que la auditoría de nuestros despachos detectó "
    "2 guías entregadas fuera del plazo acordado de 24 horas hábiles.\n\n"
    "Conforme a la multa pactada de $15.000 por guía, el monto total a reclamar es de $30.000. "
    "El detalle de cada guía se encuentra en el anexo de esta carta.\n\n"
    "Solicitamos descontar este monto de la próxima factura o emitir una nota de crédito, "
    "y responder dentro de 10 días hábiles.\n\n"
    "Saludos cordiales."
)


def _respuesta_claude(texto: str, stop_reason: str = "end_turn") -> bytes:
    """Respuesta de la API de mensajes de Anthropic con un bloque de texto."""
    return json.dumps(
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": texto}],
            "stop_reason": stop_reason,
        }
    ).encode("utf-8")


def _respuesta_gemini(texto: str) -> bytes:
    """Respuesta de Gemini con un candidato de texto."""
    return json.dumps({"candidates": [{"content": {"parts": [{"text": texto}]}}]}).encode()


def _error_http(url: str, codigo: int, mensaje: str = "") -> urllib.error.HTTPError:
    """Error HTTP con el cuerpo JSON {"error": {"message": ...}} que mandan ambos proveedores."""
    cuerpo = json.dumps({"type": "error", "error": {"message": mensaje}}).encode("utf-8")
    return urllib.error.HTTPError(url, codigo, "error", {}, io.BytesIO(cuerpo))


def _simular(monkeypatch, claude=None, gemini=None):
    """
    Define qué responde cada proveedor: bytes (respuesta) o una excepción.
    Devuelve la lista de solicitudes recibidas, en orden.
    """
    solicitudes = []

    def falso(solicitud, tiempo_espera_s):
        solicitudes.append(solicitud)
        respuesta = claude if solicitud.full_url.startswith(URL_CLAUDE) else gemini
        if respuesta is None:
            raise AssertionError(f"No se esperaba una llamada a {solicitud.full_url}")
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    monkeypatch.setattr(ia_proveedores, "_abrir_url", falso)
    return solicitudes


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    """Por defecto ambas IA tienen clave y cualquier salida a internet hace fallar la prueba."""
    monkeypatch.setattr(ia_proveedores, "obtener_configuracion", lambda: AMBAS)
    _simular(monkeypatch)


def _datos() -> ia_cartas.DatosCarta:
    """Dos guías de Chilexpress fuera de plazo, $15.000 cada una."""
    guias = [
        ia_cartas.GuiaIncumplida(
            numero_guia=f"G-{i:03d}",
            destino="Temuco",
            fecha_despacho=datetime(2026, 10, 5 + i, 9, 0),
            fecha_entrega=datetime(2026, 10, 8 + i, 18, 0),
            horas_atraso=10.5,
            monto_multa=15000.0,
        )
        for i in (1, 2)
    ]
    return ia_cartas.DatosCarta(
        empresa_nombre="Retail Demo SpA",
        empresa_rut="76.123.456-7",
        transportista="Chilexpress",
        nombre_archivo="envios.csv",
        horas_habiles_maximas=24,
        multa_por_incumplimiento=15000.0,
        guias_auditadas=8,
        guias=guias,
        fecha_emision=date(2026, 11, 17),
    )


# ------------------- Orden por defecto: Gemini y luego Claude -------------------


def test_por_defecto_gemini_es_la_principal(monkeypatch):
    solicitudes = _simular(monkeypatch, gemini=_respuesta_gemini(CUERPO_VALIDO))

    resultado = ia_cartas.generar_carta(_datos(), config=POR_DEFECTO)

    assert resultado.proveedor == "Gemini"
    assert resultado.aviso_respaldo is None
    assert len(solicitudes) == 1  # Claude no se llamó: no se gastan créditos


def test_si_gemini_agota_su_cuota_redacta_claude(monkeypatch):
    _simular(
        monkeypatch,
        gemini=_error_http(URL_GEMINI, 429, "Quota exceeded"),
        claude=_respuesta_claude(CUERPO_VALIDO),
    )

    resultado = ia_cartas.generar_carta(_datos(), config=POR_DEFECTO)

    assert resultado.proveedor == "Claude"
    assert "límite gratuito de Gemini" in resultado.aviso_respaldo


def test_por_defecto_sin_clave_de_claude_y_gemini_caido_usa_plantilla(monkeypatch):
    sin_claude = ia_proveedores.ConfiguracionIA(
        claude=ia_proveedores.ConfiguracionProveedor(
            ia_proveedores.CLAUDE, None, "claude-de-prueba", URL_CLAUDE, 5
        ),
        gemini=GEMINI,
    )
    _simular(monkeypatch, gemini=TimeoutError("timed out"))

    resultado = ia_cartas.generar_carta(_datos(), config=sin_claude)

    assert resultado.origen == ia_cartas.ORIGEN_PLANTILLA
    assert resultado.motivo_plantilla == "Gemini no respondió en 5 segundos."


@pytest.mark.parametrize(
    "valor, principal",
    [(None, "Gemini"), ("gemini", "Gemini"), ("Claude", "Claude"), ("otra", "Gemini")],
)
def test_ia_principal_se_elige_en_el_archivo_env(monkeypatch, tmp_path, valor, principal):
    archivo = tmp_path / ".env"
    archivo.write_text(f"IA_PRINCIPAL={valor}\n" if valor else "", encoding="utf-8")
    monkeypatch.setattr(ia_proveedores, "RUTA_ENV", archivo)
    monkeypatch.delenv("IA_PRINCIPAL", raising=False)

    config = _configuracion_real(monkeypatch)

    assert config.principal == principal
    assert config.en_orden[0].nombre == principal


# --------------------- Con IA_PRINCIPAL=claude: Claude primero ---------------------


def test_claude_redacta_y_gemini_no_se_usa(monkeypatch):
    solicitudes = _simular(monkeypatch, claude=_respuesta_claude(CUERPO_VALIDO))

    resultado = ia_cartas.generar_carta(_datos())

    assert resultado.origen == ia_cartas.ORIGEN_IA
    assert resultado.proveedor == "Claude"
    assert resultado.modelo == "claude-de-prueba"
    assert resultado.aviso_respaldo is None
    assert "Total: 2 guías, $30.000" in resultado.texto
    assert len(solicitudes) == 1  # Gemini no se llamó

    # Solicitud a la API de mensajes de Anthropic
    solicitud = solicitudes[0]
    assert solicitud.full_url == f"{URL_CLAUDE}/messages"
    assert solicitud.get_header("X-api-key") == "clave-claude"
    assert solicitud.get_header("Anthropic-version") == ia_proveedores.CLAUDE_VERSION_API
    cuerpo = json.loads(solicitud.data)
    assert cuerpo["model"] == "claude-de-prueba"
    assert cuerpo["max_tokens"] == ia_proveedores.CLAUDE_MAX_TOKENS
    assert cuerpo["messages"][0]["role"] == "user"
    assert "temperature" not in cuerpo  # los modelos 5.5 no aceptan cambiarla
    assert "thinking" not in cuerpo  # "claude-de-prueba" no es Haiku

    # A la IA solo va el resumen agregado: ningún número de guía ni destino
    prompt = cuerpo["messages"][0]["content"]
    assert "$30.000" in prompt and "Chilexpress" in prompt
    assert "G-001" not in prompt and "Temuco" not in prompt


def test_con_haiku_se_apaga_el_pensamiento_para_ahorrar(monkeypatch):
    haiku = ia_proveedores.ConfiguracionProveedor(
        ia_proveedores.CLAUDE, "clave-claude", "claude-haiku-5-5", URL_CLAUDE, 5
    )
    config = ia_proveedores.ConfiguracionIA(claude=haiku, gemini=GEMINI, principal="Claude")
    solicitudes = _simular(monkeypatch, claude=_respuesta_claude(CUERPO_VALIDO))

    resultado = ia_cartas.generar_carta(_datos(), config=config)

    assert resultado.modelo == "claude-haiku-5-5"
    assert json.loads(solicitudes[0].data)["thinking"] == {"type": "disabled"}


def test_solo_se_leen_los_bloques_de_texto_de_claude(monkeypatch):
    respuesta = json.dumps(
        {
            "content": [
                {"type": "thinking", "thinking": "Voy a redactar la carta..."},
                {"type": "text", "text": CUERPO_VALIDO},
            ],
            "stop_reason": "end_turn",
        }
    ).encode()
    _simular(monkeypatch, claude=respuesta)

    resultado = ia_cartas.generar_carta(_datos())

    assert resultado.proveedor == "Claude"
    assert "Voy a redactar" not in resultado.texto


# ------------------------- Respaldo: Claude -> Gemini -------------------------


def test_sin_saldo_en_claude_redacta_gemini(monkeypatch):
    sin_saldo = _error_http(
        URL_CLAUDE, 400, "Your credit balance is too low to access the Anthropic API."
    )
    solicitudes = _simular(monkeypatch, claude=sin_saldo, gemini=_respuesta_gemini(CUERPO_VALIDO))

    resultado = ia_cartas.generar_carta(_datos())

    assert resultado.origen == ia_cartas.ORIGEN_IA
    assert resultado.proveedor == "Gemini"
    assert resultado.modelo == "gemini-de-prueba"
    assert "Claude no tiene saldo" in resultado.aviso_respaldo
    assert [s.full_url.split("/")[2] for s in solicitudes] == ["claude.invalid", "gemini.invalid"]


@pytest.mark.parametrize(
    "error, fragmento",
    [
        (_error_http(URL_CLAUDE, 401, "invalid x-api-key"), "ANTHROPIC_API_KEY"),
        (_error_http(URL_CLAUDE, 402, "billing"), "no tiene saldo"),
        (_error_http(URL_CLAUDE, 404, "model not found"), "CLAUDE_MODEL"),
        (_error_http(URL_CLAUDE, 429, "rate limit"), "límite de uso"),
        (_error_http(URL_CLAUDE, 529, "Overloaded"), "sobrecargado"),
        (_error_http(URL_CLAUDE, 400, "messages: invalid"), "HTTP 400"),
        (TimeoutError("timed out"), "no respondió"),
        (urllib.error.URLError(OSError("Name or service not known")), "No hay conexión"),
    ],
)
def test_cualquier_falla_de_claude_pasa_a_gemini(monkeypatch, error, fragmento):
    _simular(monkeypatch, claude=error, gemini=_respuesta_gemini(CUERPO_VALIDO))

    resultado = ia_cartas.generar_carta(_datos())

    assert resultado.proveedor == "Gemini"
    assert fragmento in resultado.aviso_respaldo
    assert "clave-claude" not in resultado.aviso_respaldo


@pytest.mark.parametrize(
    "respuesta, fragmento",
    [
        (_respuesta_claude(CUERPO_VALIDO.replace("$30.000", "$45.000")), "monto total"),
        (_respuesta_claude(CUERPO_VALIDO, stop_reason="refusal"), "se negó"),
        (_respuesta_claude(CUERPO_VALIDO, stop_reason="max_tokens"), "cortada"),
        (_respuesta_claude(""), "vacía"),
        (b"no es json", "no se pudo leer"),
    ],
)
def test_respuesta_de_claude_descartada_pasa_a_gemini(monkeypatch, respuesta, fragmento):
    _simular(monkeypatch, claude=respuesta, gemini=_respuesta_gemini(CUERPO_VALIDO))

    resultado = ia_cartas.generar_carta(_datos())

    assert resultado.proveedor == "Gemini"
    assert fragmento in resultado.aviso_respaldo
    assert "Claude" in resultado.aviso_respaldo  # el aviso siempre dice qué IA falló


def test_si_fallan_las_dos_ia_se_usa_la_plantilla(monkeypatch):
    _simular(
        monkeypatch,
        claude=_error_http(URL_CLAUDE, 400, "Your credit balance is too low"),
        gemini=_error_http(URL_GEMINI, 429, "Quota exceeded"),
    )

    resultado = ia_cartas.generar_carta(_datos())

    assert resultado.origen == ia_cartas.ORIGEN_PLANTILLA
    assert resultado.proveedor is None
    assert resultado.motivo_plantilla.startswith("Claude no tiene saldo")
    assert "Se alcanzó el límite gratuito de Gemini" in resultado.motivo_plantilla
    assert "Total: 2 guías, $30.000" in resultado.texto


def test_sin_clave_de_claude_se_va_directo_a_gemini(monkeypatch):
    solo_gemini = ia_proveedores.ConfiguracionIA(
        principal="Claude",
        claude=ia_proveedores.ConfiguracionProveedor(
            ia_proveedores.CLAUDE, None, "claude-de-prueba", URL_CLAUDE, 5
        ),
        gemini=GEMINI,
    )
    solicitudes = _simular(monkeypatch, gemini=_respuesta_gemini(CUERPO_VALIDO))

    resultado = ia_cartas.generar_carta(_datos(), config=solo_gemini)

    assert resultado.proveedor == "Gemini"
    assert resultado.aviso_respaldo is None  # Claude no se intentó: no hay nada que avisar
    assert len(solicitudes) == 1


def test_solo_claude_configurado_y_falla_usa_la_plantilla(monkeypatch):
    solo_claude = ia_proveedores.ConfiguracionIA(
        principal="Claude",
        claude=CLAUDE,
        gemini=ia_proveedores.ConfiguracionProveedor(
            ia_proveedores.GEMINI, None, "gemini-de-prueba", URL_GEMINI, 5
        ),
    )
    _simular(monkeypatch, claude=TimeoutError("timed out"))

    resultado = ia_cartas.generar_carta(_datos(), config=solo_claude)

    assert resultado.origen == ia_cartas.ORIGEN_PLANTILLA
    assert resultado.motivo_plantilla.startswith("Claude no respondió")


def test_configuracion_de_claude_desde_archivo_env(monkeypatch, tmp_path):
    archivo = tmp_path / ".env"
    archivo.write_text(
        "ANTHROPIC_API_KEY=clave-del-archivo\nCLAUDE_TIMEOUT_S=-3\n", encoding="utf-8"
    )
    monkeypatch.setattr(ia_proveedores, "RUTA_ENV", archivo)
    for variable in ("ANTHROPIC_API_KEY", "CLAUDE_MODEL", "CLAUDE_TIMEOUT_S", "CLAUDE_API_URL"):
        monkeypatch.delenv(variable, raising=False)

    real = _configuracion_real(monkeypatch)
    assert real.claude.api_key == "clave-del-archivo"
    assert real.claude.modelo == ia_proveedores.CLAUDE_MODELO_POR_DEFECTO
    assert real.claude.tiempo_espera_s == ia_proveedores.CLAUDE_TIEMPO_POR_DEFECTO_S
    assert real.claude.url_api == ia_proveedores.CLAUDE_URL_POR_DEFECTO


def _configuracion_real(monkeypatch) -> ia_proveedores.ConfiguracionIA:
    """Lee la configuración real (la fixture reemplazó obtener_configuracion por la simulada)."""
    monkeypatch.setattr(ia_proveedores, "obtener_configuracion", _OBTENER_REAL)
    return ia_proveedores.obtener_configuracion()


# --------------------------------- Endpoints ---------------------------------


def test_endpoint_estado_muestra_principal_y_respaldo(cliente):
    estado = cliente.get("/api/v1/ia/estado").json()

    assert estado["configurada"] is True
    assert estado["proveedor"] == "Claude"
    assert [(p["nombre"], p["papel"], p["configurado"]) for p in estado["proveedores"]] == [
        ("Claude", "principal", True),
        ("Gemini", "respaldo", True),
    ]
    assert "clave-claude" not in str(estado) and "clave-gemini" not in str(estado)


def test_endpoint_carta_informa_que_redacto_gemini_por_falta_de_saldo(
    cliente, sesion_bd, empresa_ejemplo, monkeypatch
):
    transportista = Transportista(nombre="Chilexpress")
    sesion_bd.add(transportista)
    sesion_bd.flush()
    sesion_bd.add(
        ReglaSLA(
            transportista_id=transportista.id,
            horas_habiles_maximas=24,
            multa_por_incumplimiento=15000,
            activa=True,
        )
    )
    sesion_bd.commit()
    csv = (
        "N° Guía,Transportista,Fecha Despacho,Fecha Entrega,Destino\n"
        "G-001,Chilexpress,2025-11-10 09:00,2025-11-10 14:00,Maipú\n"
        "G-002,Chilexpress,2025-11-10 09:00,2025-11-12 18:00,Temuco\n"
    ).encode("utf-8")
    carga = cliente.post(
        f"/api/v1/lotes-auditoria/cargar?empresa_id={empresa_ejemplo.id}",
        files={"file": ("envios.csv", csv, "text/csv")},
    )
    lote_id = carga.json()["lote_id"]
    assert cliente.post(f"/api/v1/lotes-auditoria/{lote_id}/auditar").status_code == 200

    cuerpo_una_guia = CUERPO_VALIDO.replace("2 guías", "1 guía").replace("$30.000", "$15.000")
    _simular(
        monkeypatch,
        claude=_error_http(URL_CLAUDE, 400, "Your credit balance is too low"),
        gemini=_respuesta_gemini(cuerpo_una_guia),
    )

    carta = cliente.post(
        f"/api/v1/lotes-auditoria/{lote_id}/carta?transportista=Chilexpress"
    ).json()

    assert carta["origen"] == "IA"
    assert carta["proveedor"] == "Gemini"
    assert carta["modelo"] == "gemini-de-prueba"
    assert "no tiene saldo" in carta["aviso_respaldo"]
    assert carta["motivo_plantilla"] is None
