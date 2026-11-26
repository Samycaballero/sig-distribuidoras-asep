# SIG de distribuidoras eléctricas de Panamá (ASEP)

Proyecto Final de **Sistemas de Información Gerencial** — Universidad Tecnológica de Panamá. Sector Energía.

**Pregunta gerencial:** ¿En qué distribuidora eléctrica de Panamá está creciendo más el consumo, y cuánto de ese crecimiento se explica por más clientes o por mayor consumo por cliente?

## Fuentes (tres tipos de datos reales; fecha de consulta: 2026-11-25)

| Tipo | Fuente | Qué se usa | URL |
|---|---|---|---|
| **PDF** | ASEP, *Estadística del Mercado Eléctrico Panameño* (boletín mensual), 162 boletines abr-2013 a sep-2026 | clientes, ventas (kWh) y facturación/ingresos de EDEMET, ENSA y EDECHI; demanda máxima mensual del sistema | `https://asep.gob.pa/wp-content/uploads/electricidad/estadisticas_mensuales/{AÑO}/{MES}_{AÑO}.pdf` |
| **CSV** | Portal de datos abiertos (CKAN): «ASEP - Estadísticas de Reclamos de Electricidad AAAA» (2021–2026) y «Reclamos Admitidos por Sector» | reclamos de electricidad por distribuidora y mes; reclamos por sector (Electricidad/Agua/Telecom) | https://www.datosabiertos.gob.pa (p. ej. `.../dataset/8da3e355-4cb2-44ce-a75c-18381f9c52a7/resource/44d2b75a-d0fd-411b-a154-47afe0325600/download/reclamos-de-electricidad-2025.csv`) |
| **JSON** | API CKAN del mismo portal (`package_search`, `resource_show`) | catálogo/manifiesto: el pipeline descubre y descarga los CSV automáticamente y guarda la fecha de actualización de cada recurso | `https://www.datosabiertos.gob.pa/api/3/action/package_search?q=reclamos%20electricidad&rows=50` |

Todo lo descargado queda en `../data/raw` (bronze) con su fecha de descarga y sha256: `boletines_asep/_inventario.json` (los PDF no se vuelven a descargar si ya están) y `ckan/_descargas.json` + `ckan/manifiesto_ckan_AAAA-MM-DD.json`. Últimas actualizaciones de los CSV según la API: 2025 → 2025-12-16 (enero–noviembre), 2026 → 2026-02-10 (solo enero).

## Arquitectura (bronze → silver → gold)

| Módulo | Función |
|---|---|
| `config.py` | rutas (`SIG_DATA_DIR`, `SIG_OUT_DIR`), periodo base 2014–2025, `SIG_OFFLINE=1` |
| `ckan_client.py` | API CKAN (JSON) → manifiesto → descarga de CSV solo si cambió `last_modified`; sin red usa la copia local con `WARNING SIN RED` |
| `extraer_boletines.py` | inventario PDF, texto con pypdf (caché por sha256 en `data/interim/textos_boletines.json`), tabla por boletín, unidades por magnitud, demanda máxima |
| `calidad.py` | reglas de calidad + imputación → `silver/mercado_mensual.csv` y `gold/calidad_auditoria.json` |
| `analisis.py` | KPIs anuales, LMDI, estacionalidad, reclamos por 10.000 clientes, vista 2026, `gold/kpi_summary.json` |
| `pipeline_etl.py` | pasos ETL y **SQLite en estrella** `gold/sig_distribuidoras.db`: `dim_distribuidora`, `dim_tiempo`, `fact_mercado_mensual`, `fact_reclamos_mensual`, `fact_reclamos_sector_mensual`, `fact_demanda_maxima_mensual`, `fact_descomposicion`, vistas `vw_bi_kpi_anual`, `vw_bi_descomposicion`, `vw_bi_reclamos_vs_ventas`, `vw_bi_calidad` |
| `mongo_store.py` | **MongoDB**: colección `boletines_asep` (un documento por PDF con texto por página, tabla, sha256, fecha de descarga) y `manifiesto_ckan`; sin servidor → `MODO FALLBACK: sin Mongo, guardado a JSON` |
| `genai_diagnostico.py` | **IA generativa** (Anthropic / Gemini / Ollama / Bedrock / offline); contexto = KPIs + LMDI + hallazgos + advertencias; offline por defecto |
| `generar_dashboard_y_graficos.py` + `dashboard_template.html` | `dashboard_interactivo.html` autocontenido y sin conexión (filtros por distribuidora, años y métrica; tarjetas KPI y cascada LMDI recalculadas; meses imputados marcados con valor original y motivo; estacionalidad, participación, reclamos vs. ventas; pestaña «Calidad de datos» filtrable; `?tema=claro|oscuro`) y 6 figuras PNG a 300 dpi en `graficos/`: fig1 arquitectura, fig2 ventas anuales, fig3 LMDI 2014→2025 y 2021→2025, fig4 kWh/cliente/mes con imputaciones, fig5 reclamos vs. ventas, fig6 captura del dashboard (Chrome/Edge sin interfaz; si no hay navegador, maqueta) |
| `s3_publish.py` | **AWS S3** opcional (solo con `S3_BUCKET` + credenciales) |
| `orquestacion_airflow_dag.py` | **orquestación**: DAG Airflow `dag_sig_distribuidoras_asep_mensual`; sin Airflow `--run-local` |

