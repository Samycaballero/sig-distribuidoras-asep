"""Figuras PNG (matplotlib, 300 dpi) y dashboard HTML interactivo autocontenido a partir de la capa gold/silver.

Paleta categórica validada (modo claro y oscuro): EDEMET azul, ENSA naranja, EDECHI verde, siempre en ese orden y con
los mismos colores en el dashboard y en las figuras. Efectos LMDI: violeta (clientes) y ámbar (consumo por cliente).
Ninguna cifra se escribe a mano: todo sale de gold (kpi_summary.json, calidad_auditoria.json, CSV) o de silver.
Uso: python generar_dashboard_y_graficos.py
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

import calidad  # noqa: E402
import config  # noqa: E402

COL = {"EDEMET": "#2a78d6", "ENSA": "#eb6834", "EDECHI": "#1baf7a"}
C_CLI, C_CON = "#6250d6", "#eda100"
TXT, TXT2, GRID, BG = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": GRID, "axes.labelcolor": TXT2, "xtick.color": TXT2,
                     "ytick.color": TXT2, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True, "figure.facecolor": BG, "axes.facecolor": BG})
FUENTE = (f"Fuente: ASEP, boletines mensuales 2013–2026 (PDF); datos abiertos ASEP (CSV y API CKAN). "
          f"Fecha de consulta: {config.FECHA_CONSULTA}. Elaboración propia.")
MILES = FuncFormatter(lambda v, _: f"{v:,.0f}")
VARS = ("clientes", "ventas_kwh", "facturacion_usd")
A0, A1 = config.ANIO_INICIO, config.ANIO_FIN

# ---- textos de presentación (los códigos internos de calidad se muestran en español con tildes) ----
METODO = {"interpolacion_lineal_clientes": "interpolación lineal de clientes",
          "interpolacion_kwh_por_cliente": "interpolación de kWh/cliente × clientes",
          "interpolacion_usd_por_kwh": "interpolación de US$/kWh × ventas"}
REGLA = {"faltante": "R1 faltante", "arrastre_mes_anterior": "R2 arrastre del mes anterior",
         "atipico_puntual": "R3 atípico puntual", "kwh_cliente_fuera_banda": "R4 kWh/cliente fuera de banda",
         "salto_mm": "R5 salto mensual", "total_no_cuadra": "Total publicado ≠ suma",
         "etiqueta_mes_tabla_distinta": "Etiqueta de mes distinta", "unidad_mixta_en_boletin": "Unidad mixta en el boletín",
         "tabla_en_imagen": "Tabla en imagen", "numero_mal_formado": "Número mal formado",
         "transcripcion_manual": "Transcripción manual", "seccion_ausente": "Sección ausente"}
VARIABLE = {"clientes": "Clientes", "ventas_kwh": "Ventas (kWh)", "facturacion_usd": "Facturación (US$)",
            "(tabla)": "Tabla del boletín"}
ESTADO = {"OK": "OK", "OK_CON_OBSERVACIONES": "OK con observaciones", "TOTAL_NO_CUADRA": "total no cuadra",
          "TABLA_EN_IMAGEN": "tabla en imagen", "SECCION_AUSENTE": "sección ausente",
          "TRANSCRIPCION_MANUAL": "transcripción manual"}
_ES = [*METODO.items(), *((k, v.lower()) for k, v in ESTADO.items() if k != "OK"),
       ("arrastre_mes_anterior", "arrastre del mes anterior"), ("kwh_cliente_fuera_banda", "kWh/cliente fuera de banda"),
       ("etiqueta_mes_tabla=", "etiqueta del mes en la tabla: "), ("total_no_cuadra_", "total no cuadra: "),
       ("salto_mm", "salto mensual"), ("_", " "), (r"\btranscripcion", "transcripción"), (r"\bseccion\b", "sección"),
       (r"\bpaginas\b", "páginas"), (r"\bpag\.", "pág."), (r"\bindice\b", "índice"), (r"\bnumeros\b", "números"),
       (r"\bimagenes\b", "imágenes"), (r"\batipico\b", "atípico"), (r"\bfacturacion\b", "facturación"),
       (r"\bboletin\b", "boletín"), (r"(?<=\S)\(", " ("), (r";(?=\S)", "; "), (r"(\d)%", r"\1 %")]


def es(texto):
    """Códigos/textos internos de calidad → español legible con tildes (solo presentación)."""
    t = str(texto or "")
    for a, b in _ES:
        t = re.sub(a, b, t) if a.startswith(("\\", "(", ";")) else t.replace(a, b)
    return t


def _guardar(fig, nombre):
    d = config.out_dir() / "graficos"
    d.mkdir(parents=True, exist_ok=True)
    fig.text(0.01, 0.005, FUENTE, fontsize=6.5, color=TXT2)
    fig.savefig(d / nombre, dpi=300, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)
    return nombre


def cargar():
    g, s = config.gold_dir(), config.silver_dir()
    return {"resumen": json.loads((g / "kpi_summary.json").read_text(encoding="utf-8")),
            "aud": json.loads((g / "calidad_auditoria.json").read_text(encoding="utf-8")),
            "kpi": calidad.leer_csv(g / "kpi_anual.csv"), "lmdi": calidad.leer_csv(g / "lmdi_descomposicion.csv"),
            "rec": calidad.leer_csv(g / "reclamos_mensual.csv"), "mensual": calidad.leer_csv(s / "mercado_mensual.csv")}


def _imputados(D):
    """(valores imputados, filas distribuidora-mes con imputación) en el periodo base."""
    base = [r for r in D["mensual"] if A0 <= int(r["anio"]) <= A1]
    return (sum(bool(r[v + "_imputacion"]) for r in base for v in VARS),
            D["resumen"]["calidad"]["filas_imputadas_periodo_base"])


# ---------------- figuras ----------------
def fig_arquitectura(D):
    fig, ax = plt.subplots(figsize=(12, 6.2))
    ax.set_axis_off()
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 6.6)
    etiqueta_ia = D["resumen"].get("diagnostico_ia", {}).get("etiqueta", "no generado")

    def caja(x, y, w, h, titulo, texto, color, real=True):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12", fc="white" if real else BG,
                                    ec=color, lw=1.6, ls="-" if real else (0, (4, 3))))
        ax.text(x + w / 2, y + h - 0.2, titulo, ha="center", va="top", fontsize=9, weight="bold", color=TXT)
        ax.text(x + w / 2, y + h - 0.55, texto, ha="center", va="top", fontsize=7.4, color=TXT2, linespacing=1.35)

    def flecha(x0, y0, x1, y1):
        ax.annotate("", (x1, y1), (x0, y0), arrowprops=dict(arrowstyle="-|>", color=TXT2, lw=1.1, shrinkA=2, shrinkB=2))

    cols = [(0.1, "Fuentes"), (2.15, "Bronze"), (4.2, "Silver"), (6.25, "Gold"), (8.3, "Almacenamiento"), (10.2, "Consumo")]
    for x, t in cols:
        ax.text(x + 0.85, 6.45, t, ha="center", fontsize=10, weight="bold", color=C_CLI)
    azul, gris = COL["EDEMET"], TXT2
    caja(0.1, 4.55, 1.8, 1.5, "PDF", "Boletines mensuales\nASEP (162,\nabr-2013 a sep-2026)", azul)
    caja(0.1, 2.75, 1.8, 1.5, "CSV", "Reclamos de\nelectricidad\n(datos abiertos)", azul)
    caja(0.1, 0.95, 1.8, 1.5, "JSON", "API CKAN:\nmanifiesto y fechas\nde actualización", azul)
    caja(2.15, 2.0, 1.75, 3.3, "data/raw", "Archivos tal como\nse descargaron\n\nsha256 y fecha\nde descarga\n\nPDF → texto\n(pypdf, caché)", azul)
    caja(4.2, 2.0, 1.75, 3.3, "data/silver", "mercado_mensual\n\nReglas R1–R5\n\nImputación\nauditada (valor\nde la fuente\nconservado)", azul)
    caja(6.25, 2.0, 1.75, 3.3, "data/gold", "KPIs anuales\n\nLMDI\n(clientes × kWh\npor cliente)\n\nkpi_summary.json\ncalidad_auditoria", azul)
    caja(8.3, 4.35, 1.65, 1.55, "SQLite", "Modelo estrella\nsig_distribuidoras.db\nvistas vw_bi_*", azul)
    caja(8.3, 2.45, 1.65, 1.6, "MongoDB", "Boletines y\nmanifiesto\n(sin servidor:\nfallback JSON)", gris, real=False)
    caja(8.3, 0.75, 1.65, 1.4, "AWS S3", "Publicación\nopcional", gris, real=False)
    caja(10.2, 4.35, 1.7, 1.55, "Dashboard", "HTML interactivo\nautocontenido\n(sin conexión)", azul)
    caja(10.2, 2.6, 1.7, 1.45, "Figuras", "6 PNG para\ninforme y\npresentación", azul)
    caja(10.2, 0.75, 1.7, 1.55, "Diagnóstico IA", f"Usado hoy:\n{etiqueta_ia}\n(LLM: opcional)", gris, real=False)
    for y in (5.3, 3.5, 1.7):
        flecha(1.9, y, 2.15, min(max(y, 2.3), 5.0))
    flecha(3.9, 3.65, 4.2, 3.65)
    flecha(5.95, 3.65, 6.25, 3.65)
    for y in (5.1, 3.25, 1.45):
        flecha(8.0, 3.65, 8.3, y)
    for y in (5.1, 3.3, 1.5):
        flecha(9.95, 5.1, 10.2, y)
    fig.subplots_adjust(left=0.01, right=0.99, top=0.9, bottom=0.06)
    ax.add_patch(FancyBboxPatch((2.15, 0.12), 5.85, 0.55, boxstyle="round,pad=0.02,rounding_size=0.1", fc="white", ec=C_CLI, lw=1.4))
    ax.text(5.07, 0.39, "Orquestación: DAG de Airflow (ejecutado aquí con --run-local; Airflow real: opcional)",
            ha="center", va="center", fontsize=7.4, color=TXT)
    ax.plot([], [], color=azul, lw=1.6, label="Implementado y ejecutado en esta corrida")
    ax.plot([], [], color=gris, lw=1.6, ls=(0, (4, 3)), label="Opcional o con respaldo (no requerido para ejecutar)")
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, -0.06), frameon=False, fontsize=8, ncol=2)
    ax.set_title("Arquitectura del SIG de distribuidoras: fuentes → bronze / silver / gold → almacenamiento → dashboard e IA",
                 loc="left", fontsize=11.5, color=TXT)
    return _guardar(fig, "fig1_arquitectura_sig.png")


def fig_ventas(D):
    fig, ax = plt.subplots(figsize=(9, 4.8))
    for d in config.DISTRIBUIDORAS:
        f = [k for k in D["kpi"] if k["distribuidora"] == d and A0 <= int(k["anio"]) <= A1]
        x, y = [int(k["anio"]) for k in f], [float(k["ventas_gwh"]) for k in f]
        ax.plot(x, y, color=COL[d], lw=2.2, marker="o", ms=4)
        ax.annotate(f"{d}\n{y[-1]:,.0f} GWh ({100 * (y[-1] / y[0] - 1):+.1f} %)", (x[-1], y[-1]), xytext=(8, 0),
                    textcoords="offset points", va="center", fontsize=8.5, color=COL[d], weight="bold")
        ax.annotate(f"{y[0]:,.0f}", (x[0], y[0]), xytext=(-6, 0), textcoords="offset points", va="center", ha="right",
                    fontsize=8, color=TXT2)
    ax.yaxis.set_major_formatter(MILES)
    ax.set_ylabel("GWh por año")
    ax.set_xticks(range(A0, A1 + 1), [str(a) for a in range(A0, A1 + 1)], fontsize=8)
    ax.set_xlim(A0 - 0.8, A1 + 2.6)
    ax.set_ylim(0, None)
    ax.set_title(f"Ventas anuales de energía por distribuidora, {A0}–{A1} (GWh)", loc="left", fontsize=12, color=TXT)
    return _guardar(fig, "fig2_ventas_anuales.png")


def fig_lmdi(D):
    acum = [x for x in D["lmdi"] if x["tipo"] == "acumulada" and x["distribuidora"] in config.DISTRIBUIDORAS]
    tramos = sorted({(int(x["anio_base"]), int(x["anio_fin"])) for x in acum})
    fig, axs = plt.subplots(1, len(tramos), figsize=(12, 4.6), sharex=True)
    vals = [float(x[k]) for x in acum for k in ("efecto_clientes_gwh", "efecto_consumo_por_cliente_gwh", "delta_gwh")]
    lim = max(abs(v) for v in vals) * 1.25
    for ax, (a0, a1) in zip(axs, tramos):
        filas = [next(x for x in acum if x["distribuidora"] == d and int(x["anio_base"]) == a0) for d in config.DISTRIBUIDORAS]
        for j, x in enumerate(filas):
            y = len(filas) - 1 - j
            ec, ei, dv = (float(x[k]) for k in ("efecto_clientes_gwh", "efecto_consumo_por_cliente_gwh", "delta_gwh"))
            ax.barh(y + 0.17, ec, 0.32, color=C_CLI)
            ax.barh(y - 0.17, ei, 0.32, color=C_CON)
            for v, yy in ((ec, y + 0.17), (ei, y - 0.17)):
                ax.annotate(f"{v:+,.0f}", (v, yy), xytext=(4 if v >= 0 else -4, 0), textcoords="offset points",
                            ha="left" if v >= 0 else "right", va="center", fontsize=8, color=TXT)
            ax.plot([dv], [y], marker="D", color=COL[x["distribuidora"]], mec=TXT, ms=8, zorder=4)
            ax.text(lim * 0.98, y + 0.43, f"Cambio total {dv:+,.0f} GWh ({float(x['crec_ventas_pct']):+.1f} %)",
                    ha="right", va="center", fontsize=7.8, color=TXT, weight="bold")
        ax.axvline(0, color=TXT2, lw=0.8)
        ax.set_yticks(range(len(filas)), [x["distribuidora"] for x in reversed(filas)], fontsize=10)
        for t, x in zip(ax.get_yticklabels(), reversed(filas)):
            t.set_color(COL[x["distribuidora"]])
            t.set_fontweight("bold")
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-0.6, len(filas) - 0.25)
        ax.xaxis.set_major_formatter(MILES)
        ax.set_xlabel("GWh")
        ax.set_title(f"{a0} → {a1}", loc="left", fontsize=11, color=TXT)
        ax.grid(axis="y", visible=False)
    fig.legend(handles=[Patch(color=C_CLI, label="Efecto clientes (más o menos clientes)"),
                        Patch(color=C_CON, label="Efecto consumo por cliente"),
                        Line2D([], [], ls="", marker="D", color="#999", mec=TXT, label="Cambio total = suma de los dos efectos")],
               loc="lower center", bbox_to_anchor=(0.5, 0.04), ncol=3, frameon=False, fontsize=8.5)
    fig.suptitle("Descomposición LMDI del cambio en ventas por distribuidora (GWh)", x=0.01, ha="left", fontsize=12.5, color=TXT)
    fig.subplots_adjust(bottom=0.27, wspace=0.25)
    return _guardar(fig, "fig3_descomposicion_lmdi.png")


def fig_kwh_cliente(D):
    fig, ax = plt.subplots(figsize=(10, 4.8))
    for d in config.DISTRIBUIDORAS:
        f = [r for r in D["mensual"] if r["distribuidora"] == d and A0 <= int(r["anio"]) <= A1]
        x = [int(r["anio"]) + (int(r["mes"]) - 0.5) / 12 for r in f]
        y = [float(r["ventas_kwh"]) / float(r["clientes"]) for r in f]
        ax.plot(x, y, color=COL[d], lw=1.5)
        imp = [(a, b) for a, b, r in zip(x, y, f) if r["ventas_kwh_imputacion"] or r["clientes_imputacion"]]
        if imp:
            ax.scatter(*zip(*imp), s=30, marker="D", facecolor="white", edgecolor=TXT, lw=1.1, zorder=3)
        ax.annotate(d, (x[-1], y[-1]), xytext=(6, 0), textcoords="offset points", va="center", fontsize=9,
                    color=COL[d], weight="bold")
    ax.scatter([], [], s=30, marker="D", facecolor="white", edgecolor=TXT, lw=1.1,
               label="Mes con ventas o clientes imputados")
    ax.legend(frameon=False, fontsize=8.5, loc="upper right")
    ax.yaxis.set_major_formatter(MILES)
    ax.set_ylabel("kWh por cliente al mes")
    ax.set_xticks(range(A0, A1 + 2), [str(a) for a in range(A0, A1 + 2)], fontsize=8)
    ax.set_xlim(A0, A1 + 1.7)
    ax.set_title(f"Consumo por cliente (kWh/cliente/mes), {A0}–{A1}, con los meses imputados marcados",
                 loc="left", fontsize=12, color=TXT)
    return _guardar(fig, "fig4_kwh_por_cliente_mensual.png")


def _pearson(x, y):
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return sxy / (sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)) ** 0.5


def fig_reclamos(D):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw={"width_ratios": [1.35, 1]})
    corr = {c["distribuidora"]: c for c in D["resumen"]["reclamos"]["correlaciones"]}
    for d in config.DISTRIBUIDORAS:
        f = [r for r in D["rec"] if r["distribuidora"] == d and int(r["anio"]) <= A1]
        x = [int(r["anio"]) + (int(r["mes"]) - 0.5) / 12 for r in f]
        a1.plot(x, [float(r["reclamos_por_10k_clientes"]) for r in f], color=COL[d], lw=1.6)
        a1.annotate(d, (x[-1], float(f[-1]["reclamos_por_10k_clientes"])), xytext=(5, 0), textcoords="offset points",
                    va="center", fontsize=8.5, color=COL[d], weight="bold")
        c = corr[d]
        g = [r for r in f if c["desde"] <= r["periodo"] <= c["hasta"]]
        a2.scatter([float(r["ventas_kwh"]) / 1e6 for r in g], [int(r["reclamos"]) for r in g], s=14, color=COL[d], alpha=0.8,
                   label=f"{d}: r = {c['r_reclamos_vs_ventas']:.2f} ({c['n_meses']} meses)")
    anios = sorted({int(r["anio"]) for r in D["rec"] if int(r["anio"]) <= A1})
    a1.set_xticks(anios + [anios[-1] + 1], [str(a) for a in anios + [anios[-1] + 1]], fontsize=8)
    a1.set_xlim(anios[0], anios[-1] + 1.45)
    a1.set_ylabel("Reclamos por cada 10 mil clientes (mes)")
    a1.set_title(f"Reclamos por cada 10 mil clientes, {anios[0]}–{anios[-1]}", loc="left", fontsize=10.5, color=TXT)
    a2.xaxis.set_major_formatter(MILES)
    a2.yaxis.set_major_formatter(MILES)
    a2.set_xlabel("Ventas del mes (GWh)")
    a2.set_ylabel("Reclamos admitidos en el mes")
    a2.set_title("Reclamos frente a ventas mensuales", loc="left", fontsize=10.5, color=TXT)
    a2.legend(frameon=False, fontsize=8, loc="upper left")
    a2.text(0.99, 0.02, "Correlación ≠ causalidad:\nambas series son estacionales", transform=a2.transAxes, ha="right",
            va="bottom", fontsize=8, color=TXT2, style="italic")
    nota = f"; {anios[-1]} sin diciembre en la fuente" if any(c["hasta"].endswith("-11") for c in corr.values()) else ""
    fig.suptitle(f"Reclamos de electricidad admitidos por ASEP y su relación con las ventas ({anios[0]}–{anios[-1]}{nota})",
                 x=0.01, ha="left",
                 fontsize=12, color=TXT)
    fig.subplots_adjust(wspace=0.28)
    return _guardar(fig, "fig5_reclamos_vs_ventas.png")


def _buscar_navegador():
    for n in ("chrome", "msedge", "google-chrome", "chromium", "chromium-browser"):
        if shutil.which(n):
            return shutil.which(n)
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if os.path.exists(p):
            return p
    return None


def fig_dashboard(D):
    """Captura real del dashboard con un navegador sin interfaz; si no hay navegador, maqueta con las mismas cifras."""
    nombre = "fig6_dashboard.png"
    destino = config.out_dir() / "graficos" / nombre
    html = config.out_dir() / "dashboard_interactivo.html"
    nav = _buscar_navegador()
    if nav and html.exists():
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "captura.png"
            try:
                subprocess.run([nav, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                                f"--user-data-dir={tmp}", "--window-size=1280,1650", "--force-device-scale-factor=2",
                                "--virtual-time-budget=4000", f"--screenshot={png}", html.resolve().as_uri() + "?tema=claro"],
                               capture_output=True, timeout=90, check=False)
                if png.exists():
                    from PIL import Image
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    Image.open(png).convert("RGB").save(destino, dpi=(300, 300))
                    return nombre
            except (OSError, subprocess.SubprocessError):
                pass
    # maqueta de respaldo: tarjetas KPI con la descomposición 2014→2025 desde gold
    acum = {x["distribuidora"]: x for x in D["lmdi"] if x["tipo"] == "acumulada" and int(x["anio_base"]) == A0}
    fig, ax = plt.subplots(figsize=(10, 3.2))
    ax.set_axis_off()
    ax.set_title(f"Maqueta del dashboard (sin navegador para capturar): tarjetas KPI {A0}→{A1}", loc="left", fontsize=11)
    for j, d in enumerate(config.DISTRIBUIDORAS):
        x = acum[d]
        ax.add_patch(FancyBboxPatch((j * 0.335, 0.05), 0.31, 0.85, boxstyle="round,pad=0.01", fc="white", ec=COL[d], lw=2,
                                    transform=ax.transAxes))
        ax.text(j * 0.335 + 0.02, 0.8, d, transform=ax.transAxes, fontsize=11, weight="bold", color=COL[d])
        ax.text(j * 0.335 + 0.02, 0.58, f"{float(x['crec_ventas_pct']):+.1f} % ventas", transform=ax.transAxes, fontsize=14)
        ax.text(j * 0.335 + 0.02, 0.15, f"Efecto clientes {float(x['efecto_clientes_gwh']):+,.1f} GWh\n"
                f"Efecto consumo/cliente {float(x['efecto_consumo_por_cliente_gwh']):+,.1f} GWh",
                transform=ax.transAxes, fontsize=8.5, color=TXT2)
    return _guardar(fig, nombre)


def generar_figuras(D=None):
    D = D or cargar()
    return [f(D) for f in (fig_arquitectura, fig_ventas, fig_lmdi, fig_kwh_cliente, fig_reclamos, fig_dashboard)]


# ---------------- dashboard ----------------
def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _num_o_texto(x):
    return x if x is None or _num(x) is None else _num(x)


def datos_dashboard(D):
    R, aud = D["resumen"], D["aud"]
    n_val, n_filas = _imputados(D)
    nombres = {"clientes": "Clientes", "ventas_kwh": "Ventas", "facturacion_usd": "Facturación"}

    def imput(r):
        out = {}
        for v in VARS:
            if r[v + "_imputacion"]:
                out[v[0]] = {"var": nombres[v], "met": METODO.get(r[v + "_imputacion"], es(r[v + "_imputacion"])),
                             "o": _num(r[v + "_fuente"]), "mot": es(r[v + "_flags"])}
        return out

    mensual = []
    for r in D["mensual"]:
        fila = {"p": r["periodo"], "d": r["distribuidora"], "c": int(r["clientes"]), "v": float(r["ventas_kwh"]),
                "f": _num(r["facturacion_usd"])}
        if imput(r):
            fila["im"] = imput(r)
        mensual.append(fila)
    anual = [{"d": k["distribuidora"], "a": int(k["anio"]), "v": k["ventas_gwh"], "c": k["clientes_promedio"],
              "k": k["kwh_cliente_mes"], "u": k["ingreso_medio_usd_kwh"], "s": k["participacion_ventas_pct"],
              "i": k["meses_con_imputacion"]}
             for k in R["kpis_anuales"] if k["distribuidora"] in config.DISTRIBUIDORAS]
    tipo = lambda res: "imputado" if res.startswith("imputado") or "mes imputado" in res else (  # noqa: E731
        "conservado" if "conservado" in res else "otro")
    incid = [{"p": i["periodo"], "d": "(boletín)" if i["distribuidora"] == "(boletin)" else i["distribuidora"],
              "v": VARIABLE.get(i["variable"], es(i["variable"])), "r": REGLA.get(i["regla"], es(i["regla"])),
              "det": es(i["detalle"]), "of": _num_o_texto(i["valor_fuente"]), "vf": _num_o_texto(i["valor_final"]),
              "res": es(i["resolucion"]),
              "t": tipo(i["resolucion"])} for i in aud["incidencias"]]
    return {"pregunta": R["pregunta"], "respuesta": R["respuesta"]["texto"], "advertencias": R["advertencias"],
            "hallazgos": R.get("hallazgos", []), "diagnostico": R.get("diagnostico_ia", {}),
            "fuente": "ASEP, boletines mensuales 2013–2026; datos abiertos ASEP", "consulta": config.FECHA_CONSULTA,
            "anio_ini": A0, "anio_fin": A1, "imputados": {"valores": n_val, "filas": n_filas},
            "anual": anual, "mensual": mensual,
            "reclamos": [{"p": r["periodo"], "d": r["distribuidora"], "r": int(r["reclamos"]), "t": float(r["reclamos_por_10k_clientes"]),
                          "v": float(r["ventas_kwh"])} for r in D["rec"]],
            "reclamos_anual": [{"d": x["distribuidora"], "a": x["anio"], "m": x["meses"], "t": x["reclamos_por_10k_clientes_mes_prom"]}
                               for x in R["reclamos"]["anual"]],
            "est": [{"d": x["distribuidora"], "m": x["mes"], "i": x["indice_ventas"]} for x in R["estacionalidad"]],
            "reciente": R.get("vista_reciente_2026", []),
            "calidad": {"incidencias": incid, "boletines": aud["boletines"]["total"],
                        "estados": {ESTADO.get(k, es(k)): v for k, v in aud["boletines"]["por_estado"].items()},
                        "cambios_nivel": R["calidad"]["cambios_de_nivel"]}}


def generar_dashboard_html(D=None):
    D = D or cargar()
    plantilla = (config.BASE_DIR / "dashboard_template.html").read_text(encoding="utf-8")
    datos = json.dumps(datos_dashboard(D), ensure_ascii=False).replace("</", "<\\/")  # sin cierre de <script> en los datos
    html = plantilla.replace("/*__DATOS__*/null", datos)
    p = config.out_dir() / "dashboard_interactivo.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    return p.name


def main():
    D = cargar()
    dash = generar_dashboard_html(D)  # antes de las figuras: la figura 6 es una captura del dashboard
    return {"figuras": len(generar_figuras(D)), "dashboard": dash}


if __name__ == "__main__":
    print(main())
