"""
Pruebas de la IA generativa (carta de reclamo, app/ia_cartas.py) y de su
endpoint POST /api/v1/lotes-auditoria/{lote_id}/carta.

La IA se SIMULA en todas las pruebas: ninguna sale a internet ni gasta
cuota, aunque el equipo tenga claves reales en backend/.env. Se reemplaza
ia_proveedores._abrir_url (la única función que hace la llamada HTTP), así que
se prueba todo el resto: armado de la solicitud, lectura de la respuesta,
manejo de errores (429, timeout, sin red), revisión de montos y plantilla.

En este archivo solo Gemini tiene clave (Claude queda sin configurar), así
que se prueba el camino de Gemini, la IA principal por defecto. El respaldo
entre Gemini y Claude se prueba en test_ia_proveedores.py.
"""

import io
import json
import urllib.error
from datetime import date, datetime

import pandas as pd
import pytest

from app import ia_cartas, ia_proveedores
from app.models import ReglaSLA, Transportista

_obtener_configuracion_real = ia_proveedores.obtener_configuracion

SIN_CLAUDE = ia_proveedores.ConfiguracionProveedor(
    ia_proveedores.CLAUDE, None, "claude-de-prueba", "https://claude.invalid/v1", 5
)
CONFIG_PRUEBA = ia_proveedores.ConfiguracionIA(
    claude=SIN_CLAUDE,
    gemini=ia_proveedores.ConfiguracionProveedor(
        nombre=ia_proveedores.GEMINI,
        api_key="clave-de-prueba",
        modelo="modelo-de-prueba",
        url_api="https://gemini.invalid/v1beta",
        tiempo_espera_s=5,
    ),
)

CUERPO_IA_VALIDO = (
    "De nuestra consideración:\n\n"
    "Por medio de la presente, les informamos que la auditoría de nuestros despachos detectó "
    "2 guías entregadas fuera del plazo acordado de 24 horas hábiles.\n\n"
    "Conforme a la multa pactada de $15.000 por guía, el monto total a reclamar es de $30.000. "
    "El detalle de cada guía se encuentra en el anexo de esta carta.\n\n"
    "Solicitamos descontar este monto de la próxima factura o emitir una nota de crédito, "
    "y responder dentro de 10 días hábiles.\n\n"
    "Saludos cordiales."
)


def _respuesta_gemini(texto: str) -> bytes:
    return json.dumps(
        {
            "candidates": [
                {"content": {"role": "model", "parts": [{"text": texto}]}, "finishReason": "STOP"}
            ]
        }
    ).encode("utf-8")


def _error_http(codigo: int, mensaje: str = "") -> urllib.error.HTTPError:
    cuerpo = json.dumps({"error": {"code": codigo, "message": mensaje}}).encode("utf-8")
    return urllib.error.HTTPError("https://gemini.invalid", codigo, "error", {}, io.BytesIO(cuerpo))


@pytest.fixture(autouse=True)
def gemini_simulado(monkeypatch):
    """
    Por defecto: hay clave de prueba, y cualquier intento de salir a internet
    hace fallar la prueba. Cada prueba define qué "responde Gemini".
    """
    monkeypatch.setattr(ia_proveedores, "obtener_configuracion", lambda: CONFIG_PRUEBA)

    def sin_red(solicitud, tiempo_espera_s):
        raise AssertionError("Las pruebas no deben llamar a Gemini de verdad")

    monkeypatch.setattr(ia_proveedores, "_abrir_url", sin_red)


def _simular(monkeypatch, respuesta=None, error=None):
    """
    Hace que Gemini responda `respuesta` (bytes) o lance `error`.
    Devuelve la lista de solicitudes que recibió.
    """
    solicitudes = []

    def falso(solicitud, tiempo_espera_s):
        solicitudes.append(solicitud)
        if error is not None:
            raise error
        return respuesta

    monkeypatch.setattr(ia_proveedores, "_abrir_url", falso)
    return solicitudes


