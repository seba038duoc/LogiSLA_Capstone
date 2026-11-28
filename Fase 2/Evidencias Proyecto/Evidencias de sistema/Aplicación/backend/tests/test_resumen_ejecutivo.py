"""
Pruebas del resumen ejecutivo con IA (HU-17): app/ia_resumen.py y
POST /api/v1/lotes-auditoria/{lote_id}/resumen-ejecutivo.

Igual que en test_carta_reclamo.py, la IA se simula (solo Gemini con clave):
ninguna prueba sale a internet ni gasta cuota.
"""

import io
import json
import urllib.error

import pandas as pd
import pytest

from app import ia_proveedores, ia_resumen
from app.models import ReglaSLA, Transportista

CONFIG_PRUEBA = ia_proveedores.ConfiguracionIA(
    claude=ia_proveedores.ConfiguracionProveedor(
        ia_proveedores.CLAUDE, None, "claude-de-prueba", "https://claude.invalid/v1", 5
    ),
    gemini=ia_proveedores.ConfiguracionProveedor(
        ia_proveedores.GEMINI, "clave-de-prueba", "modelo-de-prueba", "https://gemini.invalid", 5
    ),
)

RESUMEN_IA_VALIDO = (
    "La auditoría del lote envios.csv revisó las entregas de los transportistas y obtuvo un "
    "cumplimiento del SLA de 50,0 %, con una guía en plazo y otra fuera de plazo.\n\n"
    "Las multas por reclamar suman $15.000 y se concentran en Chilexpress, único transportista "
    "con entregas atrasadas en este período.\n\n"
    "Se recomienda enviar la carta de reclamo a Chilexpress y revisar su servicio en el próximo "
    "período antes de renovar las condiciones del contrato."
)


def _respuesta_gemini(texto: str) -> bytes:
    return json.dumps({"candidates": [{"content": {"parts": [{"text": texto}]}}]}).encode()


@pytest.fixture(autouse=True)
def gemini_simulado(monkeypatch):
    monkeypatch.setattr(ia_proveedores, "obtener_configuracion", lambda: CONFIG_PRUEBA)

    def sin_red(solicitud, tiempo_espera_s):
        raise AssertionError("Las pruebas no deben llamar a Gemini de verdad")

    monkeypatch.setattr(ia_proveedores, "_abrir_url", sin_red)


def _simular(monkeypatch, respuesta=None, error=None):
    solicitudes = []

    def falso(solicitud, tiempo_espera_s):
        solicitudes.append(solicitud)
        if error is not None:
            raise error
        return respuesta

    monkeypatch.setattr(ia_proveedores, "_abrir_url", falso)
    return solicitudes


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
        files={"file": ("envios.csv", df.to_csv(index=False).encode("utf-8"), "text/csv")},
    )
    assert carga.status_code == 200
    lote_id = carga.json()["lote_id"]
    if auditar:
        assert cliente.post(f"/api/v1/lotes-auditoria/{lote_id}/auditar").status_code == 200
    return lote_id


def test_resumen_redactado_por_ia(cliente, sesion_bd, empresa_ejemplo, monkeypatch):
    lote_id = _cargar_lote(cliente, sesion_bd, empresa_ejemplo.id)
    solicitudes = _simular(monkeypatch, respuesta=_respuesta_gemini(RESUMEN_IA_VALIDO))

    response = cliente.post(f"/api/v1/lotes-auditoria/{lote_id}/resumen-ejecutivo")

    assert response.status_code == 200
    resumen = response.json()
    assert resumen["origen"] == "IA"
    assert resumen["proveedor"] == "Gemini"
    assert resumen["modelo"] == "modelo-de-prueba"
    assert resumen["motivo_plantilla"] is None
    assert "$15.000" in resumen["texto"]

    # A la IA solo va el resumen agregado: ningún número de guía ni destino
    prompt = json.loads(solicitudes[0].data)["contents"][0]["parts"][0]["text"]
    assert "$15.000" in prompt and "50,0 %" in prompt and "Chilexpress" in prompt
    assert "G-002" not in prompt and "Temuco" not in prompt


def test_resumen_con_plantilla_si_gemini_falla(cliente, sesion_bd, empresa_ejemplo, monkeypatch):
    lote_id = _cargar_lote(cliente, sesion_bd, empresa_ejemplo.id)
    cuerpo = json.dumps({"error": {"message": "Quota exceeded"}}).encode()
    error = urllib.error.HTTPError("https://gemini.invalid", 429, "", {}, io.BytesIO(cuerpo))
    _simular(monkeypatch, error=error)

    response = cliente.post(f"/api/v1/lotes-auditoria/{lote_id}/resumen-ejecutivo")

    assert response.status_code == 200
    resumen = response.json()
    assert resumen["origen"] == "PLANTILLA"
    assert "límite gratuito" in resumen["motivo_plantilla"]
    texto = resumen["texto"]
    assert "Se auditaron 2 de las 3 guías del archivo envios.csv" in texto
    assert "cumplimiento del SLA fue de 50,0 %" in texto
    assert "1 guía sin regla SLA" in texto
    assert "asciende a $15.000, repartido entre Chilexpress (1 guía, $15.000)" in texto
    assert "revisar el servicio de Chilexpress" in texto


@pytest.mark.parametrize(
    "texto, fragmento",
    [
        (RESUMEN_IA_VALIDO.replace("$15.000", "$20.000"), "monto total"),
        (RESUMEN_IA_VALIDO + " Se estiman pérdidas de $80.000 adicionales.", "$80.000"),
        ("Resumen breve.", "demasiado corta"),
    ],
)
def test_respuesta_invalida_se_descarta(
    cliente, sesion_bd, empresa_ejemplo, monkeypatch, texto, fragmento
):
    lote_id = _cargar_lote(cliente, sesion_bd, empresa_ejemplo.id)
    _simular(monkeypatch, respuesta=_respuesta_gemini(texto))

    resumen = cliente.post(f"/api/v1/lotes-auditoria/{lote_id}/resumen-ejecutivo").json()

    assert resumen["origen"] == "PLANTILLA"
    assert fragmento in resumen["motivo_plantilla"]


def test_resumen_valida_el_lote(cliente, sesion_bd, empresa_ejemplo):
    sin_auditar = _cargar_lote(cliente, sesion_bd, empresa_ejemplo.id, auditar=False)
    url = f"/api/v1/lotes-auditoria/{sin_auditar}/resumen-ejecutivo"
    assert cliente.post(url).status_code == 409
    assert cliente.post("/api/v1/lotes-auditoria/no-existe/resumen-ejecutivo").status_code == 404


def test_plantilla_sin_multas():
    datos = ia_resumen.DatosResumen(
        empresa_nombre="Retail Demo SpA",
        nombre_archivo="octubre.csv",
        total_guias=4,
        cumplidas=4,
        incumplidas=0,
        en_transito=0,
        sin_regla=0,
        monto_total=0,
        periodo=None,
        transportistas=[ia_resumen.ResultadoTransportista("Starken", 4, 0, 0, 12000, 0)],
    )

    resultado = ia_resumen.generar_resumen(datos, usar_ia=False)

    assert resultado.origen == "PLANTILLA"
    assert "cumplimiento del SLA fue de 100,0 %" in resultado.texto
    assert "No hay multas que reclamar" in resultado.texto
