"""Extraccion de los PDF reales de ASEP (casos conocidos verificados a mano contra el boletin)."""
import logging

import pypdf
import pytest

import extraer_boletines as eb
from conftest import DATA

logging.getLogger("pypdf").setLevel(logging.ERROR)


def _procesar(nombre):
    r = pypdf.PdfReader(str(DATA / "raw" / "boletines_asep" / nombre))
    estado, filas = eb.procesar_boletin(nombre, [p.extract_text() or "" for p in r.pages])
    return estado, {f["distribuidora"]: f for f in filas}


def test_diciembre_2021_edemet():
    estado, f = _procesar("2021_DICIEMBRE.pdf")
    e = f["EDEMET"]
    assert (e["clientes"], e["ventas_kwh"], e["facturacion_usd"]) == (547347, 280255232, 62915771)
    assert estado["estado"] == "OK" and e["factor_ventas"] == 1


def test_diciembre_2025_edemet():
    estado, f = _procesar("2025_DICIEMBRE.pdf")
    e = f["EDEMET"]
    assert (e["clientes"], e["ventas_kwh"]) == (596848, 313319941)
    assert e["facturacion_usd"] == pytest.approx(67001042.54)
    assert estado["moneda"] == "B/."  # B/. a la par con US$


def test_2016_10_ya_no_toma_la_tabla_de_costos():
    estado, f = _procesar("2016_OCTUBRE.pdf")
    assert f["EDEMET"]["clientes"] == 453062 and f["ENSA"]["clientes"] == 435005
    assert f["EDEMET"]["ventas_kwh"] == 349561000 and f["EDEMET"]["factor_ventas"] == 1000  # escrito en MWh
    assert estado["estado"] != "TOTAL_NO_CUADRA"


def test_2016_01_tabla_sin_titulo_se_encuentra():
    _, f = _procesar("2016_ENERO.pdf")
    assert f["EDEMET"]["clientes"] == 442289 and f["EDECHI"]["ventas_kwh"] == 69477539


def test_2021_10_unidades_mixtas_y_error_edemet_quedan_registrados():
    _, f = _procesar("2021_OCTUBRE.pdf")
    assert f["ENSA"]["ventas_texto"] == "249,949" and f["ENSA"]["factor_ventas"] == 1000
    assert f["ENSA"]["facturacion_usd"] == 39819000 and f["ENSA"]["factor_facturacion"] == 1000
    assert f["EDEMET"]["ventas_kwh"] == 828014691  # error de la fuente: se extrae tal cual; calidad lo marca


def test_2018_05_numero_mal_formado():
    estado, f = _procesar("2018_MAYO.pdf")
    assert "numero_mal_formado" in f["ENSA"]["flags_extraccion"]
    assert f["ENSA"]["facturacion_usd"] == 54128000.0
    assert estado["estado"] == "TOTAL_NO_CUADRA"


def test_meses_sin_tabla_se_clasifican():
    assert _procesar("2015_MAYO.pdf")[0]["estado"] == "TABLA_EN_IMAGEN"
    assert _procesar("2014_MARZO.pdf")[0]["estado"] == "SECCION_AUSENTE"


def test_2013_04_transcripcion_manual_cuadra_con_total():
    estado, f = _procesar("2013_ABRIL.pdf")
    assert estado["estado"] == "TRANSCRIPCION_MANUAL"
    assert f["EDEMET"]["clientes"] == 396850 and f["ENSA"]["ventas_kwh"] == 251737000


@pytest.mark.parametrize("tok,esperado,mal", [
    ("1,234,567", 1234567, False), ("1,234,567.89", 1234567.89, False), ("408734", 408734, False),
    ("298,826.74", 298826.74, False), ("54128.000.00", 54128000.0, True), ("57,135.000.00", 57135000.0, True)])
def test_parse_num(tok, esperado, mal):
    assert eb.parse_num(tok) == (pytest.approx(esperado), mal)


def test_factor_de_unidad_por_magnitud():
    assert eb._factor(300_000_000, 500_000, eb.BANDA_KWH_CLIENTE) == 1        # kWh
    assert eb._factor(300_000, 500_000, eb.BANDA_KWH_CLIENTE) == 1000         # MWh
    assert eb._factor(62_679, 326_271_000, eb.BANDA_USD_KWH) == 1000          # miles de US$
    assert eb._factor(5, 500_000, eb.BANDA_KWH_CLIENTE) is None              # imposible: se marca
