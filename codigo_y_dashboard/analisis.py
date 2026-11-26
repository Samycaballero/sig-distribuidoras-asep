"""Capa gold: KPIs, descomposicion LMDI, estacionalidad, reclamos y respuesta a la pregunta gerencial.

Pregunta: En que distribuidora electrica de Panama esta creciendo mas el consumo, y cuanto de ese crecimiento se
explica por mas clientes o por mayor consumo por cliente?

LMDI aditivo (Ang, 2005) con V = C x I  (V ventas anuales, C clientes promedio del anio, I = V/C):
    dV = L(V1,V0) ln(C1/C0)  +  L(V1,V0) ln(I1/I0),   L(a,b) = (a-b)/(ln a - ln b)
La suma de los dos efectos es exactamente dV (identidad ln(V1/V0) = ln(C1/C0) + ln(I1/I0)); se verifica en tests.
"""
import csv
import json
import logging
import math
import statistics
from datetime import date

import config

log = logging.getLogger("analisis")


def L(a, b):
    """Media logaritmica."""
    if a <= 0 or b <= 0:
        raise ValueError("LMDI requiere valores positivos")
    return a if math.isclose(a, b, rel_tol=1e-15) else (a - b) / (math.log(a) - math.log(b))


def lmdi(v0, c0, v1, c1):
    """Descomposicion aditiva del cambio de ventas en efecto clientes y efecto consumo por cliente (mismas unidades que v)."""
    w = L(v1, v0)
    ec = w * math.log(c1 / c0)
    ei = w * math.log((v1 / c1) / (v0 / c0))
    d = v1 - v0
    return {"delta": d, "efecto_clientes": ec, "efecto_consumo_por_cliente": ei,
            "pct_clientes": 100 * ec / d if d else None, "pct_consumo_por_cliente": 100 * ei / d if d else None,
            "residuo": d - ec - ei}


def leer_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _csv(path, filas):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)


def pearson(x, y):
    n = len(x)
    if n < 3:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy) if sx and sy else None


# ------------------------------------------------------------------ KPIs anuales
def kpis_anuales(mensual, anios):
    out = []
    claves = list(config.DISTRIBUIDORAS) + ["TOTAL_3"]
    agg = {}
    for r in mensual:
        a = int(r["anio"])
        if a not in anios:
            continue
        for k in (r["distribuidora"], "TOTAL_3"):
            g = agg.setdefault((k, a), {"ventas": 0.0, "clientes": [], "fact": 0.0, "meses": 0, "imputados": 0,
                                        "imp_ventas": 0})
            g["ventas"] += float(r["ventas_kwh"])
            g["fact"] += float(r["facturacion_usd"] or 0)
            g["imputados"] += int(r["imputado"])
            g["imp_ventas"] += int(bool(r["ventas_kwh_imputacion"]))
            if k != "TOTAL_3":
                g["clientes"].append(float(r["clientes"]))
                g["meses"] += 1
    # clientes promedio del total = suma de promedios
    for a in anios:
        if ("TOTAL_3", a) in agg:
            agg[("TOTAL_3", a)]["clientes"] = [sum(statistics.mean(agg[(d, a)]["clientes"]) for d in config.DISTRIBUIDORAS)]
            agg[("TOTAL_3", a)]["meses"] = min(agg[(d, a)]["meses"] for d in config.DISTRIBUIDORAS)
    for k in claves:
        prev = base = None
        for a in anios:
            g = agg.get((k, a))
            if not g:
                continue
            cp = statistics.mean(g["clientes"])
            fila = {"distribuidora": k, "anio": a, "meses": g["meses"], "ventas_gwh": round(g["ventas"] / 1e6, 3),
                    "clientes_promedio": round(cp), "kwh_cliente_mes": round(g["ventas"] / cp / 12, 1),
                    "facturacion_musd": round(g["fact"] / 1e6, 3),
                    "ingreso_medio_usd_kwh": round(g["fact"] / g["ventas"], 4) if g["ventas"] else None,
                    "participacion_ventas_pct": round(100 * g["ventas"] / agg[("TOTAL_3", a)]["ventas"], 2),
                    "crec_ventas_pct": round(100 * (g["ventas"] / prev["v"] - 1), 2) if prev else None,
                    "crec_clientes_pct": round(100 * (cp / prev["c"] - 1), 2) if prev else None,
                    "crec_acum_ventas_pct": round(100 * (g["ventas"] / base["v"] - 1), 2) if base else 0.0,
                    "crec_acum_clientes_pct": round(100 * (cp / base["c"] - 1), 2) if base else 0.0,
                    "meses_con_imputacion": g["imputados"] if k != "TOTAL_3" else g["imputados"],
                    "meses_ventas_imputadas": g["imp_ventas"]}
            out.append(fila)
            prev = {"v": g["ventas"], "c": cp}
            base = base or prev
    return out


