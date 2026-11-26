"""
DAG de orquestacion (Apache Airflow) del SIG de distribuidoras electricas de Panama (ASEP).

Cada tarea ejecuta codigo real; los datos pasan entre tareas por archivos (data/raw -> silver -> gold), no por XCom.
  descubrir_descargar_ckan : API CKAN (JSON) -> manifiesto + descarga automatica de CSV de reclamos
  extraer_pdf_boletines    : inventario de PDF (descarga solo faltantes) -> texto (cache) -> tabla por boletin
  limpiar_calidad          : reglas de calidad + imputacion -> silver/mercado_mensual.csv + gold/calidad_auditoria.json
  cargar_sql               : SQLite en estrella;  cargar_mongodb : documentos por boletin + manifiesto (fallback JSON)
  gold_kpis_lmdi           : KPIs, LMDI, estacionalidad, reclamos -> kpi_summary.json (+ fact_descomposicion)
  diagnostico_ia           : IA generativa (offline por defecto);  dashboard_y_figuras ; publicar_s3_opcional

  Con Airflow instalado : define el DAG `dag_sig_distribuidoras_asep_mensual` (PythonOperator).
  Sin Airflow           : python orquestacion_airflow_dag.py --run-local   (sale con codigo != 0 si una tarea falla)
"""
import logging
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # Airflow no siempre agrega la carpeta del DAG

import config  # noqa: E402,F401
import generar_dashboard_y_graficos as dash  # noqa: E402
import genai_diagnostico  # noqa: E402
import mongo_store  # noqa: E402
import pipeline_etl as etl  # noqa: E402
import s3_publish  # noqa: E402

log = logging.getLogger("dag")


# ---------------------------------------------------------------- tareas
# task_id -> (callable, dependencias)
TAREAS = {
    "descubrir_descargar_ckan": (etl.extraer_ckan, []),
    "extraer_pdf_boletines": (etl.extraer_pdf, []),
    "limpiar_calidad": (etl.limpiar, ["descubrir_descargar_ckan", "extraer_pdf_boletines"]),
    "cargar_sql": (etl.cargar_sqlite, ["limpiar_calidad"]),
    "cargar_mongodb": (lambda: mongo_store.guardar(), ["limpiar_calidad"]),
    "gold_kpis_lmdi": (etl.construir_gold, ["cargar_sql"]),
    "diagnostico_ia": (genai_diagnostico.ejecutar, ["gold_kpis_lmdi"]),
    "dashboard_y_figuras": (dash.main, ["diagnostico_ia"]),
    "publicar_s3_opcional": (s3_publish.publicar, ["cargar_mongodb", "dashboard_y_figuras"]),
}


def orden_topologico(tareas=None):
    tareas = tareas or TAREAS
    orden, hechas = [], set()
    while len(orden) < len(tareas):
        listas = [t for t, (_, deps) in tareas.items() if t not in hechas and all(d in hechas for d in deps)]
        if not listas:
            raise ValueError("Dependencias ciclicas en TAREAS")
        orden += listas
        hechas.update(listas)
    return orden


def run_local(tareas=None):
    """Ejecuta las tareas en orden. Devuelve 0 si todas OK, 1 si alguna falla (se detiene)."""
    tareas = tareas or TAREAS
    for tid in orden_topologico(tareas):
        t0 = time.time()
        try:
            res = tareas[tid][0]()
        except Exception:
            log.error("TAREA FALLIDA: %s\n%s", tid, traceback.format_exc())
            return 1
        log.info("OK %-30s %.1fs -> %s", tid, time.time() - t0, res)
    return 0


# ---------------------------------------------------------------- DAG real (solo si Airflow esta instalado)
try:
    from airflow import DAG
    try:
        from airflow.providers.standard.operators.python import PythonOperator  # Airflow 3
    except ImportError:
        from airflow.operators.python import PythonOperator  # Airflow 2
except ImportError:
    dag = None
else:
    with DAG(
        dag_id="dag_sig_distribuidoras_asep_mensual",
        default_args={"owner": "direccion_tecnologia", "retries": 2, "retry_delay": timedelta(minutes=5)},
        description="ASEP: CKAN (JSON/CSV) + boletines PDF -> calidad -> SQLite/MongoDB -> KPIs/LMDI -> IA -> dashboard -> S3 opcional",
        schedule="0 6 20 * *",  # mensual (supuesto: el boletin del mes anterior ya esta publicado el dia 20)
        start_date=datetime(2025, 1, 1, tzinfo=timezone(timedelta(hours=-5))),
        catchup=False,
        tags=["SIG", "Energia", "ASEP"],
    ) as dag:
        _ops = {tid: PythonOperator(task_id=tid, python_callable=fn) for tid, (fn, _) in TAREAS.items()}
        for tid, (_, deps) in TAREAS.items():
            for d in deps:
                _ops[d] >> _ops[tid]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if "--run-local" in sys.argv:
        sys.exit(run_local())
    print(__doc__)
    sys.exit(2)
