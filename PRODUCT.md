# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Primary: the course evaluator (professor Gema Castillo) and the class, watching the dashboard **projected during the group defense**; the team (Samir Caballero drives the demo) operates it live. Secondary: the professor reviewing the file alone on a laptop. Role framing in the project: an analysis unit inside ASEP, the electricity regulator of Panama (academic simulation).

## Product Purpose
A management information system (SIG) that answers: *¿En qué distribuidora eléctrica de Panamá está creciendo más el consumo, y cuánto de ese crecimiento se explica por más clientes o por mayor consumo por cliente?* The dashboard lets a manager follow KPIs per distributor (EDEMET, ENSA, EDECHI), see the LMDI decomposition of sales growth (clients effect + consumption-per-client effect = total change), monthly series with imputed months marked, seasonality, market share, complaints per 10,000 clients, data-quality incidents, and an AI diagnosis. Success: the question is answered at a glance and every figure is traceable to public ASEP data.

## Positioning
Built only on real public data from ASEP (162 monthly PDF bulletins 2013–2026 plus open-data CSV/API), with every source error flagged and every imputation kept next to its original value.

## Operating Context
Opened by double-click as a single self-contained HTML file (`codigo_y_dashboard/dashboard_interactivo.html`, generated from `dashboard_template.html` by `generar_dashboard_y_graficos.py`), shown full-screen on a classroom projector, filtered live while presenting; also captured headlessly as a PNG figure (fig6) for the report and slides.

## Capabilities and Constraints
- Must work **offline**: one HTML file, no CDNs, no external fonts or libraries.
- Must not change data or calculations; all numbers come from the gold layer.
- Filters: distributors, start year, end year, metric (ventas GWh, clientes, kWh/cliente/mes, US$/kWh with warning), reset. Tabs: Análisis and Calidad de datos.
- Light and dark modes (`?tema=claro|oscuro` and system preference). Spanish with correct accents.
- Existing automated checks to keep passing: tests in `codigo_y_dashboard/tests/test_presentacion.py` and the headless bounds check (data marks inside plot areas).

## Brand Commitments
Distributor colors are fixed and shared with the report, slides and figures: **EDEMET blue, ENSA orange, EDECHI green** (as defined today in `dashboard_template.html`). Language: Spanish (Panamá), comma thousands separator.

## Evidence on Hand
Real data in `data/gold` (kpi_summary.json, sig_distribuidoras.db, calidad_auditoria.json). Do not invent metrics, benchmarks or claims beyond these.

## Product Principles
1. The answer to the managerial question comes first.
2. Every number is traceable; imputed and flagged values are always visible as such.
3. Readable from the back of a classroom.
4. Honest labels: the AI panel shows the provider actually used.