def _datos(cantidad: int = 2) -> ia_cartas.DatosCarta:
    guias = [
        ia_cartas.GuiaIncumplida(
            numero_guia=f"G-{i:03d}",
            destino="Temuco",
            fecha_despacho=datetime(2026, 10, 5 + i, 9, 0),
            fecha_entrega=datetime(2026, 10, 8 + i, 18, 0),
            horas_atraso=10.5 + i,
            monto_multa=15000.0,
        )
        for i in range(1, cantidad + 1)
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


# ------------------------------ Módulo de IA ------------------------------


def test_carta_redactada_por_ia_lleva_cifras_y_anexo_del_sistema(monkeypatch):
    solicitudes = _simular(monkeypatch, respuesta=_respuesta_gemini(CUERPO_IA_VALIDO))

    resultado = ia_cartas.generar_carta(_datos())

    assert resultado.origen == ia_cartas.ORIGEN_IA
    assert resultado.modelo == "modelo-de-prueba"
    assert resultado.motivo_plantilla is None
    assert "Por medio de la presente" in resultado.texto  # texto de la IA
    assert "17 de noviembre de 2026" in resultado.texto  # encabezado del sistema
    assert "RUT 76.123.456-7" in resultado.texto  # firma del sistema
    assert "G-001" in resultado.texto and "G-002" in resultado.texto  # anexo del sistema
    assert "Total: 2 guías, $30.000" in resultado.texto

    # La solicitud a Gemini: modelo en la URL, clave en un header (no en la URL)
    assert len(solicitudes) == 1
    solicitud = solicitudes[0]
    assert (
        solicitud.full_url
        == "https://gemini.invalid/v1beta/models/modelo-de-prueba:generateContent"
    )
    assert solicitud.get_method() == "POST"
    assert solicitud.get_header("X-goog-api-key") == "clave-de-prueba"
    assert "clave-de-prueba" not in solicitud.full_url

    # A la IA solo va el resumen agregado: ningún número de guía ni destino
    prompt = json.loads(solicitud.data)["contents"][0]["parts"][0]["text"]
    assert "$30.000" in prompt and "Chilexpress" in prompt
    assert "G-001" not in prompt and "Temuco" not in prompt


def test_sin_clave_usa_plantilla_sin_llamar_a_gemini(monkeypatch):
    sin_gemini = ia_proveedores.ConfiguracionProveedor(
        ia_proveedores.GEMINI, None, "modelo-de-prueba", "https://gemini.invalid", 5
    )
    sin_clave = ia_proveedores.ConfiguracionIA(claude=SIN_CLAUDE, gemini=sin_gemini)

    resultado = ia_cartas.generar_carta(_datos(), config=sin_clave)

    assert resultado.origen == ia_cartas.ORIGEN_PLANTILLA
    assert "ANTHROPIC_API_KEY" in resultado.motivo_plantilla
    assert "GEMINI_API_KEY" in resultado.motivo_plantilla
    assert "De nuestra consideración:" in resultado.texto
    assert (
        "2 guías entregadas por Chilexpress superaron el plazo acordado de 24 horas hábiles"
        in resultado.texto
    )
    assert "$30.000" in resultado.texto


@pytest.mark.parametrize(
    "error, fragmento_motivo",
    [
        (_error_http(429, "Quota exceeded"), "límite gratuito"),
        (_error_http(400, "API key not valid"), "GEMINI_API_KEY"),
        (_error_http(404, "model not found"), "GEMINI_MODEL"),
        (_error_http(503, "overloaded"), "HTTP 503"),
        (TimeoutError("timed out"), "no respondió"),
        (urllib.error.URLError(TimeoutError("timed out")), "no respondió"),
        (urllib.error.URLError(OSError("Name or service not known")), "No hay conexión"),
    ],
)
def test_si_gemini_falla_la_carta_sale_igual_con_plantilla(monkeypatch, error, fragmento_motivo):
    _simular(monkeypatch, error=error)

    resultado = ia_cartas.generar_carta(_datos())

    assert resultado.origen == ia_cartas.ORIGEN_PLANTILLA
    assert fragmento_motivo in resultado.motivo_plantilla
    assert "clave-de-prueba" not in resultado.motivo_plantilla
    assert "Total: 2 guías, $30.000" in resultado.texto


@pytest.mark.parametrize(
    "respuesta, fragmento_motivo",
    [
        (b"esto no es json", "no se pudo leer"),
        (json.dumps({"promptFeedback": {"blockReason": "SAFETY"}}).encode(), "SAFETY"),
        (_respuesta_gemini(""), "vacía"),
        (_respuesta_gemini("Muy corta."), "demasiado corta"),
        (_respuesta_gemini(CUERPO_IA_VALIDO.replace("$30.000", "$45.000")), "monto total"),
        (_respuesta_gemini(CUERPO_IA_VALIDO + " Además cobraremos $99.000 de recargo."), "$99.000"),
        (_respuesta_gemini(CUERPO_IA_VALIDO.replace("2 guías", "varias guías")), "cantidad exacta"),
    ],
)
def test_respuesta_invalida_de_la_ia_se_descarta(monkeypatch, respuesta, fragmento_motivo):
    _simular(monkeypatch, respuesta=respuesta)

    resultado = ia_cartas.generar_carta(_datos())

    assert resultado.origen == ia_cartas.ORIGEN_PLANTILLA
    assert fragmento_motivo in resultado.motivo_plantilla


def test_quita_markdown_de_la_respuesta(monkeypatch):
    _simular(monkeypatch, respuesta=_respuesta_gemini("## Carta\n**" + CUERPO_IA_VALIDO + "**"))

    resultado = ia_cartas.generar_carta(_datos())

    assert resultado.origen == ia_cartas.ORIGEN_IA
    assert "**" not in resultado.texto and "##" not in resultado.texto


def test_usar_ia_false_no_llama_a_gemini():
    resultado = ia_cartas.generar_carta(_datos(cantidad=1), usar_ia=False)

    assert resultado.origen == ia_cartas.ORIGEN_PLANTILLA
    assert "1 guía entregada por Chilexpress superó" in resultado.texto


VARIABLES_IA = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_MODEL",
    "CLAUDE_TIMEOUT_S",
    "CLAUDE_API_URL",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GEMINI_TIMEOUT_S",
    "GEMINI_API_URL",
)


