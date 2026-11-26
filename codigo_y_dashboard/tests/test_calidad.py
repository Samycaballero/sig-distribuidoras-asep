"""Reglas de calidad e imputacion: series sinteticas pequenas + casos reales de la corrida completa."""
import csv
import json

import pytest

import calidad


def _serie(clientes, ventas, facturas=None):
    per = [f"2020-{m:02d}" for m in range(1, len(clientes) + 1)]
    filas = {p: {"distribuidora": "X", "clientes": c, "ventas_kwh": v,
                 "facturacion_usd": (facturas[i] if facturas else v * 0.2) if v else None}
             for i, (p, c, v) in enumerate(zip(per, clientes, ventas)) if c is not None}
    return calidad.limpiar_distribuidora(per, filas, {})


def test_arrastre_se_marca_e_imputa_conservando_el_original():
    filas, inc = _serie([100, 102, 102, 106, 108], [50000, 51000, 51000, 53000, 54000])
    f = filas[2]
    assert "arrastre_mes_anterior" in f["clientes_flags"] and "arrastre_mes_anterior" in f["ventas_kwh_flags"]
    assert f["clientes_fuente"] == 102 and f["clientes"] == 104  # interpolacion lineal 102 -> 106
    assert f["ventas_kwh"] == pytest.approx(52000, rel=1e-3)  # kWh/cliente interpolado (500) x 104
    assert any(i["regla"] == "arrastre_mes_anterior" and i["resolucion"].startswith("imputado") for i in inc)


def test_pico_aislado_de_ventas_se_imputa():
    filas, _ = _serie([100] * 3 + [101] * 3, [50000, 51000, 52000, 150000, 51000, 50500])
    f = filas[3]
    assert "atipico_puntual" in f["ventas_kwh_flags"] and f["ventas_kwh_imputacion"]
    assert f["ventas_kwh_fuente"] == 150000 and 49000 < f["ventas_kwh"] < 53000


def test_cambio_de_nivel_se_conserva_y_marca():
    c = [1000, 1002, 1004, 1110, 1112, 1115, 1117]
    filas, _ = _serie(c, [x * 450 + i for i, x in enumerate(c)])
    f = filas[3]
    assert "cambio_de_nivel" in f["clientes_flags"] and f["clientes"] == 1110 and not f["clientes_imputacion"]


def test_faltante_se_imputa():
    filas, _ = _serie([100, None, 104], [50000, None, 52000])
    assert filas[1]["clientes"] == 102 and filas[1]["clientes_flags"].startswith("faltante")


def test_interpolar_extremos():
    assert calidad.interpolar([None, 2, None, 6, None]) == [2, 2, 4, 6, 6]


# ---------------- casos reales (corrida completa del DAG sobre los 162 boletines)
def _mensual(corrida):
    with open(corrida["silver"] / "mercado_mensual.csv", encoding="utf-8") as f:
        return {(r["periodo"], r["distribuidora"]): r for r in csv.DictReader(f)}


def test_2021_10_edemet_marcado_e_imputado(corrida):
    r = _mensual(corrida)[("2021-10", "EDEMET")]
    assert "atipico_puntual" in r["ventas_kwh_flags"] and "kwh_cliente_fuera_banda" in r["ventas_kwh_flags"]
    assert float(r["ventas_kwh_fuente"]) == 828014691 and 250e6 < float(r["ventas_kwh"]) < 300e6


def test_2021_10_ensa_unidad_mixta_registrada(corrida):
    aud = json.loads((corrida["gold"] / "calidad_auditoria.json").read_text(encoding="utf-8"))
    inc = [i for i in aud["incidencias"] if i["periodo"] == "2021-10" and i["distribuidora"] == "ENSA"]
    assert {i["regla"] for i in inc} == {"unidad_mixta_en_boletin"} and len(inc) == 2


def test_2018_05_marcado(corrida):
    aud = json.loads((corrida["gold"] / "calidad_auditoria.json").read_text(encoding="utf-8"))
    reglas = {(i["distribuidora"], i["regla"]) for i in aud["incidencias"] if i["periodo"] == "2018-05"}
    assert ("ENSA", "numero_mal_formado") in reglas and ("(boletin)", "total_no_cuadra") in reglas
    assert ("EDEMET", "arrastre_mes_anterior") in reglas  # EDEMET repite abril


def test_meses_sin_tabla_imputados_y_serie_completa(corrida):
    m = _mensual(corrida)
    for per in ("2014-03", "2015-05", "2015-06"):
        for d in ("EDEMET", "ENSA", "EDECHI"):
            assert m[(per, d)]["imputado"] == "1" and m[(per, d)]["clientes_flags"].startswith("faltante")
    assert all(r["ventas_kwh"] and r["clientes"] for r in m.values())  # sin huecos tras imputar
    assert len(m) == 162 * 3


def test_edechi_2015_10_cambio_de_nivel_documentado(corrida):
    r = _mensual(corrida)[("2015-10", "EDECHI")]
    assert "cambio_de_nivel" in r["clientes_flags"] and r["clientes"] == "141475"
