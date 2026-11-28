"""
Pruebas unitarias del motor de auditoría (Sprint 2).

Las fechas de los casos de fin de semana y feriado no son inventadas a
mano: se verificaron ejecutando workalendar.america.Chile() para 2025
antes de escribir estos tests, para no adivinar mal un feriado chileno.
- 2025-11-15/16 (sáb/dom): fin de semana normal, sin feriados cerca.
- 2025-09-18 y 2025-09-19 (jue/vie): feriados nacionales chilenos
  ("Fiestas Patrias"), confirmados vía cal.holidays(2025).
"""

from datetime import date, datetime, timedelta

from app.audit_engine import (
    CUMPLIDO,
    EN_TRANSITO,
    VENCIDA_SIN_ENTREGA,
    dias_no_habiles,
    sumar_horas_habiles,
    auditar_envio,
    horas_habiles_entre,
    buscar_regla_sla_activa,
    obtener_o_crear_transportista,
    ejecutar_auditoria_lote,
)
from app.models import LoteAuditoria, EstadoLote, Transportista, Envio, ReglaSLA


class TestHorasHabilesEntre:
    def test_mismo_dia_dentro_del_horario_habil(self):
        inicio = datetime(2025, 11, 10, 9, 0)  # lunes hábil
        fin = datetime(2025, 11, 10, 14, 0)
        assert horas_habiles_entre(inicio, fin) == 5.0

    def test_salta_el_fin_de_semana(self):
        inicio = datetime(2025, 11, 14, 16, 0)  # viernes 16:00
        fin = datetime(2025, 11, 17, 10, 0)  # lunes siguiente 10:00
        # viernes: 16:00-18:00 (2h) + sáb/dom: 0h + lunes: 09:00-10:00 (1h)
        assert horas_habiles_entre(inicio, fin) == 3.0

    def test_salta_feriados_chilenos(self):
        inicio = datetime(2025, 9, 17, 15, 0)  # miércoles 15:00
        fin = datetime(2025, 9, 22, 11, 0)  # lunes siguiente 11:00
        # miércoles: 15:00-18:00 (3h) + jue/vie feriados + fin de semana
        # + lunes: 09:00-11:00 (2h)
        assert horas_habiles_entre(inicio, fin) == 5.0

    def test_recorta_despacho_antes_del_horario_de_apertura(self):
        inicio = datetime(2025, 11, 10, 7, 0)
        fin = datetime(2025, 11, 10, 10, 0)
        assert horas_habiles_entre(inicio, fin) == 1.0

    def test_recorta_entrega_despues_del_horario_de_cierre(self):
        inicio = datetime(2025, 11, 10, 9, 0)
        fin = datetime(2025, 11, 10, 20, 0)
        assert horas_habiles_entre(inicio, fin) == 9.0

    def test_varios_dias_habiles_completos(self):
        inicio = datetime(2025, 11, 10, 9, 0)  # lunes
        fin = datetime(2025, 11, 12, 18, 0)  # miércoles
        assert horas_habiles_entre(inicio, fin) == 27.0  # 3 días x 9h

    def test_devuelve_cero_cuando_fin_no_es_posterior_a_inicio(self):
        misma = datetime(2025, 11, 10, 9, 0)
        assert horas_habiles_entre(misma, misma) == 0.0
        assert horas_habiles_entre(misma, misma - timedelta(hours=1)) == 0.0

    def test_devuelve_cero_con_fechas_none(self):
        assert horas_habiles_entre(None, datetime(2025, 11, 10, 9, 0)) == 0.0
        assert horas_habiles_entre(datetime(2025, 11, 10, 9, 0), None) == 0.0


