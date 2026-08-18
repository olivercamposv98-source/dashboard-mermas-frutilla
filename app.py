"""
Dashboard BI - Control de Mermas y Precio de Frutilla
Estilo dark navy / cyan. Conectado a Google Sheets (CSV export).
Compatible con Streamlit Community Cloud.
"""

import re
from datetime import timedelta
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import plotly.io as pio

# ──────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN GENERAL
# ──────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Dashboard Mermas · Frutilla",
    page_icon="🍓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Fuente de datos
SHEET_ID = "1IjkKtyacB5fiHqHJI9sLR2musell6iTigQNCPMUwhl4"
SHEET_NAME = "MERMAS_DE_FRUTILLA"
CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"
)

# Umbrales configurables (% merma sobre kg UTILIZABLE)
# Meta: mantener la merma en 10–11% como máximo.
UMBRAL_ALERT = 11.0  # % aceptable máximo; por encima entra en alerta gradual
UMBRAL_CRIT = 13.5   # % crítico / alarmante

# Paleta
C_BG = "#0A0E1A"
C_PANEL = "#111827"
C_CYAN = "#00F5D4"
C_GREEN = "#22C55E"
C_RED = "#EF4444"
C_YELLOW = "#FACC15"
C_TEXT = "#E5E7EB"
C_MUTED = "#94A3B8"
C_GRID = "#1E293B"

PLOTLY_TEMPLATE = "plotly_dark"

# Tooltip legible en todos los gráficos (fondo sólido + texto claro)
pio.templates[PLOTLY_TEMPLATE].layout.hoverlabel = dict(
    bgcolor=C_PANEL, bordercolor=C_CYAN,
    font=dict(color=C_TEXT, size=13, family="sans serif"),
)