def descomposicion(kpis, pares):
    """LMDI por distribuidora: anual (anio vs anterior) y acumulada para cada par (a0, a1)."""
    idx = {(k["distribuidora"], k["anio"]): k for k in kpis}
    out = []
    for d in list(config.DISTRIBUIDORAS) + ["TOTAL_3"]:
        anios = sorted(a for (x, a) in idx if x == d)
        tramos = [("anual", a0, a1) for a0, a1 in zip(anios, anios[1:])] + [("acumulada", a0, a1) for a0, a1 in pares]
        for tipo, a0, a1 in tramos:
            k0, k1 = idx.get((d, a0)), idx.get((d, a1))
            if not k0 or not k1:
                continue
            r = lmdi(k0["ventas_gwh"], k0["clientes_promedio"], k1["ventas_gwh"], k1["clientes_promedio"])
            out.append({"distribuidora": d, "tipo": tipo, "anio_base": a0, "anio_fin": a1,
                        "ventas_base_gwh": k0["ventas_gwh"], "ventas_fin_gwh": k1["ventas_gwh"],
                        "delta_gwh": round(r["delta"], 3), "crec_ventas_pct": round(100 * (k1["ventas_gwh"] / k0["ventas_gwh"] - 1), 2),
                        "efecto_clientes_gwh": round(r["efecto_clientes"], 3),
                        "efecto_consumo_por_cliente_gwh": round(r["efecto_consumo_por_cliente"], 3),
                        "pct_clientes": round(r["pct_clientes"], 1) if r["pct_clientes"] is not None else None,
                        "pct_consumo_por_cliente": round(r["pct_consumo_por_cliente"], 1) if r["pct_consumo_por_cliente"] is not None else None,
                        "crec_clientes_pct": round(100 * (k1["clientes_promedio"] / k0["clientes_promedio"] - 1), 2),
                        "crec_kwh_cliente_pct": round(100 * (k1["kwh_cliente_mes"] / k0["kwh_cliente_mes"] - 1), 2),
                        "residuo_gwh": r["residuo"]})
    return out


def estacionalidad(mensual, anios):
    """Indice mensual de ventas (promedio de ventas_mes / promedio mensual del anio) por distribuidora."""
    out = []
    for d in config.DISTRIBUIDORAS:
        por_anio = {}
        for r in mensual:
            if r["distribuidora"] == d and int(r["anio"]) in anios:
                por_anio.setdefault(int(r["anio"]), {})[int(r["mes"])] = (float(r["ventas_kwh"]), float(r["clientes"]))
        for m in range(1, 13):
            idx = [v[m][0] / statistics.mean(x[0] for x in v.values()) for v in por_anio.values() if len(v) == 12]
            kc = [v[m][0] / v[m][1] for v in por_anio.values() if m in v]
            out.append({"distribuidora": d, "mes": m, "indice_ventas": round(statistics.mean(idx), 4),
                        "kwh_cliente_mes_promedio": round(statistics.mean(kc), 1), "anios": len(idx)})
    return out