class TestAuditarEnvio:
    def test_marca_incumplimiento_cuando_supera_el_limite_del_sla(self):
        envio = Envio(
            fecha_despacho=datetime(2025, 11, 10, 9, 0),
            fecha_entrega=datetime(2025, 11, 12, 18, 0),  # 27h hábiles reales
        )
        regla_sla = ReglaSLA(horas_habiles_maximas=24, multa_por_incumplimiento=15000)

        resultado = auditar_envio(envio, regla_sla)

        assert resultado.incumplio_sla is True
        assert resultado.horas_atraso == 3.0
        assert resultado.monto_multa == 15000

    def test_marca_cumplimiento_cuando_esta_dentro_del_limite_del_sla(self):
        envio = Envio(
            fecha_despacho=datetime(2025, 11, 10, 9, 0),
            fecha_entrega=datetime(2025, 11, 10, 14, 0),  # 5h hábiles reales
        )
        regla_sla = ReglaSLA(horas_habiles_maximas=48, multa_por_incumplimiento=15000)

        resultado = auditar_envio(envio, regla_sla)

        assert resultado.incumplio_sla is False
        assert resultado.horas_atraso == 0.0
        assert resultado.monto_multa == 0.0

    def test_el_limite_exacto_no_es_incumplimiento(self):
        # 9h hábiles reales, límite de la regla también 9h -> no incumple
        envio = Envio(
            fecha_despacho=datetime(2025, 11, 10, 9, 0),
            fecha_entrega=datetime(2025, 11, 10, 18, 0),
        )
        regla_sla = ReglaSLA(horas_habiles_maximas=9, multa_por_incumplimiento=15000)

        resultado = auditar_envio(envio, regla_sla)

        assert resultado.incumplio_sla is False


class TestObtenerOCrearTransportista:
    def test_crea_transportista_nuevo(self, sesion_bd):
        transportista = obtener_o_crear_transportista(sesion_bd, "Chilexpress")
        sesion_bd.commit()

        assert transportista is not None
        assert transportista.nombre == "Chilexpress"

    def test_matchea_transportista_existente_sin_importar_mayusculas_ni_espacios(self, sesion_bd):
        sesion_bd.add(Transportista(nombre="Starken"))
        sesion_bd.commit()

        transportista = obtener_o_crear_transportista(sesion_bd, "  starken  ")

        assert transportista.nombre == "Starken"
        assert sesion_bd.query(Transportista).count() == 1

    def test_devuelve_none_sin_nombre(self, sesion_bd):
        assert obtener_o_crear_transportista(sesion_bd, None) is None
        assert obtener_o_crear_transportista(sesion_bd, "   ") is None


class TestBuscarReglaSlaActiva:
    def test_prefiere_la_regla_generica_sobre_la_especifica(self, sesion_bd):
        transportista = Transportista(nombre="Chilexpress")
        sesion_bd.add(transportista)
        sesion_bd.flush()
        sesion_bd.add(
            ReglaSLA(
                transportista_id=transportista.id,
                tipo_servicio="express",
                horas_habiles_maximas=24,
                multa_por_incumplimiento=20000,
                activa=True,
            )
        )
        sesion_bd.add(
            ReglaSLA(
                transportista_id=transportista.id,
                tipo_servicio=None,
                horas_habiles_maximas=48,
                multa_por_incumplimiento=15000,
                activa=True,
            )
        )
        sesion_bd.commit()

        regla = buscar_regla_sla_activa(sesion_bd, transportista.id)

        assert regla.tipo_servicio is None
        assert regla.horas_habiles_maximas == 48

    def test_ignora_reglas_inactivas(self, sesion_bd):
        transportista = Transportista(nombre="Starken")
        sesion_bd.add(transportista)
        sesion_bd.flush()
        sesion_bd.add(
            ReglaSLA(
                transportista_id=transportista.id,
                horas_habiles_maximas=60,
                multa_por_incumplimiento=12000,
                activa=False,
            )
        )
        sesion_bd.commit()

        assert buscar_regla_sla_activa(sesion_bd, transportista.id) is None

    def test_devuelve_none_sin_transportista_id(self, sesion_bd):
        assert buscar_regla_sla_activa(sesion_bd, None) is None


