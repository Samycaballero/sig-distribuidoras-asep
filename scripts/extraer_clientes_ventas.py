"""Extrae clientes, ventas (kWh) y facturacion por distribuidora de los boletines
mensuales de ASEP (PDF) y escribe data/interim/clientes_ventas.csv + un log de calidad.

Uso: python -I scripts/extraer_clientes_ventas.py <carpeta_boletines> <salida_csv>
"""
import csv, re, sys, pathlib
import pypdf

MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO",
         "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
# nombres con que aparece cada distribuidora en los boletines
ALIAS = {"EDEMET": r"EDEMET", "ENSA": r"ENSA|ELEKTRA", "EDECHI": r"EDECHI"}
NUM = r"([\d][\d,\.]*)"


def num(s):
    """Convierte '1,234,567.89' / '1,234,567' a float; None si el texto viene mal formado."""
    s = s.strip().rstrip(".")
    try:
        if s.count(",") and s.count("."):          # 1,234,567.89
            return float(s.replace(",", ""))
        if s.count(",") > 1 or re.fullmatch(r"\d{1,3}(,\d{3})+", s):
            return float(s.replace(",", ""))       # 1,234,567
        return float(s.replace(",", "."))
    except ValueError:
        return None


def pagina_clientes(reader):
    for i, p in enumerate(reader.pages):
        t = p.extract_text() or ""
        if re.search(r"CLIENTES\s*,?\s*VENTAS", t, re.I) and re.search(r"EDEMET", t):
            if re.search(r"N[ÚU]MERO|CLIENTES", t) and re.search(r"\d{3},\d{3}", t):
                return i + 1, t
    return None, ""


def extraer(texto):
    plano = re.sub(r"\s+", " ", texto)
    out = {}
    for emp, pat in ALIAS.items():
        m = re.search(rf"(?:{pat})\s+{NUM}\s+{NUM}\s+{NUM}", plano)
        if m:
            vals = tuple(num(g) for g in m.groups())
            if None not in vals:  # valor mal formado -> la empresa queda como faltante en el log
                out[emp] = vals
    m = re.search(rf"TOTAL\s+{NUM}\s+{NUM}\s+{NUM}", plano)
    if m:
        vals = tuple(num(g) for g in m.groups())
        if None not in vals:
            out["TOTAL"] = vals
    unidad = "MWh" if re.search(r"\(\s*MWh\s*\)", plano, re.I) else "kWh"
    moneda = "Balboas" if re.search(r"Balboas", plano, re.I) else ("US $" if re.search(r"US\s*\$", plano) else "no indicada")
    return out, unidad, moneda


def main(carpeta, salida):
    carpeta, salida = pathlib.Path(carpeta), pathlib.Path(salida)
    filas, log = [], []
    for f in sorted(carpeta.glob("*.pdf")):
        anio, mes = f.stem.split("_")
        n_mes = MESES.index(mes) + 1
        try:
            r = pypdf.PdfReader(str(f))
        except Exception as e:  # PDF ilegible
            log.append((anio, mes, "ERROR_PDF", str(e)[:80])); continue
        pag, t = pagina_clientes(r)
        if not pag:
            log.append((anio, mes, "SIN_TABLA", f"{len(r.pages)} paginas")); continue
        datos, unidad, moneda = extraer(t)
        faltan = [e for e in ALIAS if e not in datos]
        estado = "OK"
        if faltan:
            estado = "FALTA_" + "_".join(faltan)
        elif "TOTAL" in datos:
            sc = sum(datos[e][0] for e in ALIAS); sv = sum(datos[e][1] for e in ALIAS)
            if abs(sc - datos["TOTAL"][0]) > 2 or abs(sv - datos["TOTAL"][1]) / max(sv, 1) > 0.001:
                estado = "TOTAL_NO_CUADRA"
        for e in ALIAS:
            if e in datos:
                c, v, fac = datos[e]
                # La unidad no siempre se lee junto a la tabla: se infiere por magnitud.
                # Un cliente regulado consume del orden de 100-3,000 kWh/mes.
                factor = next((k for k in (1, 1000, 0.001) if 100 <= v * k / c <= 3000), None)
                if factor is None:
                    log.append((anio, mes, f"VENTAS_FUERA_DE_RANGO_{e}", f"{v / c:.4g} por cliente")); continue
                filas.append({"anio": anio, "mes": n_mes, "periodo": f"{anio}-{n_mes:02d}",
                              "distribuidora": e, "clientes": int(c), "ventas_kwh": round(v * factor),
                              "facturacion": round(fac, 2), "moneda_fuente": moneda,
                              "unidad_texto": unidad, "factor_unidad": factor,
                              "pagina": pag, "archivo": f.name})
        log.append((anio, mes, estado, f"pag {pag}, unidad {unidad}, moneda {moneda}"))
    filas.sort(key=lambda x: (x["periodo"], x["distribuidora"]))
    salida.parent.mkdir(parents=True, exist_ok=True)
    with open(salida, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys())); w.writeheader(); w.writerows(filas)
    with open(salida.with_name("log_extraccion.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["anio", "mes", "estado", "detalle"]); w.writerows(log)
    from collections import Counter
    print("boletines:", len(log), "| filas:", len(filas), "| estados:", dict(Counter(x[2] for x in log)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
