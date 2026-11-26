"""Pipeline ETL Bronze -> Silver -> Gold del SIG de distribuidoras electricas (ASEP, Panama).

Bronze (data/raw)  : boletines PDF de ASEP, CSV de reclamos (CKAN) y manifiesto JSON de la API CKAN, tal como se bajaron.
Silver (data/silver): tablas limpias con flags de calidad (boletines_extraidos, mercado_mensual, reclamos_*, demanda_maxima).
Gold (data/gold)   : SQLite en estrella (sig_distribuidoras.db), KPIs/LMDI (CSV + kpi_summary.json), calidad_auditoria.json.

Uso: python pipeline_etl.py            (todo el flujo sin Mongo/IA/dashboard; el DAG orquesta el flujo completo)
"""
import csv
import json
import logging
import sqlite3

import analisis
import calidad
import ckan_client
import config
import extraer_boletines

log = logging.getLogger("etl")


def _csv(path, filas):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)


# ------------------------------------------------------------------ extraccion
def extraer_ckan():
    """API CKAN (JSON) -> descarga CSV -> silver/reclamos_*.csv. Agrega la auditoria CKAN al JSON de calidad."""
    sync = ckan_client.sincronizar()
    dist, sector, aud, cruce = ckan_client.leer_reclamos(sync["recursos"])
    if not dist:
        raise RuntimeError("No se pudo leer ningun CSV de reclamos por distribuidora")
    _csv(config.silver_dir() / "reclamos_distribuidora_mensual.csv", dist)
    _csv(config.silver_dir() / "reclamos_sector_mensual.csv", sector)
    out = {"modo": sync["modo"], "manifiesto": sync.get("manifiesto"), "archivos": aud,
           "cruce_suma_distribuidoras_vs_sector_electricidad": {
               "meses_comparados": len([c for c in cruce if c["sector_electricidad"] is not None]),
               "meses_que_no_cuadran": [c for c in cruce if c["sector_electricidad"] is not None and not c["cuadra"]]}}
    (config.silver_dir() / "auditoria_ckan.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"modo": sync["modo"], "csv": len(aud), "filas_distribuidora": len(dist), "filas_sector": len(sector),
            "meses_no_cuadran": len(out["cruce_suma_distribuidoras_vs_sector_electricidad"]["meses_que_no_cuadran"])}


def extraer_pdf():
    return extraer_boletines.extraer_todo()


def limpiar():
    aud = calidad.ejecutar()
    ck = config.silver_dir() / "auditoria_ckan.json"
    if ck.exists():  # la auditoria de calidad reune PDF + CSV/JSON
        aud["ckan"] = json.loads(ck.read_text(encoding="utf-8"))
        (config.gold_dir() / "calidad_auditoria.json").write_text(json.dumps(aud, ensure_ascii=False, indent=1, default=str),
                                                                   encoding="utf-8")
    return {"filas_imputadas": aud["filas_imputadas"], "incidencias": len(aud["incidencias"])}