class TestEjecutarAuditoriaLote:
    def test_audita_envio_y_vincula_transportista(self, sesion_bd, empresa_ejemplo):
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

        lote = LoteAuditoria(
            empresa_id=empresa_ejemplo.id,
            nombre_archivo="envios.csv",
            estado=EstadoLote.PENDIENTE,
            total_filas=1,
        )
        sesion_bd.add(lote)
        sesion_bd.flush()
        envio = Envio(
            lote_auditoria_id=lote.id,
            nombre_transportista_original="Chilexpress",
            numero_guia="G-001",
            fecha_despacho=datetime(2025, 11, 10, 9, 0),
            fecha_entrega=datetime(2025, 11, 12, 18, 0),  # 27h reales > 24h SLA
        )
        sesion_bd.add(envio)
        sesion_bd.commit()

        resumen = ejecutar_auditoria_lote(sesion_bd, lote)

        assert resumen.total_envios == 1
        assert resumen.envios_auditados == 1
        assert resumen.envios_incumplidos == 1
        assert resumen.envios_cumplidos == 0
        assert resumen.monto_multa_total == 15000

        sesion_bd.refresh(envio)
        assert envio.transportista_id == transportista.id
        assert envio.incumplio_sla is True
        assert envio.horas_atraso == 3.0
        assert envio.monto_multa == 15000
        assert lote.estado == EstadoLote.COMPLETADO
        assert lote.fecha_procesado is not None

    def test_omite_envio_sin_fecha_de_entrega(self, sesion_bd, empresa_ejemplo):
        transportista = Transportista(nombre="Starken")
        sesion_bd.add(transportista)
        sesion_bd.flush()
        sesion_bd.add(
            ReglaSLA(
                transportista_id=transportista.id,
                horas_habiles_maximas=60,
                multa_por_incumplimiento=12000,
                activa=True,
            )
        )
        sesion_bd.commit()

        lote = LoteAuditoria(
            empresa_id=empresa_ejemplo.id,
            nombre_archivo="envios.csv",
            estado=EstadoLote.PENDIENTE,
            total_filas=1,
        )
        sesion_bd.add(lote)
        sesion_bd.flush()
        envio = Envio(
            lote_auditoria_id=lote.id,
            nombre_transportista_original="Starken",
            numero_guia="G-002",
            fecha_despacho=datetime(2025, 11, 10, 9, 0),
            fecha_entrega=None,
        )
        sesion_bd.add(envio)
        sesion_bd.commit()

        resumen = ejecutar_auditoria_lote(sesion_bd, lote)

        assert resumen.omitidos_sin_fecha_entrega == 1
        assert resumen.envios_auditados == 0
        sesion_bd.refresh(envio)
        assert envio.incumplio_sla is None

    def test_omite_envio_sin_regla_sla_que_matchee(self, sesion_bd, empresa_ejemplo):
        lote = LoteAuditoria(
            empresa_id=empresa_ejemplo.id,
            nombre_archivo="envios.csv",
            estado=EstadoLote.PENDIENTE,
            total_filas=1,
        )
        sesion_bd.add(lote)
        sesion_bd.flush()
        envio = Envio(
            lote_auditoria_id=lote.id,
            nombre_transportista_original="Transportista Desconocido",
            numero_guia="G-003",
            fecha_despacho=datetime(2025, 11, 10, 9, 0),
            fecha_entrega=datetime(2025, 11, 10, 14, 0),
        )
        sesion_bd.add(envio)
        sesion_bd.commit()

        resumen = ejecutar_auditoria_lote(sesion_bd, lote)

        assert resumen.omitidos_sin_regla == 1
        assert resumen.envios_auditados == 0
        sesion_bd.refresh(envio)
        # el Transportista se crea igual (queda disponible para cuando se
        # le configure una regla SLA), pero el envío queda sin auditar.
        assert envio.transportista_id is not None
        assert envio.incumplio_sla is None


# ---------------------------------------------------------------------------
# Fecha límite, fecha de corte y días no hábiles (justificación de la auditoría)
# ---------------------------------------------------------------------------


class TestSumarHorasHabiles:
    def test_mismo_dia(self):
        assert sumar_horas_habiles(datetime(2025, 11, 10, 9, 0), 5) == datetime(2025, 11, 10, 14)

    def test_salta_el_fin_de_semana(self):
        # viernes 16:00 + 24 h hábiles: 2 (vie) + 9 (lun) + 9 (mar) + 4 (mié) -> mié 13:00
        limite = sumar_horas_habiles(datetime(2025, 11, 14, 16, 0), 24)
        assert limite == datetime(2025, 11, 19, 13, 0)

    def test_salta_feriados_chilenos(self):
        # miércoles 17-09-2025 15:00 + 9 h: 3 (mié), jue/vie feriados, fin de semana, 6 (lun)
        limite = sumar_horas_habiles(datetime(2025, 9, 17, 15, 0), 9)
        assert limite == datetime(2025, 9, 22, 15, 0)

    def test_despacho_fuera_de_horario_parte_en_la_apertura_siguiente(self):
        limite = sumar_horas_habiles(datetime(2025, 11, 10, 20, 0), 9)  # lunes 20:00
        assert limite == datetime(2025, 11, 11, 18, 0)

    def test_es_la_inversa_de_horas_habiles_entre(self):
        inicio = datetime(2025, 9, 15, 11, 30)
        for horas in (1, 9, 24, 48, 60, 120):
            assert horas_habiles_entre(inicio, sumar_horas_habiles(inicio, horas)) == horas


