"""
Pruebas de los endpoints de consulta que usa el frontend:
empresas, listado de lotes, resumen del lote y guías del lote.
"""

import pandas as pd

from app.consultas import _horas
from app.ia_cartas import _decimal as _decimal_carta
from app.models import Envio, LoteAuditoria, ReglaSLA, Transportista


def _bytes_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _cargar_lote_mixto(cliente, sesion_bd, empresa_id) -> str:
    """
    4 guías: 1 cumple, 1 incumple (ambas Chilexpress, con regla),
    1 sin fecha de entrega (despachada en 2025: su plazo ya venció) y 1
    entregada por un transportista sin regla SLA.
    """
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
            "N° Guía": ["G-001", "G-002", "G-003", "G-004"],
            "Transportista": ["Chilexpress", "chilexpress", "Chilexpress", "Fletes Don Tito"],
            "Fecha Despacho": ["2025-11-10 09:00"] * 4,
            "Fecha Entrega": ["2025-11-10 14:00", "2025-11-12 18:00", None, "2025-11-11 10:00"],
            "Destino": ["Maipú", "Temuco", "Arica", "Rancagua"],
        }
    )
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
        "total": 4,
        "cumplidos": 1,
        "incumplidos": 1,
        "en_transito": 0,
        "vencidas_sin_entrega": 1,
        "sin_regla": 1,
        "datos_invalidos": 0,
        "pendientes": 0,
        "monto_multa_total": 15000,
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
    assert filas[0]["nombre"] == "Chilexpress"  # primero el que debe multa
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
    assert resultado["G-003"]["resultado"] == "VENCIDA_SIN_ENTREGA"
    assert resultado["G-003"]["fecha_entrega"] is None
    assert resultado["G-003"]["monto_multa"] is None  # sin entrega no hay multa
    assert resultado["G-004"]["resultado"] == "SIN_REGLA"
    assert resultado["G-004"]["monto_multa"] is None


def test_cada_guia_trae_su_justificacion(cliente, sesion_bd, empresa_ejemplo):
    lote_id = _cargar_lote_mixto(cliente, sesion_bd, empresa_ejemplo.id)
    cliente.post(f"/api/v1/lotes-auditoria/{lote_id}/auditar")
    guias = {
        e["numero_guia"]: e for e in cliente.get(f"/api/v1/lotes-auditoria/{lote_id}/envios").json()
    }

    # Despacho lunes 10-11-2025 09:00 + 24 horas hábiles -> miércoles 12-11 a las 15:00
    en_plazo, atrasada = guias["G-001"], guias["G-002"]
    assert en_plazo["entregada"] is True
    assert en_plazo["fecha_limite"].startswith("2025-11-12T15:00")
    assert en_plazo["horas_habiles_permitidas"] == 24
    assert en_plazo["horas_habiles_transcurridas"] == 5
    assert "antes de la fecha límite (12-11-2025 15:00)" in en_plazo["justificacion"]
    assert "Usó 5 de las 24 horas hábiles" in en_plazo["justificacion"]

    assert atrasada["horas_habiles_transcurridas"] == 27
    assert atrasada["horas_atraso"] == 3
    assert "después de la fecha límite (12-11-2025 15:00)" in atrasada["justificacion"]
    assert "3 horas hábiles de atraso" in atrasada["justificacion"]
    assert "$15.000" in atrasada["justificacion"]
    # Mismo redondeo que la tabla de la web (27,25 -> 27,3, no 27,2), en la
    # justificación y en la carta.
    assert _horas(27.25) == "27,3" and _horas(24.0) == "24"
    assert _decimal_carta(27.25) == "27,3"

    vencida = guias["G-003"]
    assert vencida["entregada"] is False
    assert "no registra entrega" in vencida["justificacion"]
    assert "No se aplica multa" in vencida["justificacion"]
    assert vencida["horas_atraso"] > 0

    assert "no tiene una regla SLA activa" in guias["G-004"]["justificacion"]

    # Criterios de la auditoría visibles en el resumen
    resumen = cliente.get(f"/api/v1/lotes-auditoria/{lote_id}/resumen").json()
    assert resumen["fecha_corte"] is not None
    assert resumen["empresa_nombre"] == "Retail Demo SpA"
    assert resumen["empresa_rut"] == "76.123.456-7"
    criterios = resumen["criterios"]
    assert criterios["jornada"] == "09:00 a 18:00, de lunes a viernes"
    assert criterios["despacho_desde"].startswith("2025-11-10")
    assert any("vencida sin entrega" in regla for regla in criterios["reglas"])