def reclamos_kpis(mensual, reclamos):
    """Reclamos por cada 10,000 clientes (mensual y anual) y correlacion con ventas (2021+)."""
    cli = {(r["periodo"], r["distribuidora"]): r for r in mensual}
    men = []
    for r in reclamos:
        m = cli.get((r["periodo"], r["distribuidora"]))
        if not m or r["reclamos"] in (None, ""):
            continue
        rec = int(r["reclamos"])
        men.append({"periodo": r["periodo"], "anio": int(r["anio"]), "mes": int(r["mes"]), "distribuidora": r["distribuidora"],
                    "reclamos": rec, "clientes": int(m["clientes"]), "ventas_kwh": float(m["ventas_kwh"]),
                    "reclamos_por_10k_clientes": round(rec / int(m["clientes"]) * 1e4, 3)})
    anual, corr = [], []
    for d in config.DISTRIBUIDORAS:
        filas = [x for x in men if x["distribuidora"] == d]
        for a in sorted({x["anio"] for x in filas}):
            fa = [x for x in filas if x["anio"] == a]
            cp = statistics.mean(x["clientes"] for x in fa)
            tot = sum(x["reclamos"] for x in fa)
            anual.append({"distribuidora": d, "anio": a, "meses": len(fa), "reclamos": tot,
                          "reclamos_por_10k_clientes_anio": round(tot / cp * 1e4, 2),
                          "reclamos_por_10k_clientes_mes_prom": round(tot / cp * 1e4 / len(fa), 3)})
        fc = [x for x in filas if x["anio"] <= config.ANIO_FIN]
        corr.append({"distribuidora": d, "n_meses": len(fc), "desde": min(x["periodo"] for x in fc),
                     "hasta": max(x["periodo"] for x in fc),
                     "r_reclamos_vs_ventas": round(pearson([x["reclamos"] for x in fc], [x["ventas_kwh"] for x in fc]), 3),
                     "r_tasa10k_vs_kwh_cliente": round(pearson([x["reclamos_por_10k_clientes"] for x in fc],
                                                               [x["ventas_kwh"] / x["clientes"] for x in fc]), 3)})
    return men, anual, corr


def vista_reciente(mensual):
    """2026 parcial: meses publicados de 2026 contra los mismos meses de 2025."""
    m26 = sorted({int(r["mes"]) for r in mensual if r["anio"] in ("2026", 2026)})
    out = []
    for d in config.DISTRIBUIDORAS:
        f = {(int(r["anio"]), int(r["mes"])): r for r in mensual if r["distribuidora"] == d}
        v25 = sum(float(f[(2025, m)]["ventas_kwh"]) for m in m26)
        v26 = sum(float(f[(2026, m)]["ventas_kwh"]) for m in m26)
        c25 = statistics.mean(float(f[(2025, m)]["clientes"]) for m in m26)
        c26 = statistics.mean(float(f[(2026, m)]["clientes"]) for m in m26)
        r = lmdi(v25, c25, v26, c26)
        out.append({"distribuidora": d, "meses": f"ene-{config.MESES[m26[-1] - 1][:3].lower()}" if m26 else "",
                    "ventas_2025_gwh": round(v25 / 1e6, 1), "ventas_2026_gwh": round(v26 / 1e6, 1),
                    "crec_ventas_pct": round(100 * (v26 / v25 - 1), 2), "crec_clientes_pct": round(100 * (c26 / c25 - 1), 2),
                    "pct_clientes": round(r["pct_clientes"], 1), "pct_consumo_por_cliente": round(r["pct_consumo_por_cliente"], 1)})
    return out


def demanda_maxima_anual(dem, anios):
    out = []
    for a in anios:
        v = [float(r["demanda_max_mw"]) for r in dem if r["periodo"].startswith(str(a))]
        if v:
            out.append({"anio": a, "meses": len(v), "demanda_max_mw": max(v)})
    return out


def _texto_respuesta(acum):
    def fila(d, a0):
        return next(x for x in acum if x["distribuidora"] == d and x["anio_base"] == a0)
    partes = []
    for a0 in sorted({x["anio_base"] for x in acum}):
        rk = sorted((fila(d, a0) for d in config.DISTRIBUIDORAS), key=lambda x: -x["crec_ventas_pct"])
        g = rk[0]
        ab = max((fila(d, a0) for d in config.DISTRIBUIDORAS), key=lambda x: x["delta_gwh"])
        def efectos(x):
            if (x["efecto_clientes_gwh"] >= 0) == (x["efecto_consumo_por_cliente_gwh"] >= 0):
                return (f"{x['efecto_clientes_gwh']:+.0f} GWh ({x['pct_clientes']:.0f} %) por más clientes y "
                        f"{x['efecto_consumo_por_cliente_gwh']:+.0f} GWh ({x['pct_consumo_por_cliente']:.0f} %) por consumo por cliente")
            # efectos de signo opuesto: los % del cambio neto pierden sentido (>100 %), se informa solo en GWh
            return (f"efectos opuestos: clientes {x['efecto_clientes_gwh']:+.0f} GWh y consumo por cliente "
                    f"{x['efecto_consumo_por_cliente_gwh']:+.0f} GWh")
        partes.append(
            f"{a0}→{g['anio_fin']}: crece más {g['distribuidora']} ({g['crec_ventas_pct']:+.1f} % en ventas, "
            f"{g['delta_gwh']:+.0f} GWh): {efectos(g)}. Mayor aumento absoluto: {ab['distribuidora']} ({ab['delta_gwh']:+.0f} GWh). "
            "Resto: " + "; ".join(f"{x['distribuidora']} {x['crec_ventas_pct']:+.1f} % ({x['delta_gwh']:+.0f} GWh; {efectos(x)})"
                                  for x in rk[1:]) + ".")
    return " ".join(partes)


