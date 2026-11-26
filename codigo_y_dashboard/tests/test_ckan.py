"""CSV del portal CKAN y manifiesto JSON (sin red: respuestas simuladas)."""
import io
import json
import logging

import pytest

import ckan_client
import config

CSV_2021 = ("Mes;Empresa de Distribuci\xf3n El?ctrica Metro Oeste, S.A;Elektra Noreste, S.A.;"
            "Empresa de Distribuci\xf3n El?ctrica Chiriqu\xed, S.A;Liberty Services Corp.,\r\n"
            "Enero;112;92;21;0\r\nFebrero;163;92;36;0\r\nProvincia;a;b;c;d\r\nPanama;570;1096;0;0\r\n").encode("cp1252")
CSV_2025 = (b"Mes;Empresa de Distribucion Electrica Metro Oeste, S.A;Elektra Noreste, S.A.;"
            b"Empresa de Distribucion Electrica Chiriqui, S.A\r\nEnero;313;265;52\r\nNoviembre;326;167;35\r\n")
SECTOR = b"Mes;Electricidad;Agua;Telecomunicaciones\r\nEnero;225;23;17\r\nFebrero;291;24;26\r\n"


def test_parse_csv_2021_cp1252_con_liberty_y_bloque_provincia(tmp_path):
    p = tmp_path / "x.csv"
    p.write_bytes(CSV_2021)
    f = ckan_client.parse_reclamos_distribuidora(p, 2021)
    assert len(f) == 8 and {x["distribuidora"] for x in f} == {"EDEMET", "ENSA", "EDECHI", "OTRA_LIBERTY"}
    assert next(x for x in f if x["mes"] == 2 and x["distribuidora"] == "EDECHI")["reclamos"] == 36
    assert f[0]["codificacion"] == "cp1252"


def test_parse_csv_2025_utf8_y_sector(tmp_path):
    (tmp_path / "a.csv").write_bytes(CSV_2025)
    (tmp_path / "s.csv").write_bytes(SECTOR)
    f = ckan_client.parse_reclamos_distribuidora(tmp_path / "a.csv", 2025)
    assert {(x["periodo"], x["distribuidora"]): x["reclamos"] for x in f}[("2025-11", "ENSA")] == 167
    s = ckan_client.parse_reclamos_sector(tmp_path / "s.csv", 2021)
    assert len(s) == 6 and s[0]["sector"] == "Electricidad" and s[0]["reclamos"] == 225


def _paquete(titulo, recursos, org=ckan_client.ORG_ASEP):
    return {"id": titulo, "name": titulo.lower().replace(" ", "-"), "title": titulo, "organization": {"name": org},
            "resources": recursos}


def test_elegir_recursos_del_manifiesto():
    paq = [_paquete("ASEP - Estadisticas de Reclamos de Electricidad 2025", [
               {"id": "r1", "name": "Reclamos de Electricidad 2025.csv", "format": "CSV", "url": "u1", "last_modified": "2025-12-16"},
               {"id": "r2", "name": "Reclamos de Electricidad 2025.pdf", "format": "PDF", "url": "u2", "last_modified": "2025-12-16"}]),
           _paquete("ASEP - Estadisticas de Reclamos Admitidos por Sector 2023", [
               {"id": "a", "name": "Reclamos Admitidos por Sector 2023", "format": "CSV", "url": "ua", "last_modified": "2024-01-08"},
               {"id": "b", "name": "Reclamos Admitidos por Sector 2023", "format": "CSV", "url": "ub", "last_modified": "2023-09-20"}]),
           _paquete("Metro de Panama", [{"id": "m", "name": "2023", "format": "CSV", "url": "um"}]),
           _paquete("ASEP - Estadisticas de Reclamos de Electricidad 2024", [
               {"id": "z", "name": "x 2024", "format": "CSV", "url": "uz"}], org="otra")]
    r = ckan_client.elegir_recursos(paq)
    assert [(x["tipo"], x["anio"], x["resource_id"]) for x in r] == [("reclamos_electricidad", 2025, "r1"),
                                                                       ("reclamos_sector", 2023, "a")]
    assert r[0]["archivo"] == "reclamos_electricidad_2025.csv"


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_sincronizar_descarga_guarda_manifiesto_y_no_repite(tmp_path, monkeypatch):
    monkeypatch.setenv("SIG_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SIG_OFFLINE")
    paq = _paquete("ASEP - Estadisticas de Reclamos de Electricidad 2025", [
        {"id": "r1", "name": "Reclamos de Electricidad 2025.csv", "format": "CSV", "url": "https://x/r.csv", "last_modified": "2025-12-16"}])
    llamadas = []

    def falso_urlopen(req, timeout=None):
        url = req.full_url
        llamadas.append(url)
        if "package_search" in url:
            return _Resp(json.dumps({"success": True, "result": {"count": 1, "results": [paq]}}).encode())
        if "resource_show" in url:
            return _Resp(json.dumps({"success": True, "result": {"id": "r1", "last_modified": "2025-12-16T19:35:15"}}).encode())
        return _Resp(CSV_2025)

    monkeypatch.setattr(ckan_client.urllib.request, "urlopen", falso_urlopen)
    r = ckan_client.sincronizar()
    assert r["modo"] == "red" and r["nuevos"] == 1
    man = json.loads(next(config.ckan_dir().glob("manifiesto_ckan_*.json")).read_text(encoding="utf-8"))
    assert man["resource_show"]["r1"]["last_modified"] == "2025-12-16T19:35:15"
    assert (config.ckan_dir() / "reclamos_electricidad_2025.csv").read_bytes() == CSV_2025
    reg = json.loads((config.ckan_dir() / "_descargas.json").read_text(encoding="utf-8"))
    assert reg["reclamos_electricidad_2025.csv"]["fecha_descarga"] and reg["reclamos_electricidad_2025.csv"]["sha256"]
    assert ckan_client.sincronizar()["nuevos"] == 0  # mismo last_modified: no se vuelve a descargar
    assert sum("r.csv" in u for u in llamadas) == 1


def test_sin_red_usa_copia_local_y_avisa(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("SIG_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SIG_OFFLINE")
    d = tmp_path / "raw" / "ckan"
    d.mkdir(parents=True)
    (d / "manifiesto_ckan_2026-11-25.json").write_text("{}", encoding="utf-8")
    (d / "_descargas.json").write_text(json.dumps({"a.csv": {"archivo": "a.csv", "tipo": "reclamos_electricidad", "anio": 2025}}),
                                       encoding="utf-8")

    def sin_red(*a, **k):
        raise OSError("red caida")

    monkeypatch.setattr(ckan_client.urllib.request, "urlopen", sin_red)
    with caplog.at_level(logging.WARNING):
        r = ckan_client.sincronizar()
    assert r["modo"] == "copia_local" and "SIN RED" in caplog.text and len(r["recursos"]) == 1


def test_sin_red_y_sin_copia_falla(tmp_path, monkeypatch):
    monkeypatch.setenv("SIG_DATA_DIR", str(tmp_path))
    with pytest.raises(RuntimeError, match="no hay copia local"):
        ckan_client.sincronizar()


def test_cruce_reclamos_en_corrida_real(corrida):
    aud = json.loads((corrida["silver"] / "auditoria_ckan.json").read_text(encoding="utf-8"))
    assert aud["modo"] == "copia_local" and len(aud["archivos"]) == 12
    assert aud["cruce_suma_distribuidoras_vs_sector_electricidad"]["meses_comparados"] >= 59
