import importlib
import json
import sys
import types

import genai_diagnostico as gd
import orquestacion_airflow_dag as dag


# ---------------- DAG
def test_run_local_punta_a_punta(corrida):
    p = corrida["proc"]
    assert p.returncode == 0, p.stderr[-3000:]
    for tid in dag.TAREAS:
        assert f"OK {tid}" in p.stderr
    assert "MODO FALLBACK: sin Mongo, guardado a JSON" in p.stderr and "S3 OMITIDO" in p.stderr
    assert "SIN RED" in p.stderr  # SIG_OFFLINE=1: CKAN desde la copia local, con aviso
    g, out = corrida["gold"], corrida["out"]
    for f in ("sig_distribuidoras.db", "kpi_summary.json", "calidad_auditoria.json", "lmdi_descomposicion.csv",
              "diagnostico_ia.json", "mongo_fallback_boletines_asep.json", "mongo_fallback_manifiesto_ckan.json"):
        assert (g / f).exists(), f
    assert len(list((out / "graficos").glob("*.png"))) == 6
    html = (out / "dashboard_interactivo.html").read_text(encoding="utf-8")
    assert "const D=/*__DATOS__*/null" not in html and "EDECHI" in html and "modo offline (plantilla)" in html


def test_orden_topologico_respeta_dependencias():
    orden = dag.orden_topologico()
    for tid, (_, deps) in dag.TAREAS.items():
        assert all(orden.index(d) < orden.index(tid) for d in deps)


def test_run_local_se_detiene_en_la_primera_falla():
    llamadas = []

    def mal():
        raise RuntimeError("boom")

    t = {"a": (lambda: llamadas.append("a"), []), "b": (mal, ["a"]), "c": (lambda: llamadas.append("c"), ["b"])}
    assert dag.run_local(t) == 1 and llamadas == ["a"]


def test_dag_airflow_con_modulo_falso_cablea_dependencias(monkeypatch):
    # airflow FALSO: solo prueba que el DAG se arma con las mismas dependencias; no es Airflow real
    deps = []

    class Op:
        def __init__(self, task_id, python_callable):
            self.task_id = task_id

        def __rshift__(self, o):
            deps.append((self.task_id, o.task_id))
            return o

    class DAG:
        def __init__(self, **kw):
            self.kw = kw

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    af = types.ModuleType("airflow")
    af.DAG = DAG
    py = types.ModuleType("airflow.operators.python")
    py.PythonOperator = Op
    monkeypatch.setitem(sys.modules, "airflow", af)
    monkeypatch.setitem(sys.modules, "airflow.operators", types.ModuleType("airflow.operators"))
    monkeypatch.setitem(sys.modules, "airflow.operators.python", py)
    monkeypatch.setitem(sys.modules, "airflow.providers", None)
    m = importlib.reload(dag)
    try:
        assert m.dag.kw["dag_id"] == "dag_sig_distribuidoras_asep_mensual"
        assert set(deps) == {(d, t) for t, (_, ds) in m.TAREAS.items() for d in ds}
    finally:
        monkeypatch.undo()
        importlib.reload(dag)


# ---------------- IA generativa
def _resumen(corrida):
    s = json.loads((corrida["gold"] / "kpi_summary.json").read_text(encoding="utf-8"))
    s.pop("diagnostico_ia", None)
    return s


def test_ia_offline_por_defecto_usa_cifras_del_contexto(corrida):
    s = _resumen(corrida)
    d = gd.generar_diagnostico_gerencial(s, env={})
    assert d["modo"] == "offline" and d["etiqueta"] == "modo offline (plantilla)"
    assert s["respuesta"]["texto"] in d["texto"] and d["texto"].count("\n- ") >= 3
    ctx = gd.construir_contexto(s)
    assert "LMDI" in ctx and "EDECHI" in ctx


def test_ia_proveedor_fallido_cae_a_plantilla_con_error(corrida):
    d = gd.generar_diagnostico_gerencial(_resumen(corrida), env={"SIG_LLM": "gemini"})  # sin clave
    assert d["modo"] == "offline" and "gemini" in d["error"] and d["texto"]