# ------------------------------------------------------------------ SQL (estrella)
SCHEMA = """
CREATE TABLE dim_distribuidora (distribuidora_id INTEGER PRIMARY KEY, codigo TEXT UNIQUE NOT NULL, nombre_legal TEXT,
    zona_concesion TEXT);
CREATE TABLE dim_tiempo (periodo TEXT PRIMARY KEY, anio INTEGER NOT NULL, mes INTEGER NOT NULL, trimestre INTEGER NOT NULL,
    nombre_mes TEXT NOT NULL, en_periodo_base INTEGER NOT NULL);
CREATE TABLE fact_mercado_mensual (periodo TEXT NOT NULL REFERENCES dim_tiempo(periodo),
    distribuidora_id INTEGER NOT NULL REFERENCES dim_distribuidora(distribuidora_id),
    clientes INTEGER, ventas_kwh REAL, facturacion_usd REAL,
    clientes_fuente REAL, ventas_kwh_fuente REAL, facturacion_usd_fuente REAL,
    clientes_flags TEXT, ventas_kwh_flags TEXT, facturacion_usd_flags TEXT,
    clientes_imputacion TEXT, ventas_kwh_imputacion TEXT, facturacion_usd_imputacion TEXT,
    flags_extraccion TEXT, flags_boletin TEXT, estado_boletin TEXT, imputado INTEGER NOT NULL, archivo_boletin TEXT, pagina TEXT,
    PRIMARY KEY (periodo, distribuidora_id));
CREATE TABLE fact_reclamos_mensual (periodo TEXT NOT NULL REFERENCES dim_tiempo(periodo),
    distribuidora_id INTEGER NOT NULL REFERENCES dim_distribuidora(distribuidora_id), reclamos INTEGER,
    reclamos_por_10k_clientes REAL, archivo_csv TEXT, PRIMARY KEY (periodo, distribuidora_id));
CREATE TABLE fact_reclamos_sector_mensual (periodo TEXT NOT NULL REFERENCES dim_tiempo(periodo), sector TEXT NOT NULL,
    reclamos INTEGER, archivo_csv TEXT, PRIMARY KEY (periodo, sector));
CREATE TABLE fact_demanda_maxima_mensual (periodo TEXT PRIMARY KEY REFERENCES dim_tiempo(periodo), demanda_max_mw REAL,
    boletin_fuente TEXT, discrepancia TEXT);
CREATE TABLE fact_descomposicion (distribuidora_id INTEGER REFERENCES dim_distribuidora(distribuidora_id), codigo TEXT NOT NULL,
    tipo TEXT NOT NULL, anio_base INTEGER NOT NULL, anio_fin INTEGER NOT NULL, ventas_base_gwh REAL, ventas_fin_gwh REAL,
    delta_gwh REAL, efecto_clientes_gwh REAL, efecto_consumo_por_cliente_gwh REAL, pct_clientes REAL,
    pct_consumo_por_cliente REAL, PRIMARY KEY (codigo, tipo, anio_base, anio_fin));
CREATE VIEW vw_bi_kpi_anual AS
    SELECT t.anio, d.codigo AS distribuidora, COUNT(*) AS meses, ROUND(SUM(f.ventas_kwh)/1e6, 3) AS ventas_gwh,
           ROUND(AVG(f.clientes)) AS clientes_promedio, ROUND(SUM(f.ventas_kwh)/AVG(f.clientes)/12, 1) AS kwh_cliente_mes,
           ROUND(SUM(f.facturacion_usd)/SUM(f.ventas_kwh), 4) AS ingreso_medio_usd_kwh, SUM(f.imputado) AS meses_con_imputacion
    FROM fact_mercado_mensual f JOIN dim_tiempo t USING (periodo) JOIN dim_distribuidora d USING (distribuidora_id)
    WHERE t.en_periodo_base = 1 GROUP BY t.anio, d.codigo;
CREATE VIEW vw_bi_descomposicion AS
    SELECT codigo AS distribuidora, tipo, anio_base, anio_fin, delta_gwh, efecto_clientes_gwh, efecto_consumo_por_cliente_gwh,
           pct_clientes, pct_consumo_por_cliente FROM fact_descomposicion;
CREATE VIEW vw_bi_reclamos_vs_ventas AS
    SELECT f.periodo, d.codigo AS distribuidora, r.reclamos, r.reclamos_por_10k_clientes, f.clientes, f.ventas_kwh,
           ROUND(f.ventas_kwh / f.clientes, 1) AS kwh_cliente_mes
    FROM fact_reclamos_mensual r JOIN fact_mercado_mensual f USING (periodo, distribuidora_id)
    JOIN dim_distribuidora d USING (distribuidora_id);
CREATE VIEW vw_bi_calidad AS
    SELECT f.periodo, d.codigo AS distribuidora, f.estado_boletin, f.clientes_flags, f.ventas_kwh_flags, f.facturacion_usd_flags,
           f.clientes_fuente, f.clientes, f.ventas_kwh_fuente, f.ventas_kwh, f.facturacion_usd_fuente, f.facturacion_usd
    FROM fact_mercado_mensual f JOIN dim_distribuidora d USING (distribuidora_id)
    WHERE f.imputado = 1 OR f.clientes_flags <> '' OR f.ventas_kwh_flags <> '' OR f.facturacion_usd_flags <> '';
"""


def _num(x):
    return None if x in (None, "") else float(x)


