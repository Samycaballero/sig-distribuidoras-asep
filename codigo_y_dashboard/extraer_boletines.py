"""Extraccion (tipo de dato 1: PDF) de los boletines mensuales de ASEP "Estadistica del Mercado Electrico Panameno".

Por boletin: clientes, ventas (kWh) y facturacion/ingresos (US$ o B/.) de EDEMET, ENSA y EDECHI + total publicado,
y la serie de demanda maxima mensual del sistema (tabla "DEMANDA MAXIMA MENSUAL Y ANUAL").

Mejoras sobre scripts/extraer_clientes_ventas.py (version anterior):
- La tabla se busca como BLOQUE completo (EDEMET n n n / ENSA n n n / EDECHI n n n / TOTAL n n n) en cualquier pagina:
  ya no se confunde con la tabla de costos (2016-10/11) ni depende del titulo (2016-01).
- Numeros mal formados ("54128.000.00") se reinterpretan y se marcan; nunca se descartan en silencio.
- Unidad inferida por magnitud y factor registrado por valor (ventas: kWh/cliente/mes en 100-3000;
  facturacion: US$/kWh en 0,05-0,50, p. ej. 2021-10 ENSA viene en MWh y miles de US$).
- Boletines sin tabla de texto se clasifican: tabla en imagen (seccion presente sin numeros) o seccion ausente.
- 2013-04: el texto de la pagina sale fragmentado; se usa una transcripcion manual verificada contra el total.
El texto extraido se guarda en cache (data/interim/textos_boletines.json, clave sha256) y alimenta MongoDB.

Uso: python extraer_boletines.py
"""
import csv
import hashlib
import json
import logging
import re
import urllib.request
from datetime import date, datetime
from pathlib import Path

import config

log = logging.getLogger("boletines")
D = config.DISTRIBUIDORAS
N = r"(-?\d[\d,\.]*)"
BLOQUE = re.compile(rf"EDEMET\s+{N}\s+{N}\s+{N}\s+(ENSA|ELEKTRA)\s+{N}\s+{N}\s+{N}\s+EDECHI\s+{N}\s+{N}\s+{N}"
                    rf"\s+TOTAL\s+{N}\s+{N}\s+{N}", re.I)
SECCION = re.compile(r"CLIENTES\s*,?\s*VENTAS\s*(?:E|Y)\s*(?:INGRESOS|FACTURACI[ÓO]N)", re.I)
MES_ABR = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "oct": 10,
           "nov": 11, "dic": 12}
# 2013-04: pypdf devuelve la pagina 12 fragmentada (texto superpuesto). Transcripcion manual de la pag. 12;
# se acepta solo porque las 3 columnas suman exactamente el TOTAL publicado (verificado en procesar_boletin).
TRANSCRIPCION_MANUAL = {
    "2013_ABRIL.pdf": {"pagina": 12, "tokens": {
        "EDEMET": ("396,850", "317,245,351", "61,589,797"), "ENSA": ("379,381", "251,737,000", "48,488,000"),
        "EDECHI": ("118,031", "54,152,795", "8,452,949"), "TOTAL": ("894,262", "623,135,146", "118,530,746")}}}
FACTORES = (1, 1000, 0.001)
BANDA_KWH_CLIENTE = (100, 3000)
BANDA_USD_KWH = (0.05, 0.50)


def periodo_de_archivo(nombre):
    anio, mes = Path(nombre).stem.upper().split("_")
    return int(anio), config.MESES.index(mes) + 1


def _sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# ------------------------------------------------------------------ bronze: inventario y descarga de faltantes
def _meses_esperados():
    (a, m), fin = config.BOLETIN_DESDE, config.BOLETIN_HASTA
    while (a, m) <= fin:
        yield a, m
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)


