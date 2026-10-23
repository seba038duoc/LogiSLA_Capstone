"""
Pruebas de los endpoints de consulta que usa el frontend:
empresas, listado de lotes, resumen del lote y guías del lote.
"""
import pandas as pd

from app.models import Transportista, ReglaSLA


def _bytes_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _cargar_lote_mixto(cliente, sesion_bd, empresa_id) -> str:
    """
    4 guías: 1 cumple, 1 incumple (ambas Chilexpress, con regla),
    1 en tránsito (sin fecha de entrega) y 1 entregada por un
    transportista sin regla SLA.
    """
    transportista = Transportista(nombre="Chilexpress")
    sesion_bd.add(transportista)
    sesion_bd.flush()
    sesion_bd.add(ReglaSLA(
        transportista_id=transportista.id, horas_habiles_maximas=24,
        multa_por_incumplimiento=15000, activa=True,
    ))
    sesion_bd.commit()

    df = pd.DataFrame({
        "N° Guía": ["G-001", "G-002", "G-003", "G-004"],
        "Transportista": ["Chilexpress", "chilexpress", "Chilexpress", "Fletes Don Tito"],
        "Fecha Despacho": ["2025-11-10 09:00"] * 4,
        "Fecha Entrega": ["2025-11-10 14:00", "2025-11-12 18:00", None, "2025-11-11 10:00"],
        "Destino": ["Maipú", "Temuco", "Arica", "Rancagua"],
    })
    carga = cliente.post(
        f"/api/v1/lotes-auditoria/cargar?empresa_id={empresa_id}",
        files={"file": ("envios.csv", _bytes_csv(df), "text/csv")},
    )
    assert carga.status_code == 200
    return carga.json()["lote_id"]


def test_listar_empresas(cliente, empresa_ejemplo):
    response = cliente.get("/api/v1/empresas")
    assert response.status_code == 200
    assert response.json() == [
        {"id": empresa_ejemplo.id, "nombre": "Retail Demo SpA", "rut": "76.123.456-7"}
    ]


def test_listar_lotes_requiere_empresa_existente(cliente):
    response = cliente.get("/api/v1/lotes-auditoria?empresa_id=no-existe")
    assert response.status_code == 404


def test_lote_sin_auditar_queda_todo_pendiente(cliente, sesion_bd, empresa_ejemplo):
    lote_id = _cargar_lote_mixto(cliente, sesion_bd, empresa_ejemplo.id)

    lotes = cliente.get(f"/api/v1/lotes-auditoria?empresa_id={empresa_ejemplo.id}").json()
    assert len(lotes) == 1
    assert lotes[0]["id"] == lote_id
    assert lotes[0]["estado"] == "PENDIENTE"
    assert lotes[0]["conteos"]["total"] == 4
    assert lotes[0]["conteos"]["pendientes"] == 4
    assert lotes[0]["conteos"]["monto_multa_total"] == 0

    envios = cliente.get(f"/api/v1/lotes-auditoria/{lote_id}/envios").json()
    assert {e["resultado"] for e in envios} == {"PENDIENTE"}

    # aun sin auditar, el resumen ya muestra el SLA de cada transportista
    resumen = cliente.get(f"/api/v1/lotes-auditoria/{lote_id}/resumen").json()
    por_nombre = {f["nombre"].lower(): f for f in resumen["por_transportista"]}
    assert por_nombre["chilexpress"]["horas_habiles_maximas"] == 24
    assert por_nombre["fletes don tito"]["horas_habiles_maximas"] is None


def test_lote_auditado_clasifica_cada_guia(cliente, sesion_bd, empresa_ejemplo):
    lote_id = _cargar_lote_mixto(cliente, sesion_bd, empresa_ejemplo.id)
    assert cliente.post(f"/api/v1/lotes-auditoria/{lote_id}/auditar").status_code == 200

    esperado = {
        "total": 4, "cumplidos": 1, "incumplidos": 1, "en_transito": 1,
        "sin_regla": 1, "pendientes": 0, "monto_multa_total": 15000,
    }

    # el listado (consulta SQL agrupada) y el resumen (recorrido en Python)
    # tienen que dar exactamente los mismos conteos
    lotes = cliente.get(f"/api/v1/lotes-auditoria?empresa_id={empresa_ejemplo.id}").json()
    assert lotes[0]["estado"] == "COMPLETADO"
    assert lotes[0]["conteos"] == esperado

    resumen = cliente.get(f"/api/v1/lotes-auditoria/{lote_id}/resumen").json()
    assert resumen["conteos"] == esperado

    # "Chilexpress" y "chilexpress" se agrupan en una sola fila
    filas = resumen["por_transportista"]
    assert len(filas) == 2
    assert filas[0]["nombre"] == "Chilexpress"          # primero el que debe multa
    assert filas[0]["conteos"]["total"] == 3
    assert filas[0]["conteos"]["incumplidos"] == 1
    assert filas[0]["multa_por_incumplimiento"] == 15000
    assert filas[1]["nombre"] == "Fletes Don Tito"
    assert filas[1]["conteos"]["sin_regla"] == 1
    assert filas[1]["horas_habiles_maximas"] is None

    envios = cliente.get(f"/api/v1/lotes-auditoria/{lote_id}/envios").json()
    resultado = {e["numero_guia"]: e for e in envios}
    assert resultado["G-001"]["resultado"] == "CUMPLIDO"
    assert resultado["G-001"]["monto_multa"] == 0
    assert resultado["G-002"]["resultado"] == "INCUMPLIDO"
    assert resultado["G-002"]["monto_multa"] == 15000
    assert resultado["G-002"]["horas_atraso"] > 0
    assert resultado["G-002"]["transportista"] == "Chilexpress"
    assert resultado["G-003"]["resultado"] == "EN_TRANSITO"
    assert resultado["G-003"]["fecha_entrega"] is None
    assert resultado["G-004"]["resultado"] == "SIN_REGLA"
    assert resultado["G-004"]["monto_multa"] is None


def test_resumen_y_envios_de_lote_inexistente_dan_404(cliente):
    assert cliente.get("/api/v1/lotes-auditoria/no-existe/resumen").status_code == 404
    assert cliente.get("/api/v1/lotes-auditoria/no-existe/envios").status_code == 404
