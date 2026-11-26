import csv
import json
import logging
import sqlite3

import boto3
import mongomock
import pytest
from moto import mock_aws

import mongo_store
import s3_publish


# ---------------- SQLite en estrella
def test_sqlite_estrella(corrida):
    con = sqlite3.connect(corrida["gold"] / "sig_distribuidoras.db")
    try:
        q = lambda s: con.execute(s).fetchall()  # noqa: E731
        assert q("SELECT COUNT(*) FROM dim_distribuidora")[0][0] == 3
        assert q("SELECT COUNT(*) FROM fact_mercado_mensual")[0][0] == 162 * 3
        assert q("SELECT COUNT(*) FROM fact_mercado_mensual f LEFT JOIN dim_tiempo t USING (periodo) WHERE t.periodo IS NULL")[0][0] == 0
        assert q("SELECT COUNT(*) FROM fact_reclamos_mensual")[0][0] > 150
        assert q("SELECT COUNT(*) FROM fact_descomposicion WHERE tipo='acumulada'")[0][0] == 8
        v = dict(q("SELECT distribuidora, ventas_gwh FROM vw_bi_kpi_anual WHERE anio = 2025"))
        orig = q("SELECT ventas_kwh_fuente, ventas_kwh, ventas_kwh_flags FROM fact_mercado_mensual WHERE periodo='2021-10' AND distribuidora_id=1")[0]
        assert orig[0] == 828014691 and orig[1] < 3e8 and "atipico_puntual" in orig[2]  # original conservado
        assert q("SELECT COUNT(*) FROM vw_bi_calidad")[0][0] > 50
    finally:
        con.close()
    with open(corrida["gold"] / "kpi_anual.csv", encoding="utf-8") as f:
        kpi = {r["distribuidora"]: float(r["ventas_gwh"]) for r in csv.DictReader(f) if r["anio"] == "2025"}
    for d in ("EDEMET", "ENSA", "EDECHI"):
        assert v[d] == pytest.approx(kpi[d], abs=1e-3)


# ---------------- MongoDB (mongomock / fallback)
BOL = [{"_id": "2021_DICIEMBRE.pdf", "archivo": "2021_DICIEMBRE.pdf", "periodo_boletin": "2021-12",
        "paginas": [{"n": 1, "texto": "EDEMET 547,347"}], "tabla_clientes_ventas": [{"distribuidora": "EDEMET", "clientes": "547347"}]}]
MAN = [{"_id": "r1", "archivo": "reclamos_electricidad_2025.csv", "last_modified": "2025-12-16", "tipo": "recurso_ckan"}]


def test_mongo_upsert_idempotente_con_mongomock():
    cli = mongomock.MongoClient()
    for _ in range(2):
        r = mongo_store.guardar(BOL, MAN, client=cli, db_name="t")
    assert r == {"modo": "mongo", "db": "t", "boletines": 1, "manifiesto_ckan": 1}
    assert cli["t"]["boletines_asep"].count_documents({}) == 1
    assert cli["t"]["boletines_asep"].find_one({"periodo_boletin": "2021-12"})["paginas"][0]["texto"].startswith("EDEMET")
    assert cli["t"]["manifiesto_ckan"].find_one({"_id": "r1"})["last_modified"] == "2025-12-16"


def test_mongo_documentos_reales(en_corrida):
    docs = mongo_store.documentos_boletines()
    assert len(docs) == 162
    d = next(x for x in docs if x["_id"] == "2021_DICIEMBRE.pdf")
    assert d["sha256"] and d["fecha_descarga"] and d["n_paginas"] > 10 and len(d["tabla_clientes_ventas"]) == 3
    assert len(mongo_store.documentos_manifiesto()) == 12


def test_mongo_fallback_explicito(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        r = mongo_store.guardar(BOL, MAN, fallback_dir=tmp_path)
    assert r["modo"] == "fallback_json" and "MODO FALLBACK: sin Mongo, guardado a JSON" in caplog.text
    assert json.loads((tmp_path / "mongo_fallback_manifiesto_ckan.json").read_text(encoding="utf-8")) == MAN


def test_mongo_estricto_falla(tmp_path, monkeypatch):
    monkeypatch.setenv("MONGO_STRICT", "1")
    with pytest.raises(RuntimeError, match="MongoDB no disponible"):
        mongo_store.guardar(BOL, MAN, fallback_dir=tmp_path)
    assert not list(tmp_path.glob("*.json"))


# ---------------- S3 (moto)
def test_s3_sin_bucket_se_omite(caplog):
    with caplog.at_level(logging.INFO):
        assert s3_publish.publicar(env={})["estado"] == "omitido"
    assert "S3 OMITIDO" in caplog.text


def test_s3_publica_con_moto(tmp_path, monkeypatch):
    # datos minimos: moto emula S3 en memoria (no es una cuenta AWS real)
    for sub, nombre in (("raw/ckan", "a.csv"), ("silver", "b.csv"), ("gold", "c.json")):
        (tmp_path / sub).mkdir(parents=True)
        (tmp_path / sub / nombre).write_text("x", encoding="utf-8")
    monkeypatch.setenv("SIG_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SIG_OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        boto3.client("s3").create_bucket(Bucket="sig-test")
        r = s3_publish.publicar(env={"S3_BUCKET": "sig-test"})
        keys = sorted(o["Key"].split("/", 2)[2] for o in boto3.client("s3").list_objects_v2(Bucket="sig-test")["Contents"])
    assert r["estado"] == "publicado" and keys == ["bronze/ckan/a.csv", "gold/c.json", "silver/b.csv"]
