# Airflow oficial con las dependencias del proyecto horneadas en la imagen.
ARG AIRFLOW_VERSION=2.10.5
FROM apache/airflow:${AIRFLOW_VERSION}-python3.12
ARG AIRFLOW_VERSION

# Se fija apache-airflow en el mismo pip install para que ninguna dependencia lo actualice/rompa.
COPY --from=codigo requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /tmp/requirements.txt

# Carpeta para la metadata SQLite (volumen con nombre, propiedad del usuario airflow).
USER root
RUN mkdir -p /opt/airflow/db && chown airflow:root /opt/airflow/db
USER airflow
