"""Presentación: datos del dashboard completos y coherentes con gold, textos visibles con tildes, figuras a 300 dpi."""
import json
import re

import generar_dashboard_y_graficos as gen

SIN_TILDE = re.compile(r"\b(electric[oa]s?|Panama|Distribucion|Descomposicion|anios?|Diagnostico|Correlacion|facturacion|"
                       r"boletin|seccion|hipotesis|maxima|caida|atipico|interpolacion|transcripcion|paginas|metrica|"
                       r"mas clientes|crece mas|Analisis|Metodo)\b")


def _datos(html):
    return json.loads(html.split("const D=", 1)[1].split(";\nconst TEMA", 1)[0])


def _textos(x):
    if isinstance(x, dict):
        return [t for v in x.values() for t in _textos(v)]
    if isinstance(x, list):
        return [t for v in x for t in _textos(v)]
    return [x] if isinstance(x, str) else []


def test_dashboard_tiene_las_tres_distribuidoras_y_cifras_de_gold(corrida):
    html = (corrida["out"] / "dashboard_interactivo.html").read_text(encoding="utf-8")
    D = _datos(html)
    for clave in ("anual", "mensual", "reclamos", "est"):
        assert {r["d"] for r in D[clave]} == {"EDEMET", "ENSA", "EDECHI"}, clave
    s = json.loads((corrida["gold"] / "kpi_summary.json").read_text(encoding="utf-8"))
    gold = {(k["distribuidora"], k["anio"]): k for k in s["kpis_anuales"]}
    for r in D["anual"]:  # entradas del LMDI en JS = KPIs anuales de gold (mismo cálculo que fact_descomposicion)
        assert (r["v"], r["c"]) == (gold[(r["d"], r["a"])]["ventas_gwh"], gold[(r["d"], r["a"])]["clientes_promedio"])
    assert D["imputados"]["filas"] == s["calidad"]["filas_imputadas_periodo_base"]
    assert len(D["calidad"]["incidencias"]) == len(json.loads(
        (corrida["gold"] / "calidad_auditoria.json").read_text(encoding="utf-8"))["incidencias"])
    assert D["diagnostico"]["etiqueta"] in html


def test_textos_visibles_con_tildes(corrida):
    html = (corrida["out"] / "dashboard_interactivo.html").read_text(encoding="utf-8")
    visible = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html, flags=re.S)
    textos = [visible] + _textos(_datos(html))
    malas = sorted({m.group(0) for t in textos for m in SIN_TILDE.finditer(t)})
    assert not malas, malas
    assert gen.es("salto_mm(+3.0%;atipico)") == "salto mensual (+3.0 %; atípico)"
    assert gen.es("12 paginas; la seccion de clientes no aparece fuera del indice") == \
        "12 páginas; la sección de clientes no aparece fuera del índice"


def test_seis_figuras_a_300_dpi(corrida):
    from PIL import Image
    figs = sorted((corrida["out"] / "graficos").glob("*.png"))
    assert [f.name[:4] for f in figs] == ["fig1", "fig2", "fig3", "fig4", "fig5", "fig6"]
    for f in figs:
        assert round(Image.open(f).info["dpi"][0]) == 300, f.name