Tareas del DAG: `descubrir_descargar_ckan`, `extraer_pdf_boletines` → `limpiar_calidad` → `cargar_sql`, `cargar_mongodb` → `gold_kpis_lmdi` → `diagnostico_ia` → `dashboard_y_figuras` → `publicar_s3_opcional`.

## Cómo reproducir

```bash
python -m pip install -r requirements.txt
# corrida completa (sin LLM, sin tocar un MongoDB local real):
set MONGO_URI=mongodb://localhost:1/?serverSelectionTimeoutMS=500
python orquestacion_airflow_dag.py --run-local     # exit 0
python -m pytest -q                               # tests (sin red, sin Mongo real)
```
La primera extracción de texto de los 162 PDF tarda ~3 min; después se usa la caché. `SIG_OFFLINE=1` ejecuta todo sin red.

## Política de calidad (auditada en `gold/calidad_auditoria.json`)

- **Nada se borra sin rastro.** Cada fila de `fact_mercado_mensual` guarda el valor de la fuente (`*_fuente`), el valor final, las reglas que lo marcaron (`*_flags`) y el método de imputación (`*_imputacion`).
- **Valores erróneos o no reportados se marcan y se imputan solo para el análisis:** clientes por interpolación lineal; ventas por interpolación de kWh/cliente/mes × clientes; facturación por interpolación de US$/kWh × ventas.
- **Saltos persistentes no se corrigen:** se marcan como `cambio_de_nivel` (posible cambio de definición/cobertura).
- Reglas: R1 faltante; R2 **arrastre** (valor idéntico al del mes anterior: la distribuidora no reportó y el boletín repite la cifra); R3 atípico puntual (se aleja de la mediana de los 2 meses previos **y** de los 2 posteriores: clientes 3 %, ventas 20 %, US$/kWh 30 %); R4 kWh/cliente fuera de [0,6; 1,6] × mediana de la distribuidora; R5 salto m/m (clientes > 3 %, ventas > 20 %) clasificado en atípico / cambio de nivel / no persistente. Nivel boletín: total publicado ≠ suma, etiqueta de mes distinta, tabla en imagen, sección ausente, transcripción manual.
- **Unidades y monedas:** la unidad del encabezado no es fiable (dice «(MWh)» o «Millones de Balboas» con cifras en kWh y balboas). Se infiere por magnitud (100–3.000 kWh/cliente/mes; 0,05–0,50 US$/kWh) y se registra el factor por valor. B/. y US$ están a la par (1:1), no se convierte.

### Meses con observaciones y cómo se resolvieron

