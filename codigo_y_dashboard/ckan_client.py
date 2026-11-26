"""Tipos de dato 2 (CSV) y 3 (JSON): portal de datos abiertos de Panama (CKAN, https://www.datosabiertos.gob.pa).

Automatizacion: la API CKAN (JSON) se usa como catalogo/manifiesto. El pipeline
  1. consulta package_search (q = config.CKAN_CONSULTAS) y guarda la respuesta JSON en bronze
     (data/raw/ckan/manifiesto_ckan_AAAA-MM-DD.json) junto con resource_show de cada recurso elegido;
  2. elige los CSV de "ASEP - Estadisticas de Reclamos de Electricidad AAAA" (por distribuidora) y
     "ASEP - Estadisticas de Reclamos Admitidos por Sector" (Electricidad/Agua/Telecom);
  3. descarga cada CSV solo si es nuevo o cambio su last_modified (registro en data/raw/ckan/_descargas.json).
Si la red falla (o SIG_OFFLINE=1) usa la copia de data/raw/ckan y lo avisa con WARNING "SIN RED".
"""
import csv
import hashlib
import io
import json
import logging
import re
import urllib.parse
import urllib.request
from datetime import date

import config

log = logging.getLogger("ckan")
UA = {"User-Agent": "sig-academico-utp/1.0"}
ORG_ASEP = "autoridad-nacional-de-los-servicios-publicos"
MESES_CSV = {m.capitalize(): i + 1 for i, m in enumerate(config.MESES)}
COLUMNAS_DIST = (("Metro Oeste", "EDEMET"), ("Noreste", "ENSA"), ("Chiriqu", "EDECHI"), ("Liberty", "OTRA_LIBERTY"))


def _get_json(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    if not d.get("success"):
        raise RuntimeError(f"CKAN respondio success=false para {url}")
    return d["result"]


def tipo_paquete(titulo):
    t = titulo.lower()
    if "reclamos de electricidad" in t:
        return "reclamos_electricidad"
    if "reclamos admitidos por sector" in t:
        return "reclamos_sector"
    return None


def elegir_recursos(paquetes):
    """De los paquetes de package_search elige un CSV por (tipo, anio): el de last_modified mas reciente."""
    elegidos = {}
    for p in paquetes:
        tipo = tipo_paquete(p.get("title", ""))
        if not tipo or (p.get("organization") or {}).get("name") != ORG_ASEP:
            continue
        for r in p.get("resources", []):
            if (r.get("format") or "").upper() != "CSV":
                continue
            m = re.search(r"(20\d\d)", r.get("name", "")) or re.search(r"(20\d\d)", p["title"])
            if not m:
                continue
            clave = (tipo, int(m.group(1)))
            lm = r.get("last_modified") or r.get("metadata_modified") or ""
            if clave not in elegidos or lm > elegidos[clave]["last_modified"]:
                elegidos[clave] = {"tipo": tipo, "anio": int(m.group(1)), "paquete": p["name"], "paquete_titulo": p["title"],
                                   "resource_id": r["id"], "recurso": r.get("name"), "url": r["url"], "last_modified": lm,
                                   "archivo": f"{tipo}_{m.group(1)}.csv"}
    return [elegidos[k] for k in sorted(elegidos)]


def _registro():
    p = config.ckan_dir() / "_descargas.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _copia_local(motivo):
    reg = _registro()
    manifiestos = sorted(config.ckan_dir().glob("manifiesto_ckan_*.json"))
    if not reg or not manifiestos:
        raise RuntimeError(f"SIN RED ({motivo}) y no hay copia local en {config.ckan_dir()}")
    log.warning("SIN RED: %s -> se usa la copia local de data/raw/ckan (%s, %d CSV)", motivo, manifiestos[-1].name, len(reg))
    return {"modo": "copia_local", "motivo": motivo, "manifiesto": manifiestos[-1].name, "recursos": list(reg.values())}


def sincronizar():
    """Descubre (API JSON) y descarga (CSV). Devuelve {'modo': 'red'|'copia_local', 'recursos': [...]}."""
    d = config.ckan_dir()
    d.mkdir(parents=True, exist_ok=True)
    if config.offline():
        return _copia_local("SIG_OFFLINE=1")
    hoy = date.today().isoformat()
    try:
        consultas, paquetes = [], {}
        for q in config.CKAN_CONSULTAS:
            url = f"{config.CKAN_BASE}/api/3/action/package_search?q={urllib.parse.quote(q)}&rows=50"
            res = _get_json(url)
            consultas.append({"url": url, "count": res["count"], "result": res})
            for p in res["results"]:
                paquetes[p["id"]] = p
        recursos = elegir_recursos(paquetes.values())
        if not recursos:
            raise RuntimeError("package_search no devolvio recursos de reclamos de ASEP")
        detalle = {}
        for r in recursos:
            rs = _get_json(f"{config.CKAN_BASE}/api/3/action/resource_show?id={r['resource_id']}")
            detalle[r["resource_id"]] = rs
            r["last_modified"] = rs.get("last_modified") or rs.get("metadata_modified") or r["last_modified"]
    except Exception as exc:  # red caida, DNS, 5xx, JSON invalido
        return _copia_local(f"{type(exc).__name__}: {str(exc)[:100]}")
    manifiesto = {"fuente": config.CKAN_BASE, "fecha_consulta": hoy, "consultas": consultas,
                  "recursos_elegidos": recursos, "resource_show": detalle}
    (d / f"manifiesto_ckan_{hoy}.json").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=1), encoding="utf-8")
    reg, nuevos = _registro(), 0
    for r in recursos:
        ant = reg.get(r["archivo"])
        if ant and ant.get("last_modified") == r["last_modified"] and (d / r["archivo"]).exists():
            continue
        try:
            with urllib.request.urlopen(urllib.request.Request(r["url"], headers=UA), timeout=60) as resp:
                datos = resp.read()
        except Exception as exc:
            log.warning("No se pudo descargar %s (%s); se conserva la copia anterior si existe", r["url"], exc)
            continue
        (d / r["archivo"]).write_bytes(datos)
        reg[r["archivo"]] = {**r, "fecha_descarga": hoy, "bytes": len(datos), "sha256": hashlib.sha256(datos).hexdigest()}
        nuevos += 1
    (d / "_descargas.json").write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("CKAN: %d recursos en el manifiesto, %d CSV descargados ahora, %d ya estaban al dia",
             len(recursos), nuevos, len(recursos) - nuevos)
    return {"modo": "red", "manifiesto": f"manifiesto_ckan_{hoy}.json", "recursos": list(reg.values()), "nuevos": nuevos}


