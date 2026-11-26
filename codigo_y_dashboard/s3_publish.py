"""Publicacion opcional en almacenamiento compatible con S3 (boto3): MinIO local o Amazon S3.

S3_BUCKET           : bucket destino; sin el, la tarea se OMITE (y lo dice en el log).
AWS_ENDPOINT_URL    : endpoint S3 no-AWS (p. ej. MinIO local http://localhost:9000). Sin el, se usa Amazon S3.
AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY : credenciales (cadena estandar de boto3). AWS_REGION (defecto us-east-1).
S3_PREFIX           : prefijo raiz (defecto sig-distribuidoras-asep); debajo va la fecha de la corrida.
Sube los artefactos gold y dashboard_interactivo.html. Cualquier error de subida hace fallar la tarea.
"""
import logging
import os
from datetime import date
from pathlib import Path

import config

log = logging.getLogger("s3")


def destino(env):
    """Etiqueta honesta del destino segun el endpoint configurado."""
    endpoint = env.get("AWS_ENDPOINT_URL_S3") or env.get("AWS_ENDPOINT_URL")
    if not endpoint:
        return None, "Amazon S3"
    if "amazonaws.com" in endpoint:
        return endpoint, "Amazon S3"
    return endpoint, "S3 compatible (MinIO local)"


def publicar(env=None):
    env = os.environ if env is None else env
    bucket = env.get("S3_BUCKET")
    if not bucket:
        log.info("S3 OMITIDO: variable S3_BUCKET no definida")
        return {"estado": "omitido", "motivo": "sin S3_BUCKET"}
    import boto3
    from botocore.config import Config
    endpoint, modo = destino(env)
    sesion = boto3.Session()
    if sesion.get_credentials() is None:
        log.warning("S3 OMITIDO: S3_BUCKET=%s pero no hay credenciales (%s)", bucket, modo)
        return {"estado": "omitido", "motivo": "sin credenciales", "modo": modo}
    # path-style: MinIO no resuelve buckets como subdominio (bucket.localhost)
    s3 = sesion.client("s3", endpoint_url=endpoint, region_name=env.get("AWS_REGION") or "us-east-1",
                       config=Config(s3={"addressing_style": "path"}) if endpoint else None)
    prefijo = f"{env.get('S3_PREFIX') or 'sig-distribuidoras-asep'}/{date.today().isoformat()}"
    gold = config.gold_dir()
    archivos = [(p, f"{prefijo}/gold/{p.name}") for p in sorted(gold.glob("*"))
                if p.is_file() and not p.name.startswith("mongo_fallback_")]  # fallback = salida de contingencia, no gold
    html = config.out_dir() / "dashboard_interactivo.html"
    if html.exists():
        archivos.append((html, f"{prefijo}/dashboard/{html.name}"))
    if not archivos:
        raise RuntimeError(f"S3 ({modo}): no hay artefactos gold en {gold} para publicar")
    for p, key in archivos:
        s3.upload_file(str(p), bucket, key)  # lanza excepcion si falla: nada de errores silenciosos
        log.info("S3 subido: s3://%s/%s (%d bytes)", bucket, key, p.stat().st_size)
    log.info("S3 [%s]: %d archivos subidos a s3://%s/%s", modo, len(archivos), bucket, prefijo)
    return {"estado": "publicado", "modo": modo, "endpoint": endpoint, "bucket": bucket, "prefijo": prefijo,
            "archivos": len(archivos), "claves": [k for _, k in archivos]}