| Mes | Problema | Origen | Resolución |
|---|---|---|---|
| 2013-04 | texto de la pág. 12 sale fragmentado | lector (texto superpuesto en el PDF) | transcripción manual en el código; se acepta solo porque las 3 empresas suman exactamente el total publicado |
| 2014-03 | el boletín (12 págs.) no trae la sección de clientes | fuente | irrecuperable; imputado |
| 2015-05, 2015-06 | sección presente pero tabla como imagen (sin texto) | fuente | irrecuperable sin OCR; imputado |
| 2016-10, 2016-11 | el lector anterior tomaba la tabla de costos | lector | **corregido** (búsqueda del bloque completo EDEMET/ENSA/EDECHI/TOTAL) |
| 2016-01, 2015-06*, 2019-12, 2019-01 | tabla sin título / empresas no leídas | lector | **corregido** (*2015-06 es imagen) |
| 2017-11, 2017-12 | total publicado no cuadra (2017-12 repite el total de 2017-11; EDEMET 2017-11 escrito «342,351.597» en MWh) | fuente | total no se usa; valores por empresa evaluados con R2–R4 y unidad inferida |
| 2018-05 | ENSA facturación «54,128.000.00»; EDEMET repite abril; total no cuadra | fuente | número reinterpretado (54.128.000,00, validado por US$/kWh); EDEMET imputado (arrastre) |
| 2019-01 | ENSA facturación «57,135.000.00»; EDEMET repite dic-2018; total de facturación erróneo | fuente | igual que 2018-05 |
| 2021-10 | EDEMET ventas 828.014.691 kWh (≈3× lo normal); ENSA «249,949» y facturación «39,819» (MWh y miles de US$) | fuente | EDEMET: atípico + fuera de banda → imputado 276,8 GWh (original conservado). ENSA: unidad mixta → ×1000 (249,9 GWh; 39,8 M US$), conservado y marcado |
| varios (52 clientes / 49 ventas / 52 facturación) | arrastres: el boletín repite la cifra del mes anterior (p. ej. 2014-04/05 = 2014-02; 2015-11 = 2015-10; ENSA ventas 2021-03 = 2021-02; ENSA 2025-03/04 = 2025-02) | fuente | imputados |
| 2025-02 EDECHI | clientes −3,2 % y vuelve | fuente | atípico puntual → imputado |
| 2017-06, 2019-12, 2020-03 | la tabla dice otro mes (MAYO / NOVIEMBRE / FEBRERO) | fuente | informativo; 2019-12 trae cifras nuevas (se usa el mes del boletín); 2020-03 repite feb (arrastre → imputado) |

Resultado: 67 filas distribuidora-mes de 2014–2025 (de 432) tienen al menos una variable imputada (182 valores; `vw_bi_calidad`, pestaña «Calidad de datos» del dashboard, figura 4). En CKAN, la suma por distribuidora no coincide con el total «Electricidad» del CSV por sector en 8 meses de 2023 (p. ej. sep-2023: 852 vs 549): se documenta y se usa el CSV por distribuidora.

### Cambios de definición revisados

- Concepto monetario: «INGRESOS» hasta 2020-04 → «FACTURADO»/«FACTURACIÓN» desde 2020-05. El ingreso medio US$/kWh se presenta con advertencia (no es una tarifa).
- Moneda declarada alterna B/. / US$ (2015-07, 2024-01): sin efecto (paridad).
- **No resuelto:** EDECHI 2015-10 (+10,6 % de clientes en un mes, persistente; también suben las ventas) y EDEMET 2019-04 (+3,4 % en dos meses, persistente). Los boletines no traen notas metodológicas ni definen «clientes» (¿regulados?, ¿grandes clientes?). Se conservan y se marcan como **cambio de nivel**; son una limitación declarada.
- La caída del consumo por cliente de EDEMET y ENSA ocurre sobre todo entre 2018 y 2020 (empieza antes de la pandemia). No se pudo verificar si es real (clientes nuevos más pequeños, eficiencia, autoconsumo) o un cambio de cobertura (p. ej. grandes clientes que pasan a comprar en el mercado mayorista). Indicio: la demanda máxima del sistema crece +27 % 2014→2025 y las ventas de las distribuidoras solo +9,7 %.