def hallazgos(kpis, rec_a, dem_a, aud):
    """Hallazgos cuantitativos (texto) derivados de los datos; alimentan el diagnostico de IA y el README."""
    a0, a1 = config.ANIO_INICIO, config.ANIO_FIN
    k = {(x["distribuidora"], x["anio"]): x for x in kpis}
    out = []
    for d in config.DISTRIBUIDORAS:
        out.append(f"{d}: kWh/cliente/mes {k[(d, a0)]['kwh_cliente_mes']} ({a0}) → {k[(d, 2021)]['kwh_cliente_mes']} (2021) → "
                   f"{k[(d, a1)]['kwh_cliente_mes']} ({a1}); clientes {k[(d, a0)]['clientes_promedio']:,} → {k[(d, a1)]['clientes_promedio']:,}.")
    t = {a: k[("TOTAL_3", a)] for a in range(a0, a1 + 1) if ("TOTAL_3", a) in k}
    caida = [a for a in t if t[a]["crec_ventas_pct"] is not None and t[a]["crec_ventas_pct"] < 0]
    out.append(f"Ventas de las 3 distribuidoras: {t[a0]['ventas_gwh']:,.0f} GWh ({a0}) → {t[a1]['ventas_gwh']:,.0f} GWh ({a1}); "
               f"años con caída: {', '.join(map(str, caida))} (2020: pandemia).")
    dm = {x["anio"]: x["demanda_max_mw"] for x in dem_a}
    if a0 in dm and a1 in dm:
        out.append(f"Demanda máxima del sistema {dm[a0]:,.0f} MW ({a0}) → {dm[a1]:,.0f} MW ({a1}) ({100 * (dm[a1] / dm[a0] - 1):+.1f} %), "
                   f"frente a {100 * (t[a1]['ventas_gwh'] / t[a0]['ventas_gwh'] - 1):+.1f} % en ventas de distribuidoras: parte del "
                   "consumo nacional crece fuera de las ventas reguladas (hipótesis no verificada: grandes clientes que compran en el "
                   "mercado mayorista, autoconsumo solar).")
    ra = {(x["distribuidora"], x["anio"]): x for x in rec_a}
    for d in config.DISTRIBUIDORAS:
        if (d, 2021) in ra and (d, a1) in ra:
            out.append(f"Reclamos {d}: {ra[(d, 2021)]['reclamos_por_10k_clientes_mes_prom']:.2f} → {ra[(d, a1)]['reclamos_por_10k_clientes_mes_prom']:.2f} "
                       f"por 10 mil clientes al mes (2021 → {a1}, {ra[(d, a1)]['meses']} meses).")
    nc = aud.get("ckan", {}).get("cruce_suma_distribuidoras_vs_sector_electricidad", {}).get("meses_que_no_cuadran", [])
    if nc:
        out.append(f"Los dos CSV de reclamos de ASEP no coinciden en {len(nc)} meses ({', '.join(x['periodo'] for x in nc)}).")
    return out


