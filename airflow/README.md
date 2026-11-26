# Apache Airflow real (Docker) para el DAG del SIG ASEP

- **Airflow**: 2.10.5, imagen oficial `apache/airflow:2.10.5-python3.12` + dependencias de
  `../codigo_y_dashboard/requirements.txt` instaladas en la imagen (`Dockerfile`; imagen local `sig-asep-airflow:2.10.5`).
- **Modo**: `airflow standalone` (webserver + scheduler + triggerer, SequentialExecutor, metadata SQLite en el volumen `airflow-db`).
  Es para demo/aula, no para produccion (la UI muestra ese aviso).
- **DAG**: `dag_sig_distribuidoras_asep_mensual` (`../codigo_y_dashboard` se monta como carpeta de DAGs;
  `../codigo_y_dashboard/.airflowignore` excluye `tests/`). `../data` se monta en `/opt/airflow/data` (`SIG_DATA_DIR`).
  Las salidas (graficos, dashboard, data/silver, data/gold) se escriben en las carpetas reales del proyecto.
- **MongoDB**: el MongoDB 9.0.2 del host, via `mongodb://host.docker.internal:27017` (Docker Desktop reenvia el
  puerto aunque mongod escuche solo en 127.0.0.1; no se cambio su configuracion). `MONGO_STRICT=1` (falla si no hay Mongo,
  sin fallback JSON), `MONGO_DB=sig_distribuidoras`. Otro servidor: `MONGO_URI=... docker compose up -d`.
- **.env**: si existe `../codigo_y_dashboard/.env` (p. ej. `GEMINI_API_KEY`) se pasa al contenedor (`required: false`).
  Los servicios de MinIO **si** lo exigen (`MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`).

## MinIO local (almacenamiento S3 compatible; NO es Amazon AWS)

MinIO es un servidor de objetos con la misma API que Amazon S3, aqui corriendo en Docker en esta maquina. La tarea
`publicar_s3_opcional` sube a MinIO con boto3 exactamente como lo haria a S3, pero **no hay cuenta AWS, costo ni datos fuera
del equipo**. El resultado de la tarea lo dice: `modo = "S3 compatible (MinIO local)"`.

- Imagen: `pgsty/minio:RELEASE.2026-08-04T00-00-00Z` y cliente `pgsty/mc:RELEASE.2026-09-16T00-00-00Z`, un **fork comunitario no oficial**:
  el repositorio oficial `minio/minio` (y `minio/mc`) ya no existe en Docker Hub (verificado el 2026-11-26). Su consola se rotula «SILO».
- Servicios: `minio` (API `127.0.0.1:9100`, consola web `127.0.0.1:9101`, volumen `minio-data`, healthcheck `mc ready local`)
  y `minio-init` (crea el bucket `sig-distribuidoras-asep` con `mc mb --ignore-existing`: idempotente). Airflow arranca solo
  cuando MinIO esta sano y el bucket existe. Dentro de compose, Airflow usa `AWS_ENDPOINT_URL=http://minio:9000`.
- Credenciales: locales y aleatorias, solo en `../codigo_y_dashboard/.env` (en `.gitignore`); nunca en este README ni en `evidencia/`.
- Entrar a la consola: http://127.0.0.1:9101 con `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` del `.env`.
- Objetos: `s3://sig-distribuidoras-asep/sig-distribuidoras-asep/<AAAA-MM-DD>/gold/...` y `.../dashboard/dashboard_interactivo.html`.

**Estado (2026-11-26): publicacion real verificada.** La tarea `publicar_s3_opcional` subio 10 objetos (gold/*.json, *.csv,
sig_distribuidoras.db y dashboard_interactivo.html) bajo `sig-distribuidoras-asep/2026-11-26/`, desde el host y desde Airflow
(run `manual__2026-11-26T22:36:59+00:00`), rotulados `S3 compatible (MinIO local)`. Evidencia: `evidencia/log_tarea_publicar_s3_minio.log`
y `evidencia/captura_minio_bucket.png`. Riesgo: dependencia de un fork comunitario; alternativa: otra imagen o Amazon S3 (el codigo lo admite).

## Levantar

```powershell
cd airflow
docker compose up -d --build      # primera vez ~2.5 GB de imagen; luego basta docker compose up -d
docker compose ps                 # esperar STATUS "healthy" (~1 min)
```

## Entrar a la UI

http://localhost:8080 (solo localhost). Usuario `admin`; la contrasena la genera standalone **dentro del contenedor**:

```powershell
docker compose exec airflow cat /opt/airflow/standalone_admin_password.txt
```

Si el archivo no existe (contenedor recreado con la base ya creada), fijar una propia sin guardarla en archivos:

```powershell
docker compose exec airflow airflow users reset-password -u admin -p "<tu-clave>"
```

## Disparar el DAG

```powershell
docker compose exec airflow airflow dags list-import-errors        # debe decir "No data found"
docker compose exec airflow airflow dags unpause dag_sig_distribuidoras_asep_mensual
docker compose exec airflow airflow dags trigger dag_sig_distribuidoras_asep_mensual
docker compose exec airflow airflow dags list-runs -d dag_sig_distribuidoras_asep_mensual
docker compose exec airflow airflow tasks states-for-dag-run dag_sig_distribuidoras_asep_mensual "<run_id>"
```

Nota: al despausar, el scheduler crea ademas el run programado del ultimo intervalo (`catchup=False`).

## Apagar

```powershell
docker compose down            # conserva los volumenes airflow-db (historial de runs) y minio-data (objetos)
docker compose down -v         # ademas borra la metadata de Airflow y los objetos de MinIO (no toca MongoDB ni data/)
```

## Evidencia

`evidencia/` (2026-11-26): 3 runs exitosos con 9/9 tareas en success: `scheduled__2026-10-20T11:00:00+00:00`,
`manual__2026-11-26T22:17:34+00:00` y `manual__2026-11-26T22:36:59+00:00` (este ultimo, ~80 s, con publicacion en MinIO:
`tasks_states_run_minio.txt`, `dags_list_runs_minio.txt`, `log_tarea_publicar_s3_minio.log`). Ademas: estados y duraciones,
logs de tareas clave, conteos de MongoDB 9.0.2 antes/despues (162 documentos en `boletines_asep`, 12 en `manifiesto_ckan`),
capturas de la UI de Airflow (`captura_airflow_lista_dags.png`, `captura_airflow_grid.png`, `captura_airflow_graph_run_manual.png`;
tomadas a las 22:22 UTC, antes del tercer run) y de la consola de MinIO (`captura_minio_bucket.png`). El diagnostico de IA de la
corrida final lo genero Google Gemini (`gemini-3.5-flash-lite`); la clave solo vive en `../codigo_y_dashboard/.env`.