def inventariar_boletines(descargar_faltantes=True):
    """Lista los PDF de data/raw/boletines_asep (sha256, tamano, fecha de descarga) y descarga SOLO los que falten
    del rango esperado. Escribe _inventario.json. No vuelve a descargar los existentes."""
    d = config.boletines_dir()
    d.mkdir(parents=True, exist_ok=True)
    inv_path = d / "_inventario.json"
    previo = json.loads(inv_path.read_text(encoding="utf-8")) if inv_path.exists() else {}
    previo = {x["archivo"]: x for x in previo.get("boletines", [])}
    faltantes = [(a, m) for a, m in _meses_esperados() if not (d / f"{a}_{config.MESES[m - 1]}.pdf").exists()]
    descargados, errores = [], []
    if faltantes and descargar_faltantes and not config.offline():
        for a, m in faltantes:
            mes = config.MESES[m - 1].lower() if a == 2017 else config.MESES[m - 1]
            url = config.URL_BOLETIN.format(anio=a, mes=mes)
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "sig-academico"}),
                                            timeout=60) as r:
                    datos = r.read()
                if not datos.startswith(b"%PDF"):
                    raise ValueError("la respuesta no es un PDF")
                (d / f"{a}_{config.MESES[m - 1]}.pdf").write_bytes(datos)
                descargados.append(url)
            except Exception as exc:  # explicito: el mes queda faltante y se audita
                errores.append({"url": url, "error": str(exc)[:120]})
                log.warning("No se pudo descargar %s: %s", url, exc)
    elif faltantes:
        log.warning("Faltan %d boletines y no se descargan (SIG_OFFLINE=1 o descarga desactivada)", len(faltantes))
    filas = []
    for p in sorted(d.glob("*.pdf")):
        sha = _sha256(p)
        ant = previo.get(p.name)
        # fecha de descarga: la registrada; si es nuevo, la fecha de modificacion del archivo
        fecha = ant["fecha_descarga"] if ant and ant.get("sha256") == sha else \
            datetime.fromtimestamp(p.stat().st_mtime).date().isoformat()
        a, m = periodo_de_archivo(p.name)
        mes_url = config.MESES[m - 1].lower() if a == 2017 else config.MESES[m - 1]
        filas.append({"archivo": p.name, "periodo_boletin": f"{a}-{m:02d}", "bytes": p.stat().st_size, "sha256": sha,
                      "fecha_descarga": fecha, "url": config.URL_BOLETIN.format(anio=a, mes=mes_url)})
    inv = {"fuente": "ASEP - Estadistica del Mercado Electrico Panameno (boletin mensual)",
           "generado": date.today().isoformat(), "boletines": filas, "descargados_en_esta_corrida": descargados,
           "errores_descarga": errores,
           "faltantes": [f"{a}-{m:02d}" for a, m in faltantes if f"{a}_{config.MESES[m - 1]}.pdf" not in
                         {x['archivo'] for x in filas}]}
    inv_path.write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")
    return inv


# ------------------------------------------------------------------ texto (cache)
def _n_imagenes(page):
    """Cuenta XObjects /Image de la pagina sin decodificarlos (page.images decodifica y es muy lento)."""
    try:
        xo = page["/Resources"].get_object().get("/XObject")
        xo = xo.get_object() if xo else {}
        return sum(1 for k in xo if xo[k].get_object().get("/Subtype") == "/Image")
    except Exception:
        return None


def textos_boletines(inventario=None):
    """{archivo: [texto por pagina]} con cache por sha256 en data/interim/textos_boletines.json."""
    import pypdf
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    inventario = inventario or inventariar_boletines(descargar_faltantes=False)
    cache_path = config.interim_dir() / "textos_boletines.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    out, nuevos = {}, 0
    for b in inventario["boletines"]:
        c = cache.get(b["archivo"])
        if not c or c.get("sha256") != b["sha256"]:
            r = pypdf.PdfReader(str(config.boletines_dir() / b["archivo"]))
            c = {"sha256": b["sha256"], "paginas": [p.extract_text() or "" for p in r.pages],
                 "imagenes_por_pagina": [_n_imagenes(p) for p in r.pages]}
            cache[b["archivo"]] = c
            nuevos += 1
        out[b["archivo"]] = c
    if nuevos:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    log.info("Texto de %d boletines (%d extraidos ahora con pypdf, %d desde cache)", len(out), nuevos, len(out) - nuevos)
    return out


# ------------------------------------------------------------------ parseo
def parse_num(tok):
    """Texto -> (valor float, mal_formado bool). Acepta 1,234,567 / 1,234,567.89 / 408734 / 298,826.74.
    Varios puntos ("54128.000.00", "57,135.000.00") = puntos usados como separador de miles: se conservan solo
    los dos ultimos digitos como decimales y se marca mal_formado."""
    s = tok.strip().rstrip(".")
    if s.count(".") > 1:
        ent, dec = s.replace(",", "").rsplit(".", 1)
        return float(ent.replace(".", "") + "." + dec), True
    try:
        return float(s.replace(",", "")), False
    except ValueError:
        return None, True