# ──────────────────────────────────────────────────────────────────────────
# ESTILOS
# ──────────────────────────────────────────────────────────────────────────
st.markdown(
    f"""
    <style>
        .stApp {{ background-color: {C_BG}; }}
        section[data-testid="stSidebar"] {{ background-color: {C_PANEL}; }}
        h1, h2, h3, h4 {{ color: {C_TEXT}; }}
        .block-container {{ padding-top: 1.5rem; padding-bottom: 3rem; }}

        .kpi-card {{
            background: linear-gradient(145deg, #111827 0%, #0d1320 100%);
            border: 1px solid {C_GRID};
            border-radius: 14px;
            padding: 18px 20px;
            height: 100%;
        }}
        .kpi-label {{ color: {C_MUTED}; font-size: 0.80rem;
                      text-transform: uppercase; letter-spacing: .05em; }}
        .kpi-value {{ color: {C_TEXT}; font-size: 1.7rem; font-weight: 700;
                      margin-top: 4px; }}
        .kpi-sub  {{ color: {C_MUTED}; font-size: 0.78rem; margin-top: 2px; }}
        .kpi-accent {{ color: {C_CYAN}; }}
        .kpi-red {{ color: {C_RED}; }}
        .kpi-green {{ color: {C_GREEN}; }}
        .kpi-yellow {{ color: {C_YELLOW}; }}

        .alert-box {{
            border-radius: 12px; padding: 14px 18px; margin-bottom: 10px;
            border: 1px solid; font-size: 0.92rem;
        }}
        .alert-crit {{ background: rgba(239,68,68,.12);  border-color: {C_RED};   color: #FECACA; }}
        .alert-warn {{ background: rgba(250,204,21,.12); border-color: {C_YELLOW};color: #FEF08A; }}
        .alert-ok   {{ background: rgba(34,197,94,.12);  border-color: {C_GREEN}; color: #BBF7D0; }}
        .alert-info {{ background: rgba(0,245,212,.10);  border-color: {C_CYAN};  color: #99F6E4; }}

        hr {{ border-color: {C_GRID}; }}
        .stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
        .stTabs [data-baseweb="tab"] {{ font-size: 1rem; padding: 8px 18px; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────────────────
# PARSERS ROBUSTOS
# ──────────────────────────────────────────────────────────────────────────
def parse_money(val):
    """Convierte 'Bs5,040.00', 'Bs18.00', ' - ', '' → float."""
    if pd.isna(val):
        return np.nan
    s = str(val).strip()
    if s in ("", "-", "—", "n/a", "N/A"):
        return np.nan
    s = s.replace("Bs", "").replace("bs", "").replace(" ", "")
    s = s.replace(",", "")  # coma = separador de miles en este sheet
    s = re.sub(r"[^0-9.\-]", "", s)
    if s in ("", "-", ".", "-."):
        return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def parse_qty(val):
    """Convierte cantidad numérica robustamente."""
    if pd.isna(val):
        return np.nan
    s = str(val).strip().replace(" ", "")
    if s in ("", "-", "—"):
        return np.nan
    s = s.replace(",", "")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s)
    except ValueError:
        return np.nan


def norm_estado(val):
    """Normaliza ESTADO (quita espacios, mayúsculas, acentos)."""
    if pd.isna(val):
        return ""
    s = str(val).strip().upper()
    s = (s.replace("Ó", "O").replace("Á", "A").replace("É", "E")
           .replace("Í", "I").replace("Ú", "U"))
    if "INGRESO" in s:
        return "INGRESO"
    if "DEVOLUC" in s:
        return "DEVOLUCION"
    if "MERMA" in s or "LIMPIEZA" in s:
        return "MERMA_LIMPIEZA"
    return s


# ──────────────────────────────────────────────────────────────────────────
# CARGA DE DATOS (auto-refresh 60s)
# ──────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_data():
    df = pd.read_csv(CSV_URL, dtype=str)
    df.columns = [c.strip().upper() for c in df.columns]

    rename = {}
    for c in df.columns:
        if c.startswith("FECHA"):
            rename[c] = "FECHA"
        elif "PROVEEDOR" in c:
            rename[c] = "PROVEEDOR"
        elif c == "PRODUCTO":
            rename[c] = "PRODUCTO"
        elif "CANTIDAD" in c:
            rename[c] = "CANTIDAD"
        elif c == "ESTADO":
            rename[c] = "ESTADO"
        elif "PRECIO" in c:
            rename[c] = "PRECIO"
        elif c.startswith("TOTAL"):
            rename[c] = "TOTAL"
    df = df.rename(columns=rename)

    for col in ["FECHA", "PROVEEDOR", "PRODUCTO", "CANTIDAD", "ESTADO",
                "PRECIO", "TOTAL"]:
        if col not in df.columns:
            df[col] = np.nan

    df["FECHA"] = pd.to_datetime(df["FECHA"], format="%d/%m/%Y", errors="coerce")
    df["CANTIDAD"] = df["CANTIDAD"].apply(parse_qty)
    df["PRECIO"] = df["PRECIO"].apply(parse_money)
    df["TOTAL"] = df["TOTAL"].apply(parse_money)
    df["PROVEEDOR"] = df["PROVEEDOR"].astype(str).str.strip().str.upper()
    df["ESTADO_N"] = df["ESTADO"].apply(norm_estado)

    df["COSTO"] = df["CANTIDAD"] * df["PRECIO"]
    df["COSTO"] = df["COSTO"].fillna(df["TOTAL"])

    df = df[df["FECHA"].notna()]
    df = df[df["CANTIDAD"].notna() & (df["CANTIDAD"] > 0)]
    df = df[df["ESTADO_N"].isin(["INGRESO", "DEVOLUCION", "MERMA_LIMPIEZA"])]
    df = df[df["PROVEEDOR"].notna() & (df["PROVEEDOR"] != "") &
            (df["PROVEEDOR"] != "NAN")]

    df["SEMANA"] = df["FECHA"].dt.to_period("W").apply(lambda p: p.start_time)
    df["MES"] = df["FECHA"].dt.to_period("M").astype(str)
    return df.reset_index(drop=True)


# ──────────────────────────────────────────────────────────────────────────
# HELPERS DE AGREGACIÓN Y PRECIO
# ──────────────────────────────────────────────────────────────────────────
def agg_kg(frame, estado):
    return frame.loc[frame["ESTADO_N"] == estado, "CANTIDAD"].sum()


def agg_costo(frame, estado):
    return frame.loc[frame["ESTADO_N"] == estado, "COSTO"].sum()


def kpi(label, value, sub="", cls="kpi-accent"):
    return (
        f"<div class='kpi-card'>"
        f"<div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value {cls}'>{value}</div>"
        f"<div class='kpi-sub'>{sub}</div></div>"
    )


def cls_pct(p):
    if pd.isna(p):
        return "kpi-accent"
    return ("kpi-red" if p >= UMBRAL_CRIT else
            "kpi-yellow" if p >= UMBRAL_ALERT else "kpi-green")


def daily_purchase(frame):
    """Compra diaria por (fecha, proveedor).
    COMPRADA = ingreso − devolución  (lo realmente comprado ese día)
    TOTAL    = COMPRADA × precio del día
    DISPONIBLE = COMPRADA − merma    (kg utilizables tras limpieza)
    """
    cols = ["FECHA", "PROVEEDOR", "COMPRADA", "MERMA",
            "PRECIO", "TOTAL", "DISPONIBLE"]
    if frame.empty:
        return pd.DataFrame(columns=cols)
    recs = []
    for (fecha, prov), sub in frame.groupby([frame["FECHA"].dt.date, "PROVEEDOR"]):
        ing = sub.loc[sub["ESTADO_N"] == "INGRESO", "CANTIDAD"].sum()
        dev = sub.loc[sub["ESTADO_N"] == "DEVOLUCION", "CANTIDAD"].sum()
        mer = sub.loc[sub["ESTADO_N"] == "MERMA_LIMPIEZA", "CANTIDAD"].sum()
        ir = sub[sub["ESTADO_N"] == "INGRESO"]
        ki = ir["CANTIDAD"].sum()
        precio = (((ir["CANTIDAD"] * ir["PRECIO"]).sum() / ki)
                  if ki else np.nan)
        comprada = ing - dev
        total = comprada * precio if pd.notna(precio) else np.nan
        recs.append(dict(FECHA=fecha, PROVEEDOR=prov, COMPRADA=comprada,
                         MERMA=mer, PRECIO=precio, TOTAL=total,
                         DISPONIBLE=comprada - mer))
    return pd.DataFrame(recs)


def price_metrics(dp):
    """Métricas de precio agregadas sobre un DataFrame de compra diaria."""
    comprada = dp["COMPRADA"].sum() if not dp.empty else 0.0
    total = dp["TOTAL"].sum() if not dp.empty else 0.0
    merma = dp["MERMA"].sum() if not dp.empty else 0.0
    disponible = comprada - merma
    return dict(
        comprada=comprada, total=total, merma=merma, disponible=disponible,
        precio_pond=(total / comprada) if comprada else np.nan,
        pct_merma=(merma / comprada * 100) if comprada else np.nan,
        precio_post=(total / disponible) if disponible else np.nan,
    )


# ──────────────────────────────────────────────────────────────────────────
# CARGA + MANEJO DE ERRORES
# ──────────────────────────────────────────────────────────────────────────
st.title("🍓 Dashboard de Frutilla · Mermas y Precio")
st.caption("Control de calidad y costo por proveedor · Bolivianos (Bs) · "
           "datos en vivo (refresco cada 60 s)")

try:
    df = load_data()
except Exception as e:
    st.error(f"No se pudo cargar el Google Sheet. Verifica que esté "
             f"compartido como público.\n\nDetalle: {e}")
    st.stop()

if df.empty:
    st.warning("El sheet no contiene filas válidas.")
    st.stop()

# ──────────────────────────────────────────────────────────────────────────
# SIDEBAR · FILTROS
# ──────────────────────────────────────────────────────────────────────────
st.sidebar.header("⚙️ Filtros")

fmin, fmax = df["FECHA"].min().date(), df["FECHA"].max().date()
rango = st.sidebar.date_input(
    "Rango de fechas", value=(fmin, fmax), min_value=fmin, max_value=fmax,
)
if isinstance(rango, (list, tuple)) and len(rango) == 2:
    d_ini, d_fin = rango
else:
    d_ini, d_fin = fmin, fmax

provs = sorted(df["PROVEEDOR"].unique().tolist())
sel_prov = st.sidebar.multiselect("Proveedor", provs, default=provs)
if not sel_prov:
    sel_prov = provs

tipo = st.sidebar.radio(
    "Tipo de merma a mostrar (pestaña Mermas)",
    ["Ambas", "Devolución", "Limpieza"],
    index=0,
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    f"**Umbrales** (sobre utilizable)\n\n"
    f"🟢 Aceptable: ≤ {UMBRAL_ALERT:.0f}% (meta 10–11%)  \n"
    f"🟡 Alerta: {UMBRAL_ALERT:.0f}–{UMBRAL_CRIT:.1f}%  \n"
    f"🔴 Crítico: > {UMBRAL_CRIT:.1f}%"
)

# Filtro base (rango + proveedor)
mask = (
    (df["FECHA"].dt.date >= d_ini)
    & (df["FECHA"].dt.date <= d_fin)
    & (df["PROVEEDOR"].isin(sel_prov))
)
d = df[mask].copy()

if d.empty:
    st.warning("No hay datos para los filtros seleccionados.")
    st.stop()

# ──────────────────────────────────────────────────────────────────────────
# CÁLCULOS DE NEGOCIO (pestaña Mermas)
# ──────────────────────────────────────────────────────────────────────────
kg_ingreso = agg_kg(d, "INGRESO")
kg_devol = agg_kg(d, "DEVOLUCION")
kg_merma = agg_kg(d, "MERMA_LIMPIEZA")
kg_utilizable = kg_ingreso - kg_devol

costo_ingreso = agg_costo(d, "INGRESO")
costo_devol = agg_costo(d, "DEVOLUCION")
costo_merma = agg_costo(d, "MERMA_LIMPIEZA")

pct_merma_util = (kg_merma / kg_utilizable * 100) if kg_utilizable else 0.0

dias_rango = max((d_fin - d_ini).days + 1, 1)
runrate_merma_kg = kg_merma / dias_rango * 30
runrate_merma_bs = costo_merma / dias_rango * 30

# Proyección de cierre del mes en curso (mes más reciente dentro del filtro)
ult_fecha = d["FECHA"].max()
periodo_mes = ult_fecha.to_period("M")
md = d[d["FECHA"].dt.to_period("M") == periodo_mes]
md_util = agg_kg(md, "INGRESO") - agg_kg(md, "DEVOLUCION")
md_mer = agg_kg(md, "MERMA_LIMPIEZA")
pct_proj_mes = (md_mer / md_util * 100) if md_util else 0.0
factor_mes = periodo_mes.days_in_month / max(ult_fecha.day, 1)
proj_merma_bs_mes = agg_costo(md, "MERMA_LIMPIEZA") * factor_mes
cls_proj = cls_pct(pct_proj_mes)
NOMBRE_MES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
              7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}
mes_lbl = f"{NOMBRE_MES[ult_fecha.month]} {ult_fecha.year}"

# ══════════════════════════════════════════════════════════════════════════
# PESTAÑAS
# ══════════════════════════════════════════════════════════════════════════
tab_merma, tab_precio = st.tabs(["🍓 Mermas y calidad", "💵 Análisis de precio"])

# ==========================================================================
# TAB 1 · MERMAS Y CALIDAD
# ==========================================================================
with tab_merma:
    cls_merma = cls_pct(pct_merma_util)

    r1 = st.columns(5)
    r1[0].markdown(kpi("KG Utilizable", f"{kg_utilizable:,.0f}",
                       f"de {kg_ingreso:,.0f} kg recepcionados", "kpi-accent"),
                   unsafe_allow_html=True)
    r1[1].markdown(kpi("KG Merma Limpieza", f"{kg_merma:,.0f}",
                       f"Bs {costo_merma:,.0f} perdidos", "kpi-red"),
                   unsafe_allow_html=True)
    r1[2].markdown(kpi("% Merma s/ Utilizable", f"{pct_merma_util:.1f}%",
                       "Meta 10–11% · 🔴 crítico > 13.5%", cls_merma),
                   unsafe_allow_html=True)
    r1[3].markdown(kpi("Run Rate Merma / mes", f"Bs {runrate_merma_bs:,.0f}",
                       f"≈ {runrate_merma_kg:,.0f} kg/mes proyectado", "kpi-red"),
                   unsafe_allow_html=True)
    r1[4].markdown(kpi("Proyección cierre mes", f"{pct_proj_mes:.1f}%",
                       f"{mes_lbl} · ~Bs {proj_merma_bs_mes:,.0f} merma", cls_proj),
                   unsafe_allow_html=True)

    st.markdown("---")

    # GAUGE + ALERTAS
    g1, g2 = st.columns([1, 1.3])
    with g1:
        st.subheader("🎯 % Merma global vs umbral")
        gcolor = (C_RED if pct_merma_util >= UMBRAL_CRIT else
                  C_YELLOW if pct_merma_util >= UMBRAL_ALERT else C_GREEN)
        gmax = max(25, pct_merma_util * 1.2)
        fig_g = go.Figure(go.Indicator(
            mode="gauge+number",
            value=round(pct_merma_util, 2),
            number={"suffix": "%", "font": {"color": C_TEXT, "size": 40}},
            gauge={
                "axis": {"range": [0, gmax], "tickcolor": C_MUTED},
                "bar": {"color": gcolor},
                "bgcolor": C_PANEL, "borderwidth": 0,
                "steps": [
                    {"range": [0, UMBRAL_ALERT], "color": "rgba(34,197,94,.25)"},
                    {"range": [UMBRAL_ALERT, UMBRAL_CRIT], "color": "rgba(250,204,21,.25)"},
                    {"range": [UMBRAL_CRIT, gmax], "color": "rgba(239,68,68,.25)"},
                ],
                "threshold": {"line": {"color": C_RED, "width": 3},
                              "value": UMBRAL_CRIT},
            },
        ))
        fig_g.update_layout(template=PLOTLY_TEMPLATE, height=300,
                            paper_bgcolor="rgba(0,0,0,0)",
                            margin=dict(l=20, r=20, t=20, b=10))
        st.plotly_chart(fig_g, use_container_width=True)

    with g2:
        st.subheader("🚨 Alertas por proveedor")
        rows = []
        for p in sorted(d["PROVEEDOR"].unique()):
            sub = d[d["PROVEEDOR"] == p]
            util = agg_kg(sub, "INGRESO") - agg_kg(sub, "DEVOLUCION")
            mer = agg_kg(sub, "MERMA_LIMPIEZA")
            pct = (mer / util * 100) if util else 0.0
            rows.append((p, pct, agg_costo(sub, "MERMA_LIMPIEZA")))
        rows.sort(key=lambda x: x[1], reverse=True)

        any_alert = False
        for p, pct, cm in rows:
            if pct >= UMBRAL_CRIT:
                any_alert = True
                st.markdown(
                    f"<div class='alert-box alert-crit'>🔴 <b>{p}</b> — "
                    f"{pct:.1f}% merma · Bs {cm:,.0f} (CRÍTICO &gt; {UMBRAL_CRIT:.1f}%)</div>",
                    unsafe_allow_html=True)
            elif pct >= UMBRAL_ALERT:
                any_alert = True
                st.markdown(
                    f"<div class='alert-box alert-warn'>🟡 <b>{p}</b> — "
                    f"{pct:.1f}% merma · Bs {cm:,.0f} (alerta &gt; {UMBRAL_ALERT:.0f}%)</div>",
                    unsafe_allow_html=True)
        if not any_alert:
            st.markdown(
                "<div class='alert-box alert-ok'>✅ Ningún proveedor supera el "
                "umbral de alerta. Calidad bajo control.</div>",
                unsafe_allow_html=True)

    st.markdown("---")

    # EVOLUCIÓN DIARIA
    st.subheader("📈 Evolución diaria de mermas")
    daily = (d.pivot_table(index=d["FECHA"].dt.date, columns="ESTADO_N",
                           values="CANTIDAD", aggfunc="sum", fill_value=0)
               .reset_index())
    daily = daily.rename(columns={daily.columns[0]: "DIA"})
    for col in ["DEVOLUCION", "MERMA_LIMPIEZA"]:
        if col not in daily.columns:
            daily[col] = 0

    fig_d = go.Figure()
    if tipo in ("Ambas", "Limpieza"):
        fig_d.add_trace(go.Scatter(
            x=daily["DIA"], y=daily["MERMA_LIMPIEZA"], name="Merma limpieza",
            mode="lines", stackgroup="one", line=dict(color=C_RED, width=1.5),
            fillcolor="rgba(239,68,68,.35)",
            hovertemplate="%{x}<br>Merma limpieza: %{y:,.0f} kg<extra></extra>"))
    if tipo in ("Ambas", "Devolución"):
        fig_d.add_trace(go.Scatter(
            x=daily["DIA"], y=daily["DEVOLUCION"], name="Devolución",
            mode="lines", stackgroup="one", line=dict(color=C_YELLOW, width=1.5),
            fillcolor="rgba(250,204,21,.30)",
            hovertemplate="%{x}<br>Devolución: %{y:,.0f} kg<extra></extra>"))
    fig_d.update_layout(template=PLOTLY_TEMPLATE, height=350,
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        legend=dict(orientation="h", y=1.12, x=0),
                        margin=dict(l=10, r=10, t=30, b=10),
                        yaxis=dict(title="KG", gridcolor=C_GRID),
                        xaxis=dict(gridcolor=C_GRID))
    st.plotly_chart(fig_d, use_container_width=True)

    st.markdown("---")

    # RANKING PROVEEDORES
    st.subheader("🏆 Ranking de proveedores · ¿quién trae peor calidad?")
    prov_rows = []
    for p in sorted(d["PROVEEDOR"].unique()):
        sub = d[d["PROVEEDOR"] == p]
        ing = agg_kg(sub, "INGRESO")
        dev = agg_kg(sub, "DEVOLUCION")
        mer = agg_kg(sub, "MERMA_LIMPIEZA")
        util = ing - dev
        ir = sub[sub["ESTADO_N"] == "INGRESO"]
        ki = ir["CANTIDAD"].sum()
        precio_prom = (((ir["CANTIDAD"] * ir["PRECIO"]).sum() / ki)
                       if ki else np.nan)
        prov_rows.append({
            "Proveedor": p, "Precio Bs/kg": precio_prom,
            "KG Ingreso": ing, "KG Devuelto": dev, "KG Utilizable": util,
            "KG Merma": mer,
            "% Merma (util)": (mer / util * 100) if util else 0.0,
            "% Devol.": (dev / ing * 100) if ing else 0.0,
            "Costo Merma Bs": agg_costo(sub, "MERMA_LIMPIEZA"),
            "Costo Devol. Bs": agg_costo(sub, "DEVOLUCION"),
        })
    prov_df = pd.DataFrame(prov_rows)

    rk1, rk2 = st.columns(2)
    with rk1:
        pdf = prov_df.sort_values("% Merma (util)")
        colors = [C_RED if v >= UMBRAL_CRIT else C_YELLOW if v >= UMBRAL_ALERT
                  else C_GREEN for v in pdf["% Merma (util)"]]
        fig_r1 = go.Figure(go.Bar(
            x=pdf["% Merma (util)"], y=pdf["Proveedor"], orientation="h",
            marker_color=colors, text=[f"{v:.1f}%" for v in pdf["% Merma (util)"]],
            textposition="outside",
            hovertemplate="%{y}<br>%% Merma: %{x:.1f}%<extra></extra>"))
        fig_r1.add_vline(x=UMBRAL_CRIT, line_dash="dash", line_color=C_RED)
        fig_r1.add_vline(x=UMBRAL_ALERT, line_dash="dot", line_color=C_YELLOW)
        fig_r1.update_layout(template=PLOTLY_TEMPLATE, height=320,
                             title="% Merma sobre utilizable",
                             paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                             margin=dict(l=10, r=30, t=40, b=10),
                             xaxis=dict(gridcolor=C_GRID), yaxis=dict(gridcolor=C_GRID))
        st.plotly_chart(fig_r1, use_container_width=True)
    with rk2:
        pdf2 = prov_df.sort_values("Costo Merma Bs")
        fig_r2 = go.Figure(go.Bar(
            x=pdf2["Costo Merma Bs"], y=pdf2["Proveedor"], orientation="h",
            marker_color=C_CYAN, text=[f"Bs {v:,.0f}" for v in pdf2["Costo Merma Bs"]],
            textposition="outside",
            hovertemplate="%{y}<br>Costo merma: Bs %{x:,.0f}<extra></extra>"))
        fig_r2.update_layout(template=PLOTLY_TEMPLATE, height=320,
                             title="Costo de merma (Bs)",
                             paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                             margin=dict(l=10, r=40, t=40, b=10),
                             xaxis=dict(gridcolor=C_GRID), yaxis=dict(gridcolor=C_GRID))
        st.plotly_chart(fig_r2, use_container_width=True)

    tbl = prov_df.copy()
    tbl["Precio Bs/kg"] = tbl["Precio Bs/kg"].map(
        lambda v: f"Bs {v:,.2f}" if pd.notna(v) else "—")
    tbl["% Merma (util)"] = tbl["% Merma (util)"].map(lambda v: f"{v:.1f}%")
    tbl["% Devol."] = tbl["% Devol."].map(lambda v: f"{v:.1f}%")
    for c in ["KG Ingreso", "KG Devuelto", "KG Utilizable", "KG Merma"]:
        tbl[c] = tbl[c].map(lambda v: f"{v:,.0f}")
    for c in ["Costo Merma Bs", "Costo Devol. Bs"]:
        tbl[c] = tbl[c].map(lambda v: f"Bs {v:,.0f}")
    st.dataframe(tbl, use_container_width=True, hide_index=True)

    st.markdown("---")

    # SEMANA VS SEMANA
    st.subheader("📊 Comparativo semana vs semana")
    wk = (d.groupby(["SEMANA", "ESTADO_N"])["CANTIDAD"].sum()
            .unstack(fill_value=0).reset_index())
    for c in ["INGRESO", "DEVOLUCION", "MERMA_LIMPIEZA"]:
        if c not in wk.columns:
            wk[c] = 0
    wk["UTILIZABLE"] = wk["INGRESO"] - wk["DEVOLUCION"]
    wk["% MERMA"] = np.where(wk["UTILIZABLE"] > 0,
                             wk["MERMA_LIMPIEZA"] / wk["UTILIZABLE"] * 100, 0)
    wk["SEM_LBL"] = wk["SEMANA"].dt.strftime("%d/%m")

    fig_w = go.Figure()
    fig_w.add_trace(go.Bar(
        x=wk["SEM_LBL"], y=wk["MERMA_LIMPIEZA"], name="Merma limpieza (kg)",
        marker_color=C_RED,
        hovertemplate="Semana %{x}<br>Merma limpieza: %{y:,.0f} kg<extra></extra>"))
    fig_w.add_trace(go.Bar(
        x=wk["SEM_LBL"], y=wk["DEVOLUCION"], name="Devolución (kg)",
        marker_color=C_YELLOW,
        hovertemplate="Semana %{x}<br>Devolución: %{y:,.0f} kg<extra></extra>"))
    fig_w.add_trace(go.Scatter(
        x=wk["SEM_LBL"], y=wk["% MERMA"], name="% Merma util",
        mode="lines+markers", yaxis="y2", line=dict(color=C_CYAN, width=3),
        hovertemplate="Semana %{x}<br>%% Merma util: %{y:.1f}%<extra></extra>"))
    fig_w.update_layout(
        template=PLOTLY_TEMPLATE, height=380, barmode="group", hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.12, x=0),
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(title="Semana (inicio)", gridcolor=C_GRID),
        yaxis=dict(title="KG", gridcolor=C_GRID),
        yaxis2=dict(title="% Merma", overlaying="y", side="right",
                    showgrid=False, ticksuffix="%"))
    st.plotly_chart(fig_w, use_container_width=True)

    st.caption(
        "Nota: el **% de merma** se calcula sobre el **KG utilizable** "
        "(Ingreso − Devolución). La devolución se descuenta de la factura y "
        "no es pérdida. Costos = CANTIDAD × PRECIO DE COMPRA (Bs)."
    )

# ==========================================================================
# TAB 2 · ANÁLISIS DE PRECIO
# ==========================================================================
with tab_precio:
    st.caption(
        "Base de cálculo: **compra diaria = recibido − devolución**; "
        "**total del día = cantidad comprada × precio del día**. "
        "Filtra por proveedor y rango en la barra lateral."
    )

    dp = daily_purchase(d)
    m = price_metrics(dp)
    sobrecosto = (m["precio_post"] - m["precio_pond"]
                  if pd.notna(m["precio_post"]) and pd.notna(m["precio_pond"])
                  else np.nan)
    sobrecosto_pct = (sobrecosto / m["precio_pond"] * 100
                      if pd.notna(sobrecosto) and m["precio_pond"] else np.nan)
    perdida_bs = m["merma"] * m["precio_pond"] if pd.notna(m["precio_pond"]) else 0.0

    st.subheader(f"💵 Periodo seleccionado · {d_ini:%d/%m/%Y} → {d_fin:%d/%m/%Y}")
    cA = st.columns(4)
    cA[0].markdown(kpi("Precio ponderado compra",
                       f"Bs {m['precio_pond']:,.2f}/kg",
                       "total invertido ÷ kg comprados", "kpi-accent"),
                   unsafe_allow_html=True)
    cA[1].markdown(kpi("Cantidad comprada", f"{m['comprada']:,.0f} kg",
                       f"Bs {m['total']:,.0f} invertidos", "kpi-green"),
                   unsafe_allow_html=True)
    cA[2].markdown(kpi("% Merma del periodo", f"{m['pct_merma']:.1f}%",
                       f"{m['merma']:,.0f} kg de merma", cls_pct(m['pct_merma'])),
                   unsafe_allow_html=True)
    cA[3].markdown(kpi("Precio real post-merma",
                       f"Bs {m['precio_post']:,.2f}/kg",
                       f"sobre {m['disponible']:,.0f} kg disponibles", "kpi-red"),
                   unsafe_allow_html=True)

    if pd.notna(sobrecosto):
        st.markdown(
            f"<div class='alert-box alert-info'>💡 Por la merma, el costo real "
            f"del kg sube de <b>Bs {m['precio_pond']:,.2f}</b> a "
            f"<b>Bs {m['precio_post']:,.2f}</b> "
            f"(+Bs {sobrecosto:,.2f}/kg · +{sobrecosto_pct:.1f}%). "
            f"Dinero perdido en merma: <b>Bs {perdida_bs:,.0f}</b>.</div>",
            unsafe_allow_html=True)

    st.markdown("---")

    # EVOLUCIÓN DEL PRECIO PONDERADO + VOLUMEN COMPRADO
    st.subheader("📈 Evolución del precio ponderado y volumen comprado")
    day = (dp.groupby("FECHA")
             .agg(COMPRADA=("COMPRADA", "sum"), TOTAL=("TOTAL", "sum"),
                  MERMA=("MERMA", "sum"))
             .reset_index().sort_values("FECHA"))
    day["PRECIO_POND"] = np.where(day["COMPRADA"] > 0,
                                  day["TOTAL"] / day["COMPRADA"], np.nan)
    fig_pe = go.Figure()
    fig_pe.add_trace(go.Bar(
        x=day["FECHA"], y=day["COMPRADA"], name="KG comprados",
        marker_color="rgba(0,245,212,.30)",
        hovertemplate="%{x}<br>Comprado: %{y:,.0f} kg<extra></extra>"))
    fig_pe.add_trace(go.Scatter(
        x=day["FECHA"], y=day["PRECIO_POND"], name="Precio ponderado (Bs/kg)",
        mode="lines+markers", yaxis="y2", line=dict(color=C_CYAN, width=3),
        hovertemplate="%{x}<br>Precio: Bs %{y:,.2f}/kg<extra></extra>"))
    fig_pe.update_layout(
        template=PLOTLY_TEMPLATE, height=380, hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.12, x=0),
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(gridcolor=C_GRID),
        yaxis=dict(title="KG comprados", gridcolor=C_GRID),
        yaxis2=dict(title="Bs/kg", overlaying="y", side="right", showgrid=False))
    st.plotly_chart(fig_pe, use_container_width=True)

    st.markdown("---")

    # PRECIO PONDERADO Y POST-MERMA POR PROVEEDOR
    st.subheader("🏷️ Precio por proveedor · compra vs real post-merma")
    pp = (dp.groupby("PROVEEDOR")
            .agg(COMPRADA=("COMPRADA", "sum"), TOTAL=("TOTAL", "sum"),
                 MERMA=("MERMA", "sum"))
            .reset_index())
    pp["PRECIO_POND"] = np.where(pp["COMPRADA"] > 0,
                                 pp["TOTAL"] / pp["COMPRADA"], np.nan)
    pp["DISP"] = pp["COMPRADA"] - pp["MERMA"]
    pp["PRECIO_POST"] = np.where(pp["DISP"] > 0, pp["TOTAL"] / pp["DISP"], np.nan)
    pp["% MERMA"] = np.where(pp["COMPRADA"] > 0,
                             pp["MERMA"] / pp["COMPRADA"] * 100, 0)
    pp = pp.sort_values("PRECIO_POND")

    fig_pv = go.Figure()
    fig_pv.add_trace(go.Bar(
        x=pp["PROVEEDOR"], y=pp["PRECIO_POND"], name="Precio compra",
        marker_color=C_CYAN,
        hovertemplate="%{x}<br>Compra: Bs %{y:,.2f}/kg<extra></extra>"))
    fig_pv.add_trace(go.Bar(
        x=pp["PROVEEDOR"], y=pp["PRECIO_POST"], name="Precio real post-merma",
        marker_color=C_RED,
        hovertemplate="%{x}<br>Post-merma: Bs %{y:,.2f}/kg<extra></extra>"))
    fig_pv.update_layout(
        template=PLOTLY_TEMPLATE, height=360, barmode="group",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.12, x=0),
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(gridcolor=C_GRID),
        yaxis=dict(title="Bs/kg", gridcolor=C_GRID))
    st.plotly_chart(fig_pv, use_container_width=True)

    # Mejor precio real (post-merma)
    pp_valid = pp.dropna(subset=["PRECIO_POST"])
    if not pp_valid.empty:
        best = pp_valid.sort_values("PRECIO_POST").iloc[0]
        st.markdown(
            f"<div class='alert-box alert-ok'>🏅 <b>Mejor precio real "
            f"(ya descontada la merma): {best['PROVEEDOR']}</b> — "
            f"Bs {best['PRECIO_POST']:,.2f}/kg "
            f"(compra Bs {best['PRECIO_POND']:,.2f}/kg · {best['% MERMA']:.1f}% merma)</div>",
            unsafe_allow_html=True)

    ppt = pp[["PROVEEDOR", "PRECIO_POND", "PRECIO_POST", "COMPRADA",
              "MERMA", "% MERMA", "TOTAL"]].copy()
    ppt.columns = ["Proveedor", "Precio compra", "Precio post-merma",
                   "KG comprado", "KG merma", "% Merma", "Total Bs"]
    ppt["Precio compra"] = ppt["Precio compra"].map(lambda v: f"Bs {v:,.2f}")
    ppt["Precio post-merma"] = ppt["Precio post-merma"].map(
        lambda v: f"Bs {v:,.2f}" if pd.notna(v) else "—")
    ppt["KG comprado"] = ppt["KG comprado"].map(lambda v: f"{v:,.0f}")
    ppt["KG merma"] = ppt["KG merma"].map(lambda v: f"{v:,.0f}")
    ppt["% Merma"] = ppt["% Merma"].map(lambda v: f"{v:.1f}%")
    ppt["Total Bs"] = ppt["Total Bs"].map(lambda v: f"Bs {v:,.0f}")
    st.dataframe(ppt, use_container_width=True, hide_index=True)

    st.markdown("---")

    # COMPARADOR DE DOS RANGOS
    st.subheader("🆚 Comparar dos rangos de fecha")
    st.caption("Compara precio, volumen y merma entre dos periodos "
               "(respeta el filtro de proveedor de la barra lateral).")

    total_days = (fmax - fmin).days
    mid = fmin + timedelta(days=total_days // 2)
    cc = st.columns(2)
    with cc[0]:
        rA = st.date_input("Rango A", value=(fmin, mid),
                           min_value=fmin, max_value=fmax, key="rA")
    with cc[1]:
        rB = st.date_input("Rango B", value=(mid + timedelta(days=1), fmax),
                           min_value=fmin, max_value=fmax, key="rB")

    def _norm_range(r):
        if isinstance(r, (list, tuple)) and len(r) == 2:
            return r[0], r[1]
        return r, r

    aI, aF = _norm_range(rA)
    bI, bF = _norm_range(rB)

    def frame_range(a, b):
        mm = ((df["FECHA"].dt.date >= a) & (df["FECHA"].dt.date <= b)
              & (df["PROVEEDOR"].isin(sel_prov)))
        return df[mm]

    mA = price_metrics(daily_purchase(frame_range(aI, aF)))
    mB = price_metrics(daily_purchase(frame_range(bI, bF)))

    def fmt(v, kind):
        if pd.isna(v):
            return "—"
        if kind == "bs":
            return f"Bs {v:,.2f}"
        if kind == "bs0":
            return f"Bs {v:,.0f}"
        if kind == "kg":
            return f"{v:,.0f} kg"
        if kind == "pct":
            return f"{v:.1f}%"
        return f"{v}"

    filas = [
        ("Precio ponderado compra", "precio_pond", "bs"),
        ("Precio real post-merma", "precio_post", "bs"),
        ("Cantidad comprada", "comprada", "kg"),
        ("% Merma del periodo", "pct_merma", "pct"),
        ("Total invertido", "total", "bs0"),
    ]
    comp_rows = []
    for lbl, key, kind in filas:
        va, vb = mA[key], mB[key]
        delta = (vb - va) if (pd.notna(va) and pd.notna(vb)) else np.nan
        if kind == "pct":
            delta_str = f"{delta:+.1f} pp" if pd.notna(delta) else "—"
        elif kind == "kg":
            delta_str = f"{delta:+,.0f} kg" if pd.notna(delta) else "—"
        elif kind == "bs0":
            delta_str = f"{delta:+,.0f} Bs" if pd.notna(delta) else "—"
        else:
            delta_str = f"{delta:+,.2f} Bs" if pd.notna(delta) else "—"
        comp_rows.append({
            "Métrica": lbl,
            f"A ({aI:%d/%m}–{aF:%d/%m})": fmt(va, kind),
            f"B ({bI:%d/%m}–{bF:%d/%m})": fmt(vb, kind),
            "Δ (B − A)": delta_str,
        })
    st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)

    # Barras comparativas de precio
    cats = ["Precio compra", "Precio post-merma"]
    fig_cmp = go.Figure()
    fig_cmp.add_trace(go.Bar(
        x=cats, y=[mA["precio_pond"], mA["precio_post"]], name="Rango A",
        marker_color=C_CYAN,
        hovertemplate="A · %{x}: Bs %{y:,.2f}/kg<extra></extra>"))
    fig_cmp.add_trace(go.Bar(
        x=cats, y=[mB["precio_pond"], mB["precio_post"]], name="Rango B",
        marker_color=C_YELLOW,
        hovertemplate="B · %{x}: Bs %{y:,.2f}/kg<extra></extra>"))
    fig_cmp.update_layout(
        template=PLOTLY_TEMPLATE, height=340, barmode="group",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.15, x=0),
        margin=dict(l=10, r=10, t=30, b=10),
        yaxis=dict(title="Bs/kg", gridcolor=C_GRID),
        xaxis=dict(gridcolor=C_GRID))
    st.plotly_chart(fig_cmp, use_container_width=True)

    if pd.notna(mA["precio_pond"]) and pd.notna(mB["precio_pond"]):
        dif = mB["precio_pond"] - mA["precio_pond"]
        signo = "subió" if dif > 0 else "bajó"
        st.markdown(
            f"<div class='alert-box alert-info'>El precio de compra {signo} "
            f"<b>Bs {abs(dif):,.2f}/kg</b> de A a B. "
            f"El precio real post-merma pasó de Bs {mA['precio_post']:,.2f} a "
            f"Bs {mB['precio_post']:,.2f}/kg.</div>",
            unsafe_allow_html=True)
