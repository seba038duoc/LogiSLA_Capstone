"""
Pruebas unitarias del mapeo automático de columnas.

Cubrimos casos reales de headers variados, no solo el caso feliz, porque
el objetivo es que LogiSLA acepte archivos de distintas empresas sin que
cada una tenga que adaptarse a un formato fijo.
"""
from app.column_mapping import mapear_columnas, CAMPOS_OBLIGATORIOS


def test_mapea_headers_estandar_en_espanol():
    headers = ["N° Guía", "Transportista", "Fecha Despacho", "Fecha Entrega", "Destino"]
    resultado = mapear_columnas(headers)

    assert resultado.es_valido
    assert resultado.mapeo["numero_guia"] == "N° Guía"
    assert resultado.mapeo["nombre_transportista"] == "Transportista"
    assert resultado.mapeo["fecha_despacho"] == "Fecha Despacho"
    assert resultado.mapeo["fecha_entrega"] == "Fecha Entrega"
    assert resultado.mapeo["destino"] == "Destino"


def test_mapea_headers_en_ingles_y_snake_case():
    headers = ["tracking_number", "carrier", "ship_date", "delivery_date"]
    resultado = mapear_columnas(headers)

    assert resultado.es_valido
    assert resultado.mapeo["numero_guia"] == "tracking_number"
    assert resultado.mapeo["fecha_despacho"] == "ship_date"


def test_reporta_campos_obligatorios_faltantes():
    # Sin columna de transportista ni de fecha de despacho.
    headers = ["Numero de Guia", "Ciudad Destino"]
    resultado = mapear_columnas(headers)

    assert not resultado.es_valido
    assert "nombre_transportista" in resultado.obligatorios_sin_mapear
    assert "fecha_despacho" in resultado.obligatorios_sin_mapear
    # el campo que sí matcheó no debe reportarse como faltante
    assert "numero_guia" not in resultado.obligatorios_sin_mapear


def test_campos_opcionales_no_son_obligatorios_para_ser_valido():
    # Solo llegan los 3 campos obligatorios, sin destino ni valor declarado.
    headers = ["Guia", "Courier", "Fecha Despacho"]
    resultado = mapear_columnas(headers)

    assert resultado.es_valido
    assert set(CAMPOS_OBLIGATORIOS).issubset(resultado.mapeo.keys())
    assert "destino" not in resultado.mapeo
    assert "valor_declarado" not in resultado.mapeo


def test_es_insensible_a_mayusculas_y_acentos():
    # variante con acentos, mayúsculas y espacios irregulares
    headers = ["  Guía  ", "TRANSPORTISTA", "fechadespacho"]
    resultado = mapear_columnas(headers)

    assert resultado.es_valido


def test_headers_vacios_reporta_todos_los_obligatorios_como_faltantes():
    resultado = mapear_columnas([])
    assert not resultado.es_valido
    assert set(resultado.obligatorios_sin_mapear) == set(CAMPOS_OBLIGATORIOS)
