# Verificación de los boletines mensuales de ASEP

**Fecha de descarga y verificación:** 2026-11-25
**Fuente:** ASEP, "Estadística del Mercado Eléctrico Panameño" (boletín mensual, PDF)
`https://asep.gob.pa/wp-content/uploads/electricidad/estadisticas_mensuales/{AÑO}/{MES}_{AÑO}.pdf`
(en 2017 los nombres van en minúscula: `enero_2017.pdf`)

## 1. Cobertura
- **162 boletines**, de **abril 2013 a septiembre 2026**, sin meses faltantes en el rango.
- 2013: abr–dic (9) · 2014–2025: 12 por año · 2026: ene–sep (9).
- Archivos en `data/raw/boletines_asep/AAAA_MES.pdf`.

## 2. Qué trae cada boletín
Sección "Clientes, ventas y facturación (o ingresos) por distribuidora": **número de clientes, ventas (kWh) y facturación (US$ o B/.)** para EDEMET, ENSA (o Elektra) y EDECHI, más el total. También trae capacidad instalada, generación por planta, demanda máxima, costo marginal y costos por tecnología.

## 3. Resultado de la extracción (`scripts/extraer_clientes_ventas.py`)
- **150 de 162 boletines extraídos sin observaciones** (`data/interim/clientes_ventas.csv`, 466 filas; log en `data/interim/log_extraccion.csv`).
- Unidad de ventas: el texto no siempre la indica junto a la tabla. Se infiere por magnitud (100–3,000 kWh por cliente al mes): 422 filas en kWh, 44 convertidas desde MWh.
- Moneda declarada: US $ (298 filas), Balboas (165), no indicada (3). B/. y USD van a la par.

| Mes | Problema | Origen |
|---|---|---|
| 2013-04, 2014-03, 2015-05, 2016-01 | No se encontró la tabla de clientes | Por revisar (formato o tabla en imagen) |
| 2015-06, 2019-12 | No se leyeron las tres empresas | Por revisar |
| 2016-10, 2016-11 | El total no cuadra | **Lector**: tomó la tabla de costos; hay que afinar la búsqueda de la página |
| 2017-11, 2017-12 | El total no cuadra | Por revisar |
| 2018-05 | Falta ENSA | **Fuente**: facturación escrita «54128.000.00» |
| 2019-01 | Falta ENSA | Por revisar |
| 2021-10 | Ventas EDEMET 828 M kWh y ENSA «249,949» | **Fuente**: error en el propio boletín; el total publicado suma esos valores |

Otros saltos a revisar en la etapa de calidad: EDECHI 2015-10 (+10,6 % en clientes y ventas), EDEMET 2021-02 (−20,8 % ventas).

## 4. Rangos (filas válidas)
- kWh por cliente al mes (mediana): EDEMET 602 · ENSA 548 · EDECHI 439.

## 5. Resultados preliminares (NO definitivos)
**Dic-2021 → dic-2025 (descomposición LMDI):** EDECHI crece más en ventas (+17,4 %); en EDEMET y ENSA el crecimiento se explica ~75–78 % por más clientes; en EDECHI 56 % por clientes y 44 % por mayor consumo por cliente.

**2014 → 2025 (11 meses comunes):** ventas EDEMET +2,6 %, ENSA +8,3 %, EDECHI +54,6 %. Clientes +43 %, +34 % y +51 %. El consumo por cliente **baja** en EDEMET (−28 %) y ENSA (−19 %).
> Precaución: puede ser real (entrada de clientes de menor consumo) o un cambio de definiciones o cobertura en los boletines (p. ej. el salto de EDECHI en 2015-10). Hay que verificarlo antes de concluir.

## 6. Pendientes antes de iniciar el proyecto
1. Corregir el lector para 2016-10/11 y revisar los 10 meses restantes con observaciones.
2. Revisar cambios de definición (clientes regulados vs. totales, "ventas" vs. "ingresos") entre 2013 y 2026.
3. Decidir el periodo de análisis (sugerido: 2014–2025, años completos).
4. Elegir los otros dos tipos de datos (CSV de reclamos/generación de datos abiertos; JSON de la API del portal o XLSX).
