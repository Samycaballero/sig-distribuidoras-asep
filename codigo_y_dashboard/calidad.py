"""Limpieza y calidad (silver) de la serie mensual de clientes / ventas / facturacion por distribuidora.

POLITICA (documentada tambien en README y en gold/calidad_auditoria.json):
  * Ningun valor se borra sin rastro: cada fila guarda el valor de la fuente (*_fuente), el valor final usado en el
    analisis, la(s) regla(s) que lo marcaron (*_flags) y el metodo de imputacion (*_imputacion).
  * Valores ERRONEOS o NO REPORTADOS se marcan y se IMPUTAN solo para el analisis:
      - clientes    : interpolacion lineal en el tiempo entre los valores validos vecinos;
      - ventas      : interpolacion lineal de kWh/cliente/mes entre vecinos validos x clientes finales;
      - facturacion : interpolacion lineal de US$/kWh entre vecinos validos x ventas finales.
  * Saltos que PERSISTEN (cambio de nivel) no se corrigen: se marcan como posible cambio de definicion/cobertura.

REGLAS (umbrales en UMBRALES):
  R1 faltante              : boletin sin tabla de texto o valor ilegible / fuera de rango fisico.
  R2 arrastre_mes_anterior : valor identico al del mes anterior publicado (la distribuidora no reporto y ASEP repitio la cifra).
  R3 atipico_puntual       : el valor se aleja > umbral de la mediana de los 2 meses validos previos Y de los 2 posteriores
                             (pico aislado; clientes 3 %, ventas 20 %, US$/kWh 30 %).
  R4 kwh_cliente_fuera_banda: kWh/cliente/mes fuera de [0,6 ; 1,6] x la mediana historica de la distribuidora.
  R5 salto_mm              : variacion contra el mes valido anterior > 3 % (clientes) o > 20 % (ventas). Se clasifica en
                             atipico (R3, se imputa), cambio_de_nivel (persiste 3 meses: se conserva y se documenta) o
                             salto_no_persistente (se conserva).
  Nivel boletin: total_no_cuadra (total publicado != suma), etiqueta_mes_tabla distinta, transcripcion_manual,
  unidades/moneda inferidas por magnitud (factor registrado), numero_mal_formado reinterpretado.
"""
import csv
import json
import logging
import statistics
from collections import Counter

import config

log = logging.getLogger("calidad")
UMBRALES = {"clientes": 0.03, "ventas_kwh": 0.20, "usd_kwh": 0.30, "salto_clientes": 0.03, "salto_ventas": 0.20,
            "banda_kwh_cliente": (0.6, 1.6), "meses_persistencia": 3}
VARS = ("clientes", "ventas_kwh", "facturacion_usd")


