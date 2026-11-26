# SIG del crecimiento del consumo eléctrico por distribuidora (Panamá)

Proyecto final de **Sistemas de Información Gerencial** (UTP, FISC). Caso: unidad de análisis de la ASEP (roles asumidos por simulación académica).

**Pregunta gerencial:** ¿en qué distribuidora eléctrica de Panamá está creciendo más el consumo, y cuánto de ese crecimiento se explica por más clientes o por mayor consumo por cliente?

> **Datos públicos reales** de la ASEP, consultados el 2026-11-25: 162 boletines mensuales (abril 2013 – septiembre 2026) y datos abiertos de reclamos. Los valores con errores u omisiones de la fuente se marcan e imputan conservando el original (ver la pestaña *Calidad de datos* del dashboard y `data/VERIFICACION_BOLETINES.md`).

## Contenido

| Ruta | Qué contiene |
|---|---|
| `codigo_y_dashboard/` | Pipeline (PDF + CSV + JSON de la API CKAN), calidad de datos, SQLite en estrella, MongoDB (con fallback), descomposición LMDI, DAG ejecutable, diagnóstico IA opcional, `dashboard_interactivo.html` y pruebas. **Instrucciones en su `README.md`.** |
| `data/raw/` | Boletines PDF de ASEP (con inventario sha256 y fecha de descarga) y CSV/JSON del portal de datos abiertos. |
| `data/silver/`, `data/gold/` | Datos limpios, KPIs, descomposición y auditoría de calidad. |
| `presentacion/` | Presentación grupal (sin cédulas). |

## Inicio rápido

```bash
cd codigo_y_dashboard
pip install -r requirements.txt
python orquestacion_airflow_dag.py --run-local   # pipeline completo
python -m pytest -q                              # pruebas
```

Abrir `codigo_y_dashboard/dashboard_interactivo.html` en el navegador (funciona sin conexión).

Fuentes: ASEP, *Estadística del Mercado Eléctrico Panameño* (boletines mensuales); Portal de Datos Abiertos de Panamá (conjuntos de reclamos de electricidad de la ASEP, licencia indicada en el manifiesto CKAN).
