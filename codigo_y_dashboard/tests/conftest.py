import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT.parent / "data"
sys.path.insert(0, str(ROOT))

VARS_EXTERNAS = ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "BEDROCK_MODEL_ID", "GENAI_MODE", "S3_BUCKET", "MONGO_STRICT",
                 "GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_MODEL", "GEMINI_BASE_URL", "OLLAMA_MODEL", "OLLAMA_HOST",
                 "SIG_LLM", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_PROFILE", "SIG_DATA_DIR", "SIG_OUT_DIR")


@pytest.fixture(autouse=True)
def _aislado(monkeypatch):
    """Ningun test usa claves reales, la red (SIG_OFFLINE=1) ni un MongoDB local real."""
    for v in VARS_EXTERNAS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("SIG_OFFLINE", "1")
    monkeypatch.setenv("MONGO_URI", "mongodb://127.0.0.1:1")
    monkeypatch.setenv("MONGO_TIMEOUT_MS", "300")


def copiar_bronze(destino):
    """Copia data/raw (bronze) y la cache de texto de los PDF a destino/data (sin silver/gold)."""
    shutil.copytree(DATA / "raw", destino / "data" / "raw")
    (destino / "data" / "interim").mkdir(parents=True)
    cache = DATA / "interim" / "textos_boletines.json"
    if cache.exists():
        shutil.copy2(cache, destino / "data" / "interim" / cache.name)
    return destino / "data"


def env_corrida(tmp):
    env = {k: v for k, v in os.environ.items() if k not in VARS_EXTERNAS}
    env.update(SIG_DATA_DIR=str(tmp / "data"), SIG_OUT_DIR=str(tmp / "out"), SIG_OFFLINE="1",
               MONGO_URI="mongodb://127.0.0.1:1", MONGO_TIMEOUT_MS="300", PYTHONIOENCODING="utf-8")
    return env


@pytest.fixture(scope="session")
def corrida(tmp_path_factory):
    """Una corrida completa del DAG (--run-local) sobre una copia del bronze; la usan varios tests."""
    tmp = tmp_path_factory.mktemp("corrida")
    copiar_bronze(tmp)
    p = subprocess.run([sys.executable, str(ROOT / "orquestacion_airflow_dag.py"), "--run-local"], capture_output=True,
                       text=True, env=env_corrida(tmp), encoding="utf-8")
    return {"proc": p, "data": tmp / "data", "out": tmp / "out", "silver": tmp / "data" / "silver",
            "gold": tmp / "data" / "gold"}


@pytest.fixture
def en_corrida(corrida, monkeypatch):
    """Apunta config a los datos de la corrida de sesion."""
    monkeypatch.setenv("SIG_DATA_DIR", str(corrida["data"]))
    monkeypatch.setenv("SIG_OUT_DIR", str(corrida["out"]))
    return corrida
