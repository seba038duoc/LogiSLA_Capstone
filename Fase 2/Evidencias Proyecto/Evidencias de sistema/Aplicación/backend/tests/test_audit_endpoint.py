"""
Pruebas de integración del endpoint del motor de auditoría
(POST /api/v1/lotes-auditoria/{lote_id}/auditar).

Reutiliza el flujo real de ingesta (/cargar) para armar el lote, en vez
de insertar Envio a mano, así se prueba el camino completo tal como lo
recorre un archivo real subido por el usuario.
"""
import pandas as pd

from app.models import Transportista, ReglaSLA


def _bytes_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def test_auditar_calcula_incumplimientos_y_multas(cliente, sesion_bd, empresa_ejemplo):
    transportista = Transportista(nombre="Chilexpress")
    sesion_bd.add(transportista)
    sesion_bd.flush()
    sesion_bd.add(ReglaSLA(transportista_id=transportista.id, horas_habiles_maximas=24, multa_por_incumplimiento=15000, activa=True))
    sesion_bd.commit()

    df = pd.DataFrame({
        "N° Guía": ["G-001", "G-002"],
        "Transportista": ["Chilexpress", "Chilexpress"],
        "Fecha Despacho": ["2025-11-10 09:00", "2025-11-10 09:00"],
        "Fecha Entrega": ["2025-11-10 14:00", "2025-11-12 18:00"],
    })
    carga = cliente.post(
        f"/api/v1/lotes-auditoria/cargar?empresa_id={empresa_ejemplo.id}",
        files={"file": ("envios.csv", _bytes_csv(df), "text/csv")},
    )
    assert carga.status_code == 200
    lote_id = carga.json()["lote_id"]

    response = cliente.post(f"/api/v1/lotes-auditoria/{lote_id}/auditar")

    assert response.status_code == 200
    body = response.json()
    assert body["lote_id"] == lote_id
    assert body["total_envios"] == 2
    assert body["envios_auditados"] == 2
    assert body["envios_incumplidos"] == 1
    assert body["envios_cumplidos"] == 1
    assert body["monto_multa_total"] == 15000

    # el lote queda consultable como COMPLETADO después de auditar
    respuesta_get = cliente.get(f"/api/v1/lotes-auditoria/{lote_id}")
    assert respuesta_get.json()["estado"] == "COMPLETADO"


def test_auditar_reporta_envios_sin_regla_sla_que_matchee(cliente, empresa_ejemplo):
    df = pd.DataFrame({
        "N° Guía": ["G-010"],
        "Transportista": ["Transportista Sin Regla"],
        "Fecha Despacho": ["2025-11-10 09:00"],
        "Fecha Entrega": ["2025-11-10 14:00"],
    })
    carga = cliente.post(
        f"/api/v1/lotes-auditoria/cargar?empresa_id={empresa_ejemplo.id}",
        files={"file": ("envios.csv", _bytes_csv(df), "text/csv")},
    )
    lote_id = carga.json()["lote_id"]

    response = cliente.post(f"/api/v1/lotes-auditoria/{lote_id}/auditar")

    assert response.status_code == 200
    body = response.json()
    assert body["omitidos_sin_regla"] == 1
    assert body["envios_auditados"] == 0


def test_auditar_devuelve_404_para_lote_desconocido(cliente):
    response = cliente.post("/api/v1/lotes-auditoria/no-existe/auditar")
    assert response.status_code == 404
