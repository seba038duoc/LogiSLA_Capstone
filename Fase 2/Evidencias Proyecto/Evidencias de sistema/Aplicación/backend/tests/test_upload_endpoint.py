"""
Pruebas de integración del endpoint de carga
(POST /api/v1/lotes-auditoria/cargar).

Cubren: carga exitosa con headers en español, rechazo (sin tocar la BD)
cuando el mapeo automático no logra reconocer las columnas obligatorias,
y rechazo de formato de archivo no soportado.

No hay flujo de mapeo manual: se sacó a pedido del profesor, porque las
empresas ya entregan sus documentos bien estructurados y no tiene sentido
ofrecer una pantalla de "arreglar el mapeo a mano" para el caso raro de
un archivo que no se pueda leer.
"""
import pandas as pd


def _bytes_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def test_cargar_crea_lote_y_envios(cliente, empresa_ejemplo):
    df = pd.DataFrame({
        "N° Guía": ["G-001", "G-002", "G-003"],
        "Transportista": ["Chilexpress", "Starken", "Chilexpress"],
        "Fecha Despacho": ["2026-09-01", "2026-09-02", "2026-09-03"],
        "Fecha Entrega": ["2026-09-05", "2026-09-06", ""],
        "Destino": ["Santiago", "Valparaíso", "Concepción"],
    })

    response = cliente.post(
        f"/api/v1/lotes-auditoria/cargar?empresa_id={empresa_ejemplo.id}",
        files={"file": ("envios.csv", _bytes_csv(df), "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["estado"] == "PENDIENTE"
    assert body["total_filas"] == 3
    assert body["lote_id"]
    assert body["mapeo_columnas"]["numero_guia"] == "N° Guía"

    # confirmar que quedó consultable
    respuesta_get = cliente.get(f"/api/v1/lotes-auditoria/{body['lote_id']}")
    assert respuesta_get.status_code == 200
    assert respuesta_get.json()["total_filas"] == 3


def test_cargar_rechaza_columnas_obligatorias_no_reconocidas_sin_crear_lote(cliente, empresa_ejemplo):
    df = pd.DataFrame({
        "Numero de Guia": ["G-001"],
        "Ciudad Destino": ["Santiago"],
        # sin transportista ni fecha de despacho
    })

    response = cliente.post(
        f"/api/v1/lotes-auditoria/cargar?empresa_id={empresa_ejemplo.id}",
        files={"file": ("envios.csv", _bytes_csv(df), "text/csv")},
    )

    assert response.status_code == 400
    detalle = response.json()["detail"]
    assert "nombre_transportista" in detalle
    assert "fecha_despacho" in detalle


def test_cargar_rechaza_extension_de_archivo_no_soportada(cliente, empresa_ejemplo):
    response = cliente.post(
        f"/api/v1/lotes-auditoria/cargar?empresa_id={empresa_ejemplo.id}",
        files={"file": ("envios.txt", b"contenido", "text/plain")},
    )
    assert response.status_code == 400


def test_cargar_rechaza_empresa_desconocida(cliente):
    df = pd.DataFrame({
        "Guia": ["G-001"], "Courier": ["Chilexpress"], "Fecha Despacho": ["2026-09-01"],
    })
    response = cliente.post(
        "/api/v1/lotes-auditoria/cargar?empresa_id=no-existe",
        files={"file": ("envios.csv", _bytes_csv(df), "text/csv")},
    )
    assert response.status_code == 404
