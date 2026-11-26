"""Persistencia NoSQL en MongoDB (pymongo): un documento por boletin PDF (texto extraido por pagina + tabla + metadatos)
y el manifiesto CKAN (un documento por recurso + la consulta completa).

MONGO_URI (defecto mongodb://localhost:27017), MONGO_DB (defecto sig_distribuidoras),
MONGO_TIMEOUT_MS (defecto 3000), MONGO_STRICT=1 -> si no hay Mongo, lanza error en vez de usar fallback.
Sin conexion y sin STRICT: log "MODO FALLBACK: sin Mongo, guardado a JSON" y archivos gold/mongo_fallback_*.json.
"""
import json
import logging
import os

import config

log = logging.getLogger("mongo")
URI_DEFECTO = "mongodb://localhost:27017"


def documentos_boletines():
    """Documentos por boletin: metadatos del inventario + estado de extraccion + filas extraidas + texto por pagina."""
    import calidad
    inv = json.loads((config.boletines_dir() / "_inventario.json").read_text(encoding="utf-8"))
    textos = json.loads((config.interim_dir() / "textos_boletines.json").read_text(encoding="utf-8"))
    estados = {e["archivo"]: e for e in calidad.leer_csv(config.silver_dir() / "log_extraccion.csv")}
    filas = {}
    for r in calidad.leer_csv(config.silver_dir() / "boletines_extraidos.csv"):
        filas.setdefault(r["archivo"], []).append({k: r[k] for k in ("distribuidora", "clientes", "ventas_kwh", "facturacion_usd",
                                                                    "clientes_texto", "ventas_texto", "facturacion_texto",
                                                                    "factor_ventas", "factor_facturacion", "flags_extraccion")})
    docs = []
    for b in inv["boletines"]:
        t = textos.get(b["archivo"], {})
        docs.append({**b, "_id": b["archivo"], "tipo": "boletin_asep_pdf", "extraccion": estados.get(b["archivo"], {}),
                     "tabla_clientes_ventas": filas.get(b["archivo"], []), "n_paginas": len(t.get("paginas", [])),
                     "paginas": [{"n": i + 1, "texto": x, "imagenes": (t.get("imagenes_por_pagina") or [None] * len(t["paginas"]))[i]}
                                 for i, x in enumerate(t.get("paginas", []))]})
    return docs


def documentos_manifiesto():
    reg = json.loads((config.ckan_dir() / "_descargas.json").read_text(encoding="utf-8"))
    return [{**r, "_id": r["resource_id"], "tipo": "recurso_ckan"} for r in reg.values()]


def conectar(uri=None, timeout_ms=None):
    from pymongo import MongoClient
    uri = uri or os.environ.get("MONGO_URI") or URI_DEFECTO
    timeout_ms = int(timeout_ms or os.environ.get("MONGO_TIMEOUT_MS") or 3000)
    cli = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
    cli.admin.command("ping")  # falla aqui si no hay servidor
    return cli


def _upsert(col, docs):
    # replace_one por documento (portable a mongomock); shortcut: ~170 docs por corrida, usar bulk_write si crece
    for d in docs:
        col.replace_one({"_id": d["_id"]}, d, upsert=True)
    return len(docs)


def guardar(boletines=None, manifiesto=None, client=None, db_name=None, fallback_dir=None):
    """Upsert idempotente de boletines y manifiesto CKAN. Devuelve {'modo': 'mongo'|'fallback_json', ...}."""
    from pymongo.errors import PyMongoError
    boletines = documentos_boletines() if boletines is None else boletines
    manifiesto = documentos_manifiesto() if manifiesto is None else manifiesto
    db_name = db_name or os.environ.get("MONGO_DB") or "sig_distribuidoras"
    try:
        cli = client or conectar()
        db = cli[db_name]
        n_b = _upsert(db["boletines_asep"], boletines)
        n_m = _upsert(db["manifiesto_ckan"], manifiesto)
        db["boletines_asep"].create_index("periodo_boletin")
        log.info("MongoDB: %d boletines y %d recursos CKAN upserted en %s", n_b, n_m, db_name)
        return {"modo": "mongo", "db": db_name, "boletines": n_b, "manifiesto_ckan": n_m}
    except PyMongoError as exc:
        if os.environ.get("MONGO_STRICT") == "1":
            raise RuntimeError(f"MongoDB no disponible y MONGO_STRICT=1: {exc}") from exc
        log.warning("MODO FALLBACK: sin Mongo, guardado a JSON (%s)", type(exc).__name__)
        d = fallback_dir or config.gold_dir()
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "mongo_fallback_boletines_asep.json"), "w", encoding="utf-8") as f:
            json.dump(boletines, f, ensure_ascii=False)
        with open(os.path.join(d, "mongo_fallback_manifiesto_ckan.json"), "w", encoding="utf-8") as f:
            json.dump(manifiesto, f, ensure_ascii=False, indent=1)
        return {"modo": "fallback_json", "boletines": len(boletines), "manifiesto_ckan": len(manifiesto)}