# ------------------------------------------------------------------ parseo de los CSV
def leer_texto(path):
    b = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return b.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return b.decode("latin-1"), "latin-1"


def _filas_mensuales(texto):
    """Primer bloque 'Mes;...' del CSV; se detiene en el primer renglon que no es un mes (p. ej. bloque Provincia)."""
    rows = list(csv.reader(io.StringIO(texto), delimiter=";"))
    cab = [c.strip() for c in rows[0]]
    if not cab or cab[0].lower() != "mes":
        raise ValueError(f"cabecera inesperada: {cab[:3]}")
    datos = []
    for r in rows[1:]:
        if not r or r[0].strip().capitalize() not in MESES_CSV:
            break
        datos.append(r)
    return cab, datos


def parse_reclamos_distribuidora(path, anio):
    texto, enc = leer_texto(path)
    cab, datos = _filas_mensuales(texto)
    cols = {}
    for j, c in enumerate(cab[1:], start=1):
        dist = next((d for k, d in COLUMNAS_DIST if k.lower() in c.lower()), None)
        if dist is None and c:
            raise ValueError(f"{path.name}: columna no reconocida {c!r}")
        if dist:
            cols[j] = dist
    out = []
    for r in datos:
        mes = MESES_CSV[r[0].strip().capitalize()]
        for j, dist in cols.items():
            v = r[j].strip() if j < len(r) else ""
            out.append({"anio": anio, "mes": mes, "periodo": f"{anio}-{mes:02d}", "distribuidora": dist,
                        "reclamos": int(v) if v else None, "archivo": path.name, "codificacion": enc})
    return out


def parse_reclamos_sector(path, anio):
    texto, enc = leer_texto(path)
    cab, datos = _filas_mensuales(texto)
    out = []
    for r in datos:
        mes = MESES_CSV[r[0].strip().capitalize()]
        for j, sector in enumerate(cab[1:], start=1):
            v = r[j].strip() if j < len(r) else ""
            out.append({"anio": anio, "mes": mes, "periodo": f"{anio}-{mes:02d}", "sector": sector,
                        "reclamos": int(v) if v else None, "archivo": path.name})
    return out


def leer_reclamos(recursos):
    """Parsea los CSV registrados. Devuelve (por_distribuidora, por_sector, auditoria)."""
    dist, sector, aud = [], [], []
    for r in sorted(recursos, key=lambda x: x["archivo"]):
        p = config.ckan_dir() / r["archivo"]
        try:
            filas = (parse_reclamos_distribuidora if r["tipo"] == "reclamos_electricidad" else parse_reclamos_sector)(p, r["anio"])
        except Exception as exc:
            aud.append({"archivo": r["archivo"], "estado": "ERROR", "detalle": str(exc)[:150]})
            log.warning("CSV %s no se pudo leer: %s", r["archivo"], exc)
            continue
        (dist if r["tipo"] == "reclamos_electricidad" else sector).extend(filas)
        meses = sorted({f["mes"] for f in filas})
        aud.append({"archivo": r["archivo"], "estado": "OK", "meses": len(meses),
                    "detalle": "" if len(meses) == 12 else f"anio incompleto: meses {meses[0]}-{meses[-1]}",
                    "last_modified": r.get("last_modified"), "fecha_descarga": r.get("fecha_descarga")})
    # verificacion cruzada: suma por distribuidora == sector Electricidad
    elec = {f["periodo"]: f["reclamos"] for f in sector if f["sector"].lower().startswith("electricidad")}
    sumas = {}
    for f in dist:
        sumas[f["periodo"]] = sumas.get(f["periodo"], 0) + (f["reclamos"] or 0)
    cruce = [{"periodo": p, "suma_distribuidoras": s, "sector_electricidad": elec.get(p),
              "cuadra": elec.get(p) == s} for p, s in sorted(sumas.items())]
    return dist, sector, aud, cruce