def _factor(valor, base, banda):
    return next((k for k in FACTORES if base and banda[0] <= valor * k / base <= banda[1]), None)


def buscar_tabla(paginas):
    """Devuelve (pagina 1-based, tokens {EMPRESA: (c, v, f)}, etiqueta_mes, encabezado) o Nones.
    El encabezado (120 caracteres antes del bloque) da unidad, moneda y concepto de ESA tabla (no de otras de la pagina)."""
    for i, t in enumerate(paginas):
        plano = re.sub(r"\s+", " ", t)
        m = BLOQUE.search(plano)
        if m:
            g = m.groups()
            tokens = {"EDEMET": g[0:3], "ENSA": g[4:7], "EDECHI": g[7:10], "TOTAL": g[10:13]}
            pre = plano[max(0, m.start() - 120):m.start()].upper()
            pos = [(pre.rfind(x), x) for x in config.MESES if x in pre]
            return i + 1, tokens, (max(pos)[1] if pos else None), pre
    return None, None, None, None


def _clasificar_sin_tabla(paginas, imagenes):
    for i, t in enumerate(paginas):
        s = SECCION.search(t)
        if s and not re.search(r"CONTENIDO|[ÍI]NDICE", t[:400], re.I):  # la pagina del indice no cuenta
            return "TABLA_EN_IMAGEN", f"seccion en pag. {i + 1} sin numeros en texto ({imagenes[i]} imagenes)"
    return "SECCION_AUSENTE", f"{len(paginas)} paginas; la seccion de clientes no aparece fuera del indice"


def procesar_boletin(archivo, paginas, imagenes=None):
    """Devuelve (estado_boletin dict, filas por distribuidora)."""
    anio, mes = periodo_de_archivo(archivo)
    periodo = f"{anio}-{mes:02d}"
    obs = []
    if archivo in TRANSCRIPCION_MANUAL:
        pag, tokens, etiqueta = TRANSCRIPCION_MANUAL[archivo]["pagina"], TRANSCRIPCION_MANUAL[archivo]["tokens"], None
        texto = re.sub(r"\s+", " ", paginas[pag - 1]) if pag <= len(paginas) else ""
        obs.append("transcripcion_manual")
    else:
        pag, tokens, etiqueta, texto = buscar_tabla(paginas)
    if not pag:
        estado, detalle = _clasificar_sin_tabla(paginas, imagenes or [0] * len(paginas))
        return {"archivo": archivo, "periodo": periodo, "estado": estado, "detalle": detalle, "pagina": None}, []
    moneda = "B/." if re.search(r"Balboas|B/\.", texto, re.I) else ("US$" if re.search(r"US\s*\$", texto) else "no indicada")
    unidad = "MWh" if re.search(r"\(\s*MWh\s*\)", texto, re.I) else ("GWh" if re.search(r"\(\s*GWh\s*\)", texto, re.I) else "kWh")
    concepto = "facturacion" if re.search(r"FACTURA", texto, re.I) else "ingresos"
    if etiqueta and etiqueta != config.MESES[mes - 1]:
        obs.append(f"etiqueta_mes_tabla={etiqueta}")
    val = {e: [parse_num(x) for x in tokens[e]] for e in tokens}
    # total publicado vs suma (en las cifras tal como estan escritas)
    for j, var in enumerate(("clientes", "ventas", "facturacion")):
        tot = val["TOTAL"][j][0]
        suma = sum(val[e][j][0] or 0 for e in D)
        if tot is None or abs(suma - tot) > max(2, abs(tot) * 1e-4):
            obs.append(f"total_no_cuadra_{var}")
    filas = []
    for e in D:
        (c, c_mal), (v, v_mal), (f, f_mal) = val[e]
        flags = []
        if c_mal or v_mal or f_mal:
            flags.append("numero_mal_formado")
        fv = _factor(v, c, BANDA_KWH_CLIENTE) if v and c else None
        ventas = round(v * fv) if fv else None
        if fv is None:
            flags.append("ventas_fuera_de_rango")
        elif fv != 1:
            flags.append(f"ventas_x{fv:g}")
        ff = _factor(f, ventas, BANDA_USD_KWH) if f and ventas else None
        fact = round(f * ff, 2) if ff else None
        if ff is None:
            flags.append("facturacion_fuera_de_rango")
        elif ff != 1:
            flags.append(f"facturacion_x{ff:g}")
        filas.append({"periodo": periodo, "anio": anio, "mes": mes, "distribuidora": e,
                      "clientes": int(c) if c else None, "ventas_kwh": ventas, "facturacion_usd": fact,
                      "clientes_texto": tokens[e][0], "ventas_texto": tokens[e][1], "facturacion_texto": tokens[e][2],
                      "factor_ventas": fv, "factor_facturacion": ff, "unidad_declarada": unidad,
                      "moneda_declarada": moneda, "concepto_monetario": concepto,
                      "flags_extraccion": ";".join(flags), "pagina": pag, "archivo": archivo})
    estado = "OK"
    if any(o.startswith("total_no_cuadra") for o in obs):
        estado = "TOTAL_NO_CUADRA"
    if any(f["flags_extraccion"] for f in filas):
        estado = "OK_CON_OBSERVACIONES" if estado == "OK" else estado
    if "transcripcion_manual" in obs:
        if any(o.startswith("total_no_cuadra") for o in obs):
            raise ValueError("La transcripcion manual de 2013-04 no cuadra con el total: revisar")
        estado = "TRANSCRIPCION_MANUAL"
    return {"archivo": archivo, "periodo": periodo, "estado": estado, "detalle": ";".join(obs), "pagina": pag,
            "moneda": moneda, "unidad_declarada": unidad, "concepto_monetario": concepto}, filas