def test_datos_inconsistentes_no_se_auditan_ni_se_multan(cliente, sesion_bd, empresa_ejemplo):
    transportista = Transportista(nombre="Starken")
    sesion_bd.add(transportista)
    sesion_bd.flush()
    sesion_bd.add(
        ReglaSLA(
            transportista_id=transportista.id,
            horas_habiles_maximas=24,
            multa_por_incumplimiento=12000,
            activa=True,
        )
    )
    sesion_bd.commit()
    df = pd.DataFrame(
        {
            "N° Guía": ["S-001", "S-002", "S-002", "S-003"],
            "Transportista": ["Starken"] * 4,
            "Fecha Despacho": [
                "2025-11-12 10:00",  # entrega antes del despacho
                "2025-11-10 09:00",  # repetida: esta se audita (despacho más antiguo)
                "2025-11-11 09:00",  # repetida: esta no
                "2099-01-05 09:00",  # fecha futura
            ],
            "Fecha Entrega": [
                "2025-11-11 10:00",
                "2025-11-14 18:00",
                "2025-11-14 18:00",
                None,
            ],
        }
    )
    carga = cliente.post(
        f"/api/v1/lotes-auditoria/cargar?empresa_id={empresa_ejemplo.id}",
        files={"file": ("envios.csv", _bytes_csv(df), "text/csv")},
    )
    lote_id = carga.json()["lote_id"]
    auditoria = cliente.post(f"/api/v1/lotes-auditoria/{lote_id}/auditar").json()

    assert auditoria["datos_invalidos"] == 3
    assert auditoria["envios_incumplidos"] == 1
    assert auditoria["monto_multa_total"] == 12000  # la guía repetida se multa una sola vez

    guias = cliente.get(f"/api/v1/lotes-auditoria/{lote_id}/envios").json()
    invalidas = [g for g in guias if g["resultado"] == "DATOS_INVALIDOS"]
    assert len(invalidas) == 3
    assert all(g["monto_multa"] is None for g in invalidas)
    textos = " ".join(g["justificacion"] for g in invalidas)
    assert "es anterior a la de despacho" in textos
    assert "aparece 2 veces en el archivo" in textos
    assert "posterior a la fecha de corte" in textos

    lotes = cliente.get(f"/api/v1/lotes-auditoria?empresa_id={empresa_ejemplo.id}").json()
    assert lotes[0]["conteos"]["datos_invalidos"] == 3
    assert lotes[0]["conteos"]["incumplidos"] == 1


def test_resumen_y_envios_de_lote_inexistente_dan_404(cliente):
    assert cliente.get("/api/v1/lotes-auditoria/no-existe/resumen").status_code == 404
    assert cliente.get("/api/v1/lotes-auditoria/no-existe/envios").status_code == 404


def test_lote_auditado_antes_de_la_migracion_pide_volver_a_auditar(
    cliente, sesion_bd, empresa_ejemplo
):
    lote_id = _cargar_lote_mixto(cliente, sesion_bd, empresa_ejemplo.id)
    cliente.post(f"/api/v1/lotes-auditoria/{lote_id}/auditar")
    # Simula un lote auditado con la versión anterior: sin fecha de corte ni fecha límite.
    sesion_bd.query(Envio).update({Envio.fecha_limite: None, Envio.resultado: None})
    sesion_bd.query(LoteAuditoria).update({LoteAuditoria.fecha_corte: None})
    sesion_bd.commit()

    guias = {
        e["numero_guia"]: e for e in cliente.get(f"/api/v1/lotes-auditoria/{lote_id}/envios").json()
    }
    assert guias["G-002"]["resultado"] == "INCUMPLIDO"  # criterio anterior
    assert "Vuelva a auditar" in guias["G-002"]["justificacion"]
    assert guias["G-003"]["resultado"] == "EN_TRANSITO"
