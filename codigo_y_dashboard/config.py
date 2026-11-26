"""Rutas y parametros del SIG de distribuidoras (ASEP). Todo relativo a este archivo; sobreescribible por entorno.

SIG_DATA_DIR : carpeta con raw (bronze) / interim / silver / gold (defecto: ../data, junto a esta carpeta)
SIG_OUT_DIR  : carpeta donde se escriben graficos/ y dashboard_interactivo.html (defecto: esta carpeta)
SIG_OFFLINE=1: no usa la red (CKAN y boletines se leen de la copia en data/raw y se avisa en el log)
SIG_DOTENV=0 : no carga el .env local (lo usan las corridas de prueba en subproceso)
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def cargar_env(ruta: Path = BASE_DIR / ".env", forzar: bool = False) -> list:
    """Carga KEY=VALOR de un .env local (ignorado por git) sin pisar variables ya definidas.

    Devuelve solo los NOMBRES cargados (nunca los valores). No se carga durante pytest,
    para que las pruebas no usen claves reales, salvo que se pida con forzar=True."""
    if not forzar and ("pytest" in sys.modules or os.environ.get("SIG_DOTENV") == "0"):
        return []
    if not ruta.is_file():
        return []
    cargadas = []
    for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave, valor = clave.strip(), valor.strip().strip('"').strip("'")
        if clave and valor and clave not in os.environ:
            os.environ[clave] = valor
            cargadas.append(clave)
    return cargadas


ENV_CARGADAS = cargar_env()

DISTRIBUIDORAS = ("EDEMET", "ENSA", "EDECHI")
NOMBRES_LEGALES = {
    "EDEMET": "Empresa de Distribucion Electrica Metro-Oeste, S.A.",
    "ENSA": "Elektra Noreste, S.A. (ENSA)",
    "EDECHI": "Empresa de Distribucion Electrica Chiriqui, S.A.",
}
ZONAS = {"EDEMET": "Panama Oeste, oeste de la ciudad, Cocle, Veraguas, Herrera, Los Santos",
         "ENSA": "Este de la ciudad de Panama, Colon, Darien, Guna Yala",
         "EDECHI": "Chiriqui y Bocas del Toro"}
MESES = ("ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO",
         "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE")

# Periodo de analisis: anios completos. 2026 (parcial) solo para la vista mensual reciente.
ANIO_INICIO, ANIO_FIN = 2014, 2025
FECHA_CONSULTA = "2026-11-25"

# Fuentes
URL_BOLETIN = "https://asep.gob.pa/wp-content/uploads/electricidad/estadisticas_mensuales/{anio}/{mes}_{anio}.pdf"
BOLETIN_DESDE, BOLETIN_HASTA = (2013, 4), (2026, 9)  # rango esperado de boletines (no se buscan meses nuevos)
CKAN_BASE = "https://www.datosabiertos.gob.pa"
CKAN_CONSULTAS = ("reclamos electricidad", "reclamos admitidos por sector")


def data_dir() -> Path:
    return Path(os.environ.get("SIG_DATA_DIR") or BASE_DIR.parent / "data")


def raw_dir() -> Path:  # capa bronze: archivos tal como se descargaron
    return data_dir() / "raw"


def boletines_dir() -> Path:
    return raw_dir() / "boletines_asep"


def ckan_dir() -> Path:
    return raw_dir() / "ckan"


def interim_dir() -> Path:
    return data_dir() / "interim"


def silver_dir() -> Path:
    return data_dir() / "silver"


def gold_dir() -> Path:
    return data_dir() / "gold"


def out_dir() -> Path:
    return Path(os.environ.get("SIG_OUT_DIR") or BASE_DIR)


def db_path() -> Path:
    return gold_dir() / "sig_distribuidoras.db"


def offline() -> bool:
    return os.environ.get("SIG_OFFLINE") == "1"