def extraer_demanda_maxima(textos):
    """Serie mensual de demanda maxima del SIN (MW) de la tabla 'DEMANDA MAXIMA MENSUAL Y ANUAL' (pares mmm-aa valor).
    Para cada mes se usa el boletin mas reciente que lo publica; se registran discrepancias entre boletines."""
    vistos = {}
    for archivo in sorted(textos, key=periodo_de_archivo):
        for t in textos[archivo]["paginas"]:
            plano = re.sub(r"\s+", " ", t)
            m = re.search(r"DEMANDA M[ÁA]XIMA MENSUAL Y ANUAL", plano, re.I)
            if not m:
                continue
            seg = plano[m.end():m.end() + 600]
            pares = re.findall(r"\b(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\.?-(\d{2})\s+(\d[\d,]*(?:\.\d+)?)",
                               seg, re.I)
            for mm, aa, v in pares:
                mw = float(v.replace(",", ""))
                if 500 <= mw <= 5000:
                    vistos.setdefault(f"20{aa}-{MES_ABR[mm.lower()]:02d}", []).append((archivo, mw))
            if pares:  # la primera coincidencia suele ser el indice: se sigue hasta la tabla
                break
    filas = []
    for per in sorted(vistos):
        vals = vistos[per]
        distintos = sorted({v for _, v in vals})
        filas.append({"periodo": per, "demanda_max_mw": vals[-1][1], "boletin_fuente": vals[-1][0],
                      "n_boletines": len(vals), "discrepancia": "" if len(distintos) == 1 else
                      "valores distintos entre boletines: " + ", ".join(f"{v:g}" for v in distintos)})
    return filas


def _csv(path, filas):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)


def extraer_todo(descargar_faltantes=True):
    """Bronze -> silver/boletines_extraidos.csv + silver/log_extraccion.csv + silver/demanda_maxima_mensual.csv."""
    inv = inventariar_boletines(descargar_faltantes)
    textos = textos_boletines(inv)
    estados, filas = [], []
    for archivo in sorted(textos, key=periodo_de_archivo):
        e, f = procesar_boletin(archivo, textos[archivo]["paginas"], textos[archivo].get("imagenes_por_pagina"))
        estados.append(e)
        filas += f
    _csv(config.silver_dir() / "boletines_extraidos.csv", filas)
    _csv(config.silver_dir() / "log_extraccion.csv", estados)
    dem = extraer_demanda_maxima(textos)
    _csv(config.silver_dir() / "demanda_maxima_mensual.csv", dem)
    from collections import Counter
    res = {"boletines": len(estados), "filas": len(filas), "estados": dict(Counter(e["estado"] for e in estados)),
           "meses_demanda_maxima": len(dem)}
    log.info("Extraccion PDF: %s", res)
    return res


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print(extraer_todo())
