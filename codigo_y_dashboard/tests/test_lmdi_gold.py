import csv
import json
import math
import random

import pytest

import analisis


def test_lmdi_suma_exacta_aleatorio():
    rnd = random.Random(7)
    for _ in range(500):
        v0, v1 = rnd.uniform(1, 5000), rnd.uniform(1, 5000)
        c0, c1 = rnd.uniform(1e3, 1e6), rnd.uniform(1e3, 1e6)
        r = analisis.lmdi(v0, c0, v1, c1)
        assert r["efecto_clientes"] + r["efecto_consumo_por_cliente"] == pytest.approx(v1 - v0, abs=1e-9 * max(v0, v1))


def test_lmdi_casos_limite():
    r = analisis.lmdi(100, 10, 200, 20)  # solo crecen los clientes
    assert r["efecto_clientes"] == pytest.approx(100) and r["efecto_consumo_por_cliente"] == pytest.approx(0)
    r = analisis.lmdi(100, 10, 100, 10)
    assert r["delta"] == 0 and r["pct_clientes"] is None
    assert analisis.L(3, 3) == 3 and analisis.L(math.e, 1) == pytest.approx(math.e - 1)


def test_gold_descomposicion_suma_el_cambio(corrida):
    with open(corrida["gold"] / "lmdi_descomposicion.csv", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    assert {(r["anio_base"], r["anio_fin"]) for r in filas if r["tipo"] == "acumulada"} == {("2014", "2025"), ("2021", "2025")}
    for r in filas:
        assert float(r["efecto_clientes_gwh"]) + float(r["efecto_consumo_por_cliente_gwh"]) == pytest.approx(float(r["delta_gwh"]), abs=2e-3)
        assert abs(float(r["residuo_gwh"])) < 1e-9


def test_kpi_summary_responde_la_pregunta(corrida):
    s = json.loads((corrida["gold"] / "kpi_summary.json").read_text(encoding="utf-8"))
    r = s["respuesta"]
    assert set(r["mayor_crecimiento_pct"]) == {"2014-2025", "2021-2025"}
    assert all(v in ("EDEMET", "ENSA", "EDECHI") for v in r["mayor_crecimiento_pct"].values())
    assert "efecto" in r["texto"] or "clientes" in r["texto"]
    assert len(s["advertencias"]) >= 4 and s["diagnostico_ia"]["etiqueta"] == "modo offline (plantilla)"
    anios = {k["anio"] for k in s["kpis_anuales"]}
    assert anios == set(range(2014, 2026))
    assert all(k["meses"] == 12 for k in s["kpis_anuales"])