def construir_gold():
    """silver -> gold (CSV + kpi_summary.json). Devuelve el resumen."""
    mensual = leer_csv(config.silver_dir() / "mercado_mensual.csv")
    anios = list(range(config.ANIO_INICIO, config.ANIO_FIN + 1))
    kpis = kpis_anuales(mensual, anios)
    pares = [(config.ANIO_INICIO, config.ANIO_FIN), (2021, config.ANIO_FIN)]
    desc = descomposicion(kpis, pares)
    est = estacionalidad(mensual, anios)
    rec = leer_csv(config.silver_dir() / "reclamos_distribuidora_mensual.csv")
    rec_m, rec_a, rec_c = reclamos_kpis(mensual, [r for r in rec if r["distribuidora"] in config.DISTRIBUIDORAS])
    dem = leer_csv(config.silver_dir() / "demanda_maxima_mensual.csv")
    dem_a = demanda_maxima_anual(dem, anios)
    reciente = vista_reciente(mensual)
    g = config.gold_dir()
    _csv(g / "kpi_anual.csv", kpis)
    _csv(g / "lmdi_descomposicion.csv", desc)
    _csv(g / "estacionalidad_mensual.csv", est)
    _csv(g / "reclamos_mensual.csv", rec_m)
    _csv(g / "reclamos_anual.csv", rec_a)
    aud = json.loads((g / "calidad_auditoria.json").read_text(encoding="utf-8"))
    acum = [x for x in desc if x["tipo"] == "acumulada" and x["distribuidora"] != "TOTAL_3"]
    kc = {(k["distribuidora"], k["anio"]): k["kwh_cliente_mes"] for k in kpis}
    cambios_nivel = sorted({f"{i['distribuidora']} {i['periodo']} {i['variable']}" for i in aud.get("cambios_de_nivel", [])})
    resumen = {
        "pregunta": "¿En qué distribuidora eléctrica de Panamá está creciendo más el consumo, y cuánto de ese crecimiento "
                    "se explica por más clientes o por mayor consumo por cliente?",
        "generado": date.today().isoformat(),
        "periodo_base": f"{config.ANIO_INICIO}-01 a {config.ANIO_FIN}-12 (años completos); 2026 parcial solo en vista_reciente",
        "metodo": "Ventas anuales = suma de 12 meses (kWh facturados a clientes de la distribuidora según boletín ASEP); "
                  "clientes = promedio de los 12 meses; LMDI aditivo V = C × I.",
        "respuesta": {
            "texto": _texto_respuesta(acum),
            "mayor_crecimiento_pct": {f"{a0}-{a1}": max((x for x in acum if x["anio_base"] == a0), key=lambda x: x["crec_ventas_pct"])["distribuidora"]
                                      for a0, a1 in pares},
            "mayor_crecimiento_absoluto_gwh": {f"{a0}-{a1}": max((x for x in acum if x["anio_base"] == a0), key=lambda x: x["delta_gwh"])["distribuidora"]
                                               for a0, a1 in pares},
            "descomposicion_acumulada": [{k: v for k, v in x.items() if k != "residuo_gwh"} for x in desc if x["tipo"] == "acumulada"],
            "kwh_cliente_mes": {d: {str(a): kc.get((d, a)) for a in (config.ANIO_INICIO, 2021, config.ANIO_FIN)} for d in config.DISTRIBUIDORAS},
        },
        "kpis_anuales": kpis,
        "descomposicion_anual": [x for x in desc if x["tipo"] == "anual"],
        "estacionalidad": est,
        "reclamos": {"anual": rec_a, "correlaciones": rec_c,
                     "nota": "Reclamos de electricidad admitidos por ASEP (CSV CKAN). 2025 tiene 11 meses (sin diciembre) y "
                             "2026 solo enero. Correlación no implica causalidad."},
        "demanda_maxima_sistema": dem_a,
        "hallazgos": hallazgos(kpis, rec_a, dem_a, aud),
        "vista_reciente_2026": reciente,
        "calidad": {"filas_imputadas_periodo_base": aud["filas_imputadas_periodo_base"],
                    "boletines_por_estado": aud["boletines"]["por_estado"], "resumen_incidencias": aud["resumen_incidencias"],
                    "cambios_de_nivel": cambios_nivel},
        "advertencias": [
            "Los boletines ASEP reportan 'clientes' y 'ventas' sin definir cobertura (regulados vs. totales, grandes clientes, "
            "autoconsumo); un cambio de cobertura no documentado se vería como cambio de nivel.",
            "Cambios de nivel detectados (conservados, posible cambio de definición/cobertura): " + (", ".join(cambios_nivel) or "ninguno") + ".",
            f"{aud['filas_imputadas_periodo_base']} filas distribuidora-mes del periodo base tienen al menos una variable imputada "
            "(arrastres de la fuente, meses sin tabla, errores puntuales); ver calidad_auditoria.json.",
            "Ingreso medio US$/kWh = facturación/ventas: el concepto cambia de 'ingresos' (hasta 2020-04) a 'facturado/facturación' "
            "(desde 2020-05) e incluye subsidios/cargos no separados; no es una tarifa.",
            "El consumo por cliente es un promedio: puede bajar por entrada de clientes pequeños, no necesariamente por eficiencia.",
            "Correlación no implica causalidad (reclamos vs. ventas).",
        ],
    }
    (g / "kpi_summary.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("Gold: %s", resumen["respuesta"]["mayor_crecimiento_pct"])
    return resumen