## Resultados principales (corrida del 2026-11-25)

Descomposición LMDI aditiva (V = clientes × kWh por cliente; los efectos suman exactamente el cambio):

| Distribuidora | Ventas 2014→2025 | Efecto clientes | Efecto consumo/cliente | Ventas 2021→2025 | Efecto clientes | Efecto consumo/cliente |
|---|---|---|---|---|---|---|
| EDEMET | 3.796 → 3.903 GWh (+2,8 %, +107 GWh) | +1.370 GWh | −1.263 GWh | 3.404 → 3.903 GWh (+14,6 %, +499 GWh) | +353 GWh (71 %) | +146 GWh (29 %) |
| ENSA | 3.044 → 3.315 GWh (+8,9 %, +271 GWh) | +926 GWh | −655 GWh | 2.935 → 3.315 GWh (+13,0 %, +380 GWh) | +305 GWh (80 %) | +75 GWh (20 %) |
| EDECHI | 625 → 972 GWh (+55,5 %, +347 GWh) | +329 GWh (95 %) | +18 GWh (5 %) | 822 → 972 GWh (+18,3 %, +150 GWh) | +90 GWh (60 %) | +60 GWh (40 %) |

kWh/cliente/mes 2014 → 2025: EDEMET 761 → 548; ENSA 633 → 516; EDECHI 425 → 435.
Reclamos por 10.000 clientes al mes (2021 → 2025, 11 meses): EDEMET 4,06 → 7,93; ENSA 2,26 → 4,76; EDECHI 1,56 → 2,97. Correlación mensual reclamos–ventas 2021-01…2025-11: r = 0,71 / 0,84 / 0,72.

**Respuesta:** EDECHI es la que más crece en términos relativos en ambos periodos (+55,5 % 2014→2025; +18,3 % 2021→2025). Su crecimiento se explica sobre todo por más clientes (95 % en 2014→2025; 60 % en 2021→2025, con 40 % por mayor consumo por cliente). En GWh absolutos, desde 2021 crece más EDEMET (+499 GWh, 71 % por clientes). En 2014→2025, EDEMET y ENSA ganan clientes pero su consumo por cliente cae, y los dos efectos casi se anulan (los % del cambio neto no tienen sentido; se informan en GWh). 2026 (ene–sep vs. ene–sep 2025): ventas +5,9 % EDEMET, +7,7 % ENSA, +7,5 % EDECHI, ahora explicadas sobre todo por el consumo por cliente.

## Limitaciones

- **Correlación ≠ causa** (reclamos vs. ventas: ambos son estacionales).
- **Definiciones:** «clientes» y «ventas» no se definen en los boletines; cambios de nivel EDECHI 2015-10 y EDEMET 2019-04 sin explicar; la caída del consumo por cliente 2018–2020 puede deberse a un cambio de cobertura.
- **Errores de la fuente:** 3 boletines sin tabla de texto (2014-03, 2015-05, 2015-06) y ~50 arrastres por variable se imputan; las cifras imputadas son estimaciones.
- Reclamos: 2025 sin diciembre, 2026 solo enero; los dos CSV de ASEP no coinciden en 2023.
- Demanda máxima: tomada del boletín más reciente que publica cada mes; hay discrepancias entre boletines (p. ej. sep-2020: 1.399 vs. 1.775 MW) registradas en `silver/demanda_maxima_mensual.csv`.
- MongoDB se probó con `mongomock` y con el fallback JSON; S3 con `moto`; el DAG con `--run-local` (no en un Airflow real); la IA corrió en modo offline (plantilla).
- `scripts/extraer_clientes_ventas.py` (versión anterior del lector) queda solo como referencia; lo reemplaza `extraer_boletines.py`.