def test_configuracion_desde_archivo_env(monkeypatch, tmp_path):
    archivo = tmp_path / ".env"
    archivo.write_text(
        "\ufeff# comentario\nGEMINI_API_KEY ="
        ' "clave-del-archivo"\nGEMINI_MODEL=modelo-x\nGEMINI_TIMEOUT_S=abc\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(ia_proveedores, "RUTA_ENV", archivo)
    for variable in VARIABLES_IA:
        monkeypatch.delenv(variable, raising=False)

    config = _obtener_configuracion_real().gemini
    assert config.api_key == "clave-del-archivo"
    assert config.modelo == "modelo-x"
    assert config.tiempo_espera_s == ia_proveedores.GEMINI_TIEMPO_POR_DEFECTO_S
    assert config.url_api == ia_proveedores.GEMINI_URL_POR_DEFECTO

    # una variable de entorno tiene prioridad sobre el archivo
    monkeypatch.setenv("GEMINI_API_KEY", "clave-del-entorno")
    assert _obtener_configuracion_real().gemini.api_key == "clave-del-entorno"


def test_sin_archivo_env_queda_sin_clave_y_con_modelo_por_defecto(monkeypatch, tmp_path):
    monkeypatch.setattr(ia_proveedores, "RUTA_ENV", tmp_path / "no-existe.env")
    for variable in VARIABLES_IA:
        monkeypatch.delenv(variable, raising=False)

    config = _obtener_configuracion_real()
    assert config.configurada is False
    assert config.gemini.modelo == ia_proveedores.GEMINI_MODELO_POR_DEFECTO
    assert config.claude.modelo == ia_proveedores.CLAUDE_MODELO_POR_DEFECTO


# -------------------------------- Endpoint --------------------------------


def _bytes_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _cargar_lote(cliente, sesion_bd, empresa_id, auditar=True) -> str:
    """Chilexpress: G-001 en plazo y G-002 fuera de plazo; Fletes Don Tito sin regla SLA."""
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

    df = pd.DataFrame(
        {
            "N° Guía": ["G-001", "G-002", "G-004"],
            "Transportista": ["Chilexpress", "chilexpress", "Fletes Don Tito"],
            "Fecha Despacho": ["2025-11-10 09:00"] * 3,
            "Fecha Entrega": ["2025-11-10 14:00", "2025-11-12 18:00", "2025-11-11 10:00"],
            "Destino": ["Maipú", "Temuco", "Rancagua"],
        }
    )
    carga = cliente.post(
        f"/api/v1/lotes-auditoria/cargar?empresa_id={empresa_id}",
        files={"file": ("envios.csv", _bytes_csv(df), "text/csv")},
    )
    assert carga.status_code == 200
    lote_id = carga.json()["lote_id"]
    if auditar:
        assert cliente.post(f"/api/v1/lotes-auditoria/{lote_id}/auditar").status_code == 200
    return lote_id


CUERPO_IA_UNA_GUIA = (
    "De nuestra consideración:\n\n"
    "Les informamos que en la auditoría de nuestros despachos se detectó 1 guía entregada "
    "fuera del plazo acordado de 24 horas hábiles.\n\n"
    "Según la multa pactada, el monto total a reclamar es de $15.000, cuyo detalle se encuentra "
    "en el anexo de esta carta. Solicitamos descontarlo de la próxima factura o emitir una nota "
    "de crédito, y responder dentro de 10 días hábiles.\n\n"
    "Saludos cordiales."
)


def test_endpoint_carta_con_ia(cliente, sesion_bd, empresa_ejemplo, monkeypatch):
    lote_id = _cargar_lote(cliente, sesion_bd, empresa_ejemplo.id)
    _simular(monkeypatch, respuesta=_respuesta_gemini(CUERPO_IA_UNA_GUIA))

    response = cliente.post(f"/api/v1/lotes-auditoria/{lote_id}/carta?transportista=CHILEXPRESS")

    assert response.status_code == 200
    carta = response.json()
    assert carta["origen"] == "IA"
    assert carta["proveedor"] == "Gemini"
    assert carta["modelo"] == "modelo-de-prueba"
    assert carta["transportista"] == "Chilexpress"
    assert carta["guias_incumplidas"] == 1
    assert carta["monto_total"] == 15000
    assert "Señores\nChilexpress" in carta["texto"]
    assert "G-002" in carta["texto"]  # la guía fuera de plazo va en el anexo
    assert "G-001" not in carta["texto"]  # la que llegó en plazo no
    assert "Retail Demo SpA\nRUT 76.123.456-7" in carta["texto"]


def test_endpoint_carta_usa_plantilla_si_gemini_no_responde(
    cliente, sesion_bd, empresa_ejemplo, monkeypatch
):
    lote_id = _cargar_lote(cliente, sesion_bd, empresa_ejemplo.id)
    _simular(monkeypatch, error=_error_http(429, "Quota exceeded"))

    response = cliente.post(f"/api/v1/lotes-auditoria/{lote_id}/carta?transportista=Chilexpress")

    assert response.status_code == 200
    carta = response.json()
    assert carta["origen"] == "PLANTILLA"
    assert "límite gratuito" in carta["motivo_plantilla"]
    assert "$15.000" in carta["texto"] and "G-002" in carta["texto"]


def test_endpoint_carta_valida_lote_y_transportista(cliente, sesion_bd, empresa_ejemplo):
    sin_auditar = _cargar_lote(cliente, sesion_bd, empresa_ejemplo.id, auditar=False)
    assert (
        cliente.post(
            f"/api/v1/lotes-auditoria/{sin_auditar}/carta?transportista=Chilexpress"
        ).status_code
        == 409
    )

    assert (
        cliente.post(
            "/api/v1/lotes-auditoria/no-existe/carta?transportista=Chilexpress"
        ).status_code
        == 404
    )
    assert (
        cliente.post(f"/api/v1/lotes-auditoria/{sin_auditar}/carta").status_code == 422
    )  # falta el transportista

    assert cliente.post(f"/api/v1/lotes-auditoria/{sin_auditar}/auditar").status_code == 200
    desconocido = cliente.post(f"/api/v1/lotes-auditoria/{sin_auditar}/carta?transportista=Starken")
    assert desconocido.status_code == 404

    # Fletes Don Tito no tiene regla SLA: no tiene guías fuera de plazo que reclamar
    sin_multas = cliente.post(
        f"/api/v1/lotes-auditoria/{sin_auditar}/carta?transportista=Fletes Don Tito"
    )
    assert sin_multas.status_code == 400
    assert "no hay nada que reclamar" in sin_multas.json()["detail"]


def test_estado_ia_no_expone_la_clave(cliente):
    response = cliente.get("/api/v1/ia/estado")

    assert response.status_code == 200
    assert response.json() == {
        "configurada": True,
        "proveedor": "Gemini",
        "modelo": "modelo-de-prueba",
        "proveedores": [
            {
                "nombre": "Gemini",
                "papel": "principal",
                "configurado": True,
                "modelo": "modelo-de-prueba",
            },
            {
                "nombre": "Claude",
                "papel": "respaldo",
                "configurado": False,  # Claude no tiene clave en estas pruebas
                "modelo": "claude-de-prueba",
            },
        ],
    }
    assert "clave-de-prueba" not in response.text