def cargar_sqlite(db_path=None):
    """silver + gold CSV -> SQLite en estrella (se recrea en cada corrida: idempotente)."""
    db_path = db_path or config.db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    s = config.silver_dir()
    mensual = calidad.leer_csv(s / "mercado_mensual.csv")
    rec = calidad.leer_csv(s / "reclamos_distribuidora_mensual.csv")
    sec = calidad.leer_csv(s / "reclamos_sector_mensual.csv")
    dem = calidad.leer_csv(s / "demanda_maxima_mensual.csv")
    periodos = sorted({r["periodo"] for r in mensual} | {r["periodo"] for r in rec} | {r["periodo"] for r in sec}
                      | {r["periodo"] for r in dem})
    ids = {d: i + 1 for i, d in enumerate(config.DISTRIBUIDORAS)}
    cli = {(r["periodo"], r["distribuidora"]): float(r["clientes"]) for r in mensual}
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO dim_distribuidora VALUES (?,?,?,?)",
                         [(i, d, config.NOMBRES_LEGALES[d], config.ZONAS[d]) for d, i in ids.items()])
        conn.executemany("INSERT INTO dim_tiempo VALUES (?,?,?,?,?,?)",
                         [(p, int(p[:4]), int(p[5:]), (int(p[5:]) - 1) // 3 + 1, config.MESES[int(p[5:]) - 1].capitalize(),
                           int(config.ANIO_INICIO <= int(p[:4]) <= config.ANIO_FIN)) for p in periodos])
        conn.executemany("INSERT INTO fact_mercado_mensual VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         [(r["periodo"], ids[r["distribuidora"]], int(r["clientes"]), _num(r["ventas_kwh"]), _num(r["facturacion_usd"]),
                           _num(r["clientes_fuente"]), _num(r["ventas_kwh_fuente"]), _num(r["facturacion_usd_fuente"]),
                           r["clientes_flags"], r["ventas_kwh_flags"], r["facturacion_usd_flags"], r["clientes_imputacion"],
                           r["ventas_kwh_imputacion"], r["facturacion_usd_imputacion"], r["flags_extraccion"], r["flags_boletin"],
                           r["estado_boletin"], int(r["imputado"]), r["archivo"], r["pagina"]) for r in mensual])
        conn.executemany("INSERT INTO fact_reclamos_mensual VALUES (?,?,?,?,?)",
                         [(r["periodo"], ids[r["distribuidora"]], int(r["reclamos"]) if r["reclamos"] else None,
                           round(int(r["reclamos"]) / cli[(r["periodo"], r["distribuidora"])] * 1e4, 3)
                           if r["reclamos"] and (r["periodo"], r["distribuidora"]) in cli else None, r["archivo"])
                          for r in rec if r["distribuidora"] in ids])
        conn.executemany("INSERT INTO fact_reclamos_sector_mensual VALUES (?,?,?,?)",
                         [(r["periodo"], r["sector"], int(r["reclamos"]) if r["reclamos"] else None, r["archivo"]) for r in sec])
        conn.executemany("INSERT INTO fact_demanda_maxima_mensual VALUES (?,?,?,?)",
                         [(r["periodo"], float(r["demanda_max_mw"]), r["boletin_fuente"], r["discrepancia"]) for r in dem])
        conn.commit()
        n = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
             ("fact_mercado_mensual", "fact_reclamos_mensual", "fact_reclamos_sector_mensual", "fact_demanda_maxima_mensual",
              "fact_descomposicion")}
    finally:
        conn.close()
    log.info("SQLite %s: %s", db_path.name, n)
    return {"db": str(db_path), **n}


def cargar_descomposicion_sql(db_path=None):
    """gold/lmdi_descomposicion.csv -> fact_descomposicion (la tabla de hechos se llena despues del calculo gold)."""
    ids = {d: i + 1 for i, d in enumerate(config.DISTRIBUIDORAS)}
    filas = calidad.leer_csv(config.gold_dir() / "lmdi_descomposicion.csv")
    conn = sqlite3.connect(db_path or config.db_path())
    try:
        conn.execute("DELETE FROM fact_descomposicion")
        conn.executemany("INSERT INTO fact_descomposicion VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         [(ids.get(r["distribuidora"]), r["distribuidora"], r["tipo"], int(r["anio_base"]), int(r["anio_fin"]),
                           float(r["ventas_base_gwh"]), float(r["ventas_fin_gwh"]), float(r["delta_gwh"]),
                           float(r["efecto_clientes_gwh"]), float(r["efecto_consumo_por_cliente_gwh"]),
                           _num(r["pct_clientes"]), _num(r["pct_consumo_por_cliente"])) for r in filas])
        conn.commit()
    finally:
        conn.close()
    return len(filas)


def construir_gold():
    r = analisis.construir_gold()
    n = cargar_descomposicion_sql()
    return {"respuesta": r["respuesta"]["mayor_crecimiento_pct"], "filas_fact_descomposicion": n}


def run_pipeline():
    pasos = [extraer_ckan, extraer_pdf, limpiar, cargar_sqlite, construir_gold]
    return {p.__name__: p() for p in pasos}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print(json.dumps(run_pipeline(), ensure_ascii=False, indent=1, default=str))