def periodos(desde=None, hasta=None):
    (a, m), fin = desde or config.BOLETIN_DESDE, hasta or config.BOLETIN_HASTA
    out = []
    while (a, m) <= fin:
        out.append(f"{a}-{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return out


def leer_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _f(x):
    return float(x) if x not in (None, "") else None


def _mediana(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def _vecinos(serie, i, k=2, lado=-1, alcance=4):
    """Hasta k valores validos a un lado de i (dentro de `alcance` meses)."""
    out, j = [], i + lado
    while 0 <= j < len(serie) and abs(j - i) <= alcance and len(out) < k:
        if serie[j] is not None:
            out.append(serie[j])
        j += lado
    return out


def atipico_puntual(serie, i, umbral):
    """True si serie[i] se aleja > umbral de la mediana previa y de la posterior, en la misma direccion."""
    v = serie[i]
    antes, despues = _mediana(_vecinos(serie, i, lado=-1)), _mediana(_vecinos(serie, i, lado=1))
    if v is None or not antes or not despues:
        return False
    da, dd = v / antes - 1, v / despues - 1
    return abs(da) > umbral and abs(dd) > umbral and (da > 0) == (dd > 0)


def interpolar(serie):
    """Interpolacion lineal de los None entre valores validos; en los extremos, el valor valido mas cercano."""
    idx = [i for i, v in enumerate(serie) if v is not None]
    if not idx:
        return list(serie)
    out = list(serie)
    for i, v in enumerate(serie):
        if v is not None:
            continue
        a = max((j for j in idx if j < i), default=None)
        b = min((j for j in idx if j > i), default=None)
        if a is None:
            out[i] = serie[b]
        elif b is None:
            out[i] = serie[a]
        else:
            out[i] = serie[a] + (serie[b] - serie[a]) * (i - a) / (b - a)
    return out


def limpiar_distribuidora(per, filas_por_periodo, info_boletin):
    """Aplica R1-R5 e imputacion a una distribuidora. Devuelve (filas silver, incidencias)."""
    n = len(per)
    fuente = {v: [_f(filas_por_periodo.get(p, {}).get(v)) for p in per] for v in VARS}
    flags = {v: [[] for _ in range(n)] for v in VARS}
    valido = {v: list(fuente[v]) for v in VARS}
    # R1 faltante / R2 arrastre
    for v in VARS:
        ultimo = None
        for i in range(n):
            x = fuente[v][i]
            if x is None:
                motivo = info_boletin.get(per[i], {}).get("estado", "SIN_BOLETIN")
                flags[v][i].append("faltante(fuera_de_rango)" if per[i] in filas_por_periodo else f"faltante({motivo})")
                continue
            if ultimo is not None and x == ultimo:
                flags[v][i].append("arrastre_mes_anterior")
                valido[v][i] = None
            ultimo = x
    # R3 atipico puntual (clientes, ventas) y R4 banda kWh/cliente
    for v, um in (("clientes", UMBRALES["clientes"]), ("ventas_kwh", UMBRALES["ventas_kwh"])):
        marcados = [i for i in range(n) if atipico_puntual(valido[v], i, um)]
        for i in marcados:
            flags[v][i].append("atipico_puntual")
            valido[v][i] = None
    # banda sobre las cifras de la fuente (sin arrastres) para que el error quede marcado aunque R3 ya lo haya detectado
    kc = [fuente["ventas_kwh"][i] / fuente["clientes"][i] if fuente["ventas_kwh"][i] and fuente["clientes"][i]
          and "arrastre_mes_anterior" not in flags["ventas_kwh"][i] else None for i in range(n)]
    med = _mediana(kc)
    lo, hi = UMBRALES["banda_kwh_cliente"]
    for i in range(n):
        if kc[i] is not None and not (lo * med <= kc[i] <= hi * med):
            flags["ventas_kwh"][i].append("kwh_cliente_fuera_banda")
            valido["ventas_kwh"][i] = None
    # facturacion: US$/kWh atipico (sobre ventas validas)
    pu = [valido["facturacion_usd"][i] / valido["ventas_kwh"][i] if valido["facturacion_usd"][i] and valido["ventas_kwh"][i]
          else None for i in range(n)]
    for i in range(n):
        if atipico_puntual(pu, i, UMBRALES["usd_kwh"]):
            flags["facturacion_usd"][i].append("usd_kwh_atipico")
            valido["facturacion_usd"][i] = None
    # R5 saltos m/m (sobre la fuente sin arrastres), clasificados
    for v, um in (("clientes", UMBRALES["salto_clientes"]), ("ventas_kwh", UMBRALES["salto_ventas"])):
        base = [None if "arrastre_mes_anterior" in flags[v][i] else fuente[v][i] for i in range(n)]
        prev = None
        for i in range(n):
            x = base[i]
            if x is None:
                continue
            if prev is not None and abs(x / prev - 1) > um:
                if "atipico_puntual" in flags[v][i] or "kwh_cliente_fuera_banda" in flags[v][i]:
                    tipo = "atipico"
                else:
                    k = UMBRALES["meses_persistencia"]
                    ant, des = _mediana(_vecinos(base, i, k, -1, 6)), _mediana([x] + _vecinos(base, i, k - 1, 1, 6))
                    tipo = "cambio_de_nivel" if ant and des and abs(des / ant - 1) > um else "salto_no_persistente"
                flags[v][i].append(f"salto_mm({x / prev - 1:+.1%};{tipo})")
            if "atipico_puntual" not in flags[v][i] and "kwh_cliente_fuera_banda" not in flags[v][i]:
                prev = x
    # Imputacion
    cli = interpolar(valido["clientes"])
    kc_val = [valido["ventas_kwh"][i] / cli[i] if valido["ventas_kwh"][i] is not None and cli[i] else None for i in range(n)]
    kc_fin = interpolar(kc_val)
    ven = [valido["ventas_kwh"][i] if valido["ventas_kwh"][i] is not None else kc_fin[i] * cli[i] for i in range(n)]
    pu_val = [valido["facturacion_usd"][i] / ven[i] if valido["facturacion_usd"][i] is not None else None for i in range(n)]
    pu_fin = interpolar(pu_val)
    fac = [valido["facturacion_usd"][i] if valido["facturacion_usd"][i] is not None else
           (pu_fin[i] * ven[i] if pu_fin[i] is not None else None) for i in range(n)]
    final = {"clientes": cli, "ventas_kwh": ven, "facturacion_usd": fac}
    metodo = {"clientes": "interpolacion_lineal_clientes", "ventas_kwh": "interpolacion_kwh_por_cliente",
              "facturacion_usd": "interpolacion_usd_por_kwh"}
    filas, inc = [], []
    for i, p in enumerate(per):
        src = filas_por_periodo.get(p, {})
        fila = {"periodo": p, "anio": int(p[:4]), "mes": int(p[5:]), "distribuidora": src.get("distribuidora")}
        for v in VARS:
            imp = valido[v][i] is None
            val = final[v][i]
            fila[v] = (round(val) if v == "clientes" else round(val, 2 if v == "facturacion_usd" else 0)) if val is not None else None
            fila[f"{v}_fuente"] = fuente[v][i]
            fila[f"{v}_flags"] = ";".join(flags[v][i])
            fila[f"{v}_imputacion"] = metodo[v] if imp else ""
            for fl in flags[v][i]:
                inc.append({"periodo": p, "variable": v, "regla": fl.split("(")[0], "detalle": fl,
                            "valor_fuente": fuente[v][i], "valor_final": fila[v],
                            "resolucion": f"imputado ({metodo[v]})" if imp else "conservado (marcado)"})
        fila["flags_extraccion"] = src.get("flags_extraccion", "")
        fila["flags_boletin"] = info_boletin.get(p, {}).get("detalle", "")
        fila["estado_boletin"] = info_boletin.get(p, {}).get("estado", "SIN_BOLETIN")
        fila["archivo"] = src.get("archivo", "")
        fila["pagina"] = src.get("pagina", "")
        fila["imputado"] = int(any(fila[f"{v}_imputacion"] for v in VARS))
        filas.append(fila)
    return filas, inc


def incidencias_extraccion(ext, estados):
    """Incidencias de nivel extraccion/boletin (unidades, numeros mal formados, totales, tablas no legibles)."""
    out = []
    por_bol = {}
    for r in ext:
        por_bol.setdefault(r["periodo"], []).append(r)
    for per, filas in sorted(por_bol.items()):
        for var, campo in (("ventas_kwh", "factor_ventas"), ("facturacion_usd", "factor_facturacion")):
            factores = {r[campo] for r in filas}
            for r in filas:
                if len(factores) > 1 and r[campo] not in ("1", "1.0", 1):
                    out.append({"periodo": per, "distribuidora": r["distribuidora"], "variable": var,
                                "regla": "unidad_mixta_en_boletin",
                                "detalle": f"{r['ventas_texto' if var == 'ventas_kwh' else 'facturacion_texto']} escrito en "
                                           f"{'MWh' if var == 'ventas_kwh' else 'miles de US$'} mientras las otras empresas usan "
                                           f"{'kWh' if var == 'ventas_kwh' else 'US$'} (factor x{float(r[campo]):g})",
                                "valor_fuente": r[campo.replace("factor_", "") + "_texto"],
                                "valor_final": r[var], "resolucion": "corregido por magnitud (factor registrado), conservado"})
        for r in filas:
            if "numero_mal_formado" in r["flags_extraccion"]:
                out.append({"periodo": per, "distribuidora": r["distribuidora"], "variable": "facturacion_usd",
                            "regla": "numero_mal_formado", "detalle": f"texto de la fuente: {r['facturacion_texto']!r}",
                            "valor_fuente": r["facturacion_texto"], "valor_final": r["facturacion_usd"],
                            "resolucion": "reinterpretado (puntos como separador de miles) y validado por banda US$/kWh"})
    for e in estados:
        if e["estado"] in ("OK", "OK_CON_OBSERVACIONES") and not e["detalle"]:
            continue
        res = {"TABLA_EN_IMAGEN": "irrecuperable sin OCR: mes imputado", "SECCION_AUSENTE": "irrecuperable: mes imputado",
               "TRANSCRIPCION_MANUAL": "recuperado (transcripcion verificada: las 3 empresas suman el total)",
               "TOTAL_NO_CUADRA": "total publicado no se usa; valores por empresa evaluados con R2-R4"}.get(
            e["estado"], "informativo (se usa el mes del boletin)")
        regla = "etiqueta_mes_tabla_distinta" if e["estado"].startswith("OK") else e["estado"].lower()
        out.append({"periodo": e["periodo"], "distribuidora": "(boletin)", "variable": "(tabla)", "regla": regla,
                    "detalle": e["detalle"], "valor_fuente": e["archivo"], "valor_final": None, "resolucion": res})
    return out


def detectar_cambios_definicion(extraidos, estados):
    """Transiciones de encabezado (concepto monetario, moneda, unidad declarada) y cambios de nivel."""
    out = []
    for campo in ("concepto_monetario", "moneda", "unidad_declarada"):
        prev = None
        for e in sorted(estados, key=lambda x: x["periodo"]):
            val = e.get(campo)
            if not val:
                continue
            if prev is not None and val != prev[1]:
                out.append({"campo": campo, "desde": prev[1], "hacia": val, "ultimo_periodo_anterior": prev[0],
                            "primer_periodo": e["periodo"]})
            prev = (e["periodo"], val)
    return out


def ejecutar():
    """silver/boletines_extraidos.csv -> silver/mercado_mensual.csv + gold/calidad_auditoria.json (parcial: PDF)."""
    ext = leer_csv(config.silver_dir() / "boletines_extraidos.csv")
    estados = leer_csv(config.silver_dir() / "log_extraccion.csv")
    info = {e["periodo"]: e for e in estados}
    per = periodos()
    filas, incid = [], []
    for d in config.DISTRIBUIDORAS:
        por_p = {r["periodo"]: r for r in ext if r["distribuidora"] == d}
        f, inc = limpiar_distribuidora(per, por_p, info)
        for x in f:
            x["distribuidora"] = d
        for x in inc:
            x["distribuidora"] = d
        filas += f
        incid += inc
    incid += incidencias_extraccion(ext, estados)
    filas.sort(key=lambda r: (r["periodo"], r["distribuidora"]))
    config.silver_dir().mkdir(parents=True, exist_ok=True)
    with open(config.silver_dir() / "mercado_mensual.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    cambios = detectar_cambios_definicion(ext, estados)
    niveles = [i for i in incid if "cambio_de_nivel" in i["detalle"]]
    aud = {
        "politica": __doc__.split("REGLAS")[0].replace("POLITICA (documentada tambien en README y en gold/calidad_auditoria.json):", "").strip(),
        "reglas": __doc__.split("REGLAS (umbrales en UMBRALES):")[1].strip(),
        "umbrales": UMBRALES,
        "boletines": {"total": len(estados), "por_estado": dict(Counter(e["estado"] for e in estados)),
                      "con_observaciones": [e for e in estados if e["estado"] != "OK" or e["detalle"]]},
        "resumen_incidencias": dict(Counter(f"{i['variable']}:{i['regla']}" for i in incid)),
        "filas_imputadas": sum(f["imputado"] for f in filas),
        "filas_imputadas_periodo_base": sum(f["imputado"] for f in filas if config.ANIO_INICIO <= f["anio"] <= config.ANIO_FIN),
        "incidencias": sorted(incid, key=lambda i: (i["periodo"], i["distribuidora"], i["variable"])),
        "cambios_de_encabezado": cambios,
        "cambios_de_nivel": niveles,
        "unidades": {"ventas_factor": dict(Counter(r["factor_ventas"] for r in ext)),
                     "facturacion_factor": dict(Counter(r["factor_facturacion"] for r in ext)),
                     "moneda_declarada": dict(Counter(r["moneda_declarada"] for r in ext)),
                     "nota": "B/. y US$ circulan a la par (1:1); no se convierte. Factor = multiplicador aplicado al numero "
                             "escrito para llevarlo a kWh / US$ (inferido por magnitud, no por el encabezado)."},
    }
    p = config.gold_dir() / "calidad_auditoria.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(aud, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    log.info("Calidad: %d filas silver, %d incidencias, %d filas imputadas (%d en %d-%d)", len(filas), len(incid),
             aud["filas_imputadas"], aud["filas_imputadas_periodo_base"], config.ANIO_INICIO, config.ANIO_FIN)
    return aud