def test_dias_no_habiles_distingue_fin_de_semana_y_feriados():
    fines_de_semana, feriados = dias_no_habiles(
        datetime(2025, 9, 17, 15, 0), datetime(2025, 9, 22, 11, 0)
    )
    assert fines_de_semana == 2
    assert [f[0] for f in feriados] == [date(2025, 9, 18), date(2025, 9, 19)]
    assert feriados[0][1] == "Fiestas Patrias"


class TestFechaDeCorte:
    """Guías sin entrega: se comparan contra la fecha de corte de la auditoría."""

    def _lote_con_guia_sin_entrega(self, sesion_bd, empresa_id):
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
        lote = LoteAuditoria(
            empresa_id=empresa_id, nombre_archivo="envios.csv", estado=EstadoLote.PENDIENTE
        )
        sesion_bd.add(lote)
        sesion_bd.flush()
        envio = Envio(
            lote_auditoria_id=lote.id,
            nombre_transportista_original="Starken",
            numero_guia="S-001",
            fecha_despacho=datetime(2025, 11, 10, 9, 0),  # vence el 12-11 a las 15:00
            fecha_entrega=None,
        )
        sesion_bd.add(envio)
        sesion_bd.commit()
        return lote, envio

    def test_antes_del_vencimiento_queda_en_transito(self, sesion_bd, empresa_ejemplo):
        lote, envio = self._lote_con_guia_sin_entrega(sesion_bd, empresa_ejemplo.id)

        resumen = ejecutar_auditoria_lote(sesion_bd, lote, fecha_corte=datetime(2025, 11, 11, 12))

        sesion_bd.refresh(envio)
        assert envio.resultado == EN_TRANSITO
        assert envio.fecha_limite.replace(tzinfo=None) == datetime(2025, 11, 12, 15, 0)
        assert envio.horas_habiles_transcurridas == 12  # 9 (lun) + 3 (mar)
        assert resumen.vencidas_sin_entrega == 0

    def test_despues_del_vencimiento_es_alerta_sin_multa(self, sesion_bd, empresa_ejemplo):
        lote, envio = self._lote_con_guia_sin_entrega(sesion_bd, empresa_ejemplo.id)

        resumen = ejecutar_auditoria_lote(sesion_bd, lote, fecha_corte=datetime(2025, 11, 14, 9))

        sesion_bd.refresh(envio)
        assert envio.resultado == VENCIDA_SIN_ENTREGA
        assert envio.horas_habiles_transcurridas == 36  # lun a jue, 9 h cada día
        assert envio.horas_atraso == 12
        assert envio.monto_multa is None
        assert envio.incumplio_sla is None
        assert resumen.vencidas_sin_entrega == 1
        assert resumen.monto_multa_total == 0
        assert lote.fecha_corte.replace(tzinfo=None) == datetime(2025, 11, 14, 9)

    def test_volver_a_auditar_recalcula_desde_cero(self, sesion_bd, empresa_ejemplo):
        lote, envio = self._lote_con_guia_sin_entrega(sesion_bd, empresa_ejemplo.id)
        ejecutar_auditoria_lote(sesion_bd, lote, fecha_corte=datetime(2025, 11, 14, 9))

        envio.fecha_entrega = datetime(2025, 11, 11, 10, 0)  # llegó la información de entrega
        sesion_bd.commit()
        ejecutar_auditoria_lote(sesion_bd, lote, fecha_corte=datetime(2025, 11, 14, 9))

        sesion_bd.refresh(envio)
        assert envio.resultado == CUMPLIDO
        assert envio.horas_atraso == 0
        assert envio.monto_multa == 0
