"""
Dashboard BI - Control de Mermas de Frutilla
Estilo dark navy / cyan. Conectado a Google Sheets (CSV export).
Compatible con Streamlit Community Cloud.
"""

import re
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

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

        hr {{ border-color: {C_GRID}; }}
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
    # quitar 'Bs', espacios y separadores de miles
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

    # Mapeo flexible de nombres de columnas
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

    # Parseo
    df["FECHA"] = pd.to_datetime(df["FECHA"], format="%d/%m/%Y", errors="coerce")
    df["CANTIDAD"] = df["CANTIDAD"].apply(parse_qty)
    df["PRECIO"] = df["PRECIO"].apply(parse_money)
    df["TOTAL"] = df["TOTAL"].apply(parse_money)
    df["PROVEEDOR"] = df["PROVEEDOR"].astype(str).str.strip().str.upper()
    df["ESTADO_N"] = df["ESTADO"].apply(norm_estado)

    # Costo por fila: usa CANTIDAD × PRECIO; fallback al TOTAL del sheet
    df["COSTO"] = df["CANTIDAD"] * df["PRECIO"]
    df["COSTO"] = df["COSTO"].fillna(df["TOTAL"])

    # Limpiar filas vacías / inválidas
    df = df[df["FECHA"].notna()]
    df = df[df["CANTIDAD"].notna() & (df["CANTIDAD"] > 0)]
    df = df[df["ESTADO_N"].isin(["INGRESO", "DEVOLUCION", "MERMA_LIMPIEZA"])]
    df = df[df["PROVEEDOR"].notna() & (df["PROVEEDOR"] != "") &
            (df["PROVEEDOR"] != "NAN")]

    df["SEMANA"] = df["FECHA"].dt.to_period("W").apply(lambda p: p.start_time)
    df["MES"] = df["FECHA"].dt.to_period("M").astype(str)
    return df.reset_index(drop=True)


# ──────────────────────────────────────────────────────────────────────────
# CARGA + MANEJO DE ERRORES
# ──────────────────────────────────────────────────────────────────────────
st.title("🍓 Dashboard de Mermas · Frutilla")
st.caption("Control de calidad por proveedor · Bolivianos (Bs) · "
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

tipo = st.sidebar.radio(
    "Tipo de merma a mostrar",
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

# Aplicar filtros base (fecha + proveedor)
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
# CÁLCULOS DE NEGOCIO
# Utilizable = INGRESO − DEVOLUCIÓN
# % merma limpieza = MERMA_LIMPIEZA / UTILIZABLE
# La DEVOLUCIÓN no es pérdida (se descuenta de factura)
# ──────────────────────────────────────────────────────────────────────────
def agg_kg(frame, estado):
    return frame.loc[frame["ESTADO_N"] == estado, "CANTIDAD"].sum()

def agg_costo(frame, estado):
    return frame.loc[frame["ESTADO_N"] == estado, "COSTO"].sum()

kg_ingreso = agg_kg(d, "INGRESO")
kg_devol = agg_kg(d, "DEVOLUCION")
kg_merma = agg_kg(d, "MERMA_LIMPIEZA")
kg_utilizable = kg_ingreso - kg_devol

costo_ingreso = agg_costo(d, "INGRESO")
costo_devol = agg_costo(d, "DEVOLUCION")
costo_merma = agg_costo(d, "MERMA_LIMPIEZA")

pct_merma_global = (kg_merma / kg_ingreso * 100) if kg_ingreso else 0.0       # sobre recepcionado
pct_devol = (kg_devol / kg_ingreso * 100) if kg_ingreso else 0.0
pct_merma_util = (kg_merma / kg_utilizable * 100) if kg_utilizable else 0.0   # sobre utilizable (definición oficial)

# Run rate mensual (ritmo proyectado a 30 días sobre el rango filtrado)
dias_rango = max((d_fin - d_ini).days + 1, 1)
runrate_merma_kg = kg_merma / dias_rango * 30
runrate_merma_bs = costo_merma / dias_rango * 30
runrate_devol_kg = kg_devol / dias_rango * 30
runrate_devol_bs = costo_devol / dias_rango * 30

# ──────────────────────────────────────────────────────────────────────────
# KPIs
# ──────────────────────────────────────────────────────────────────────────
def kpi(label, value, sub="", cls="kpi-accent"):
    return (
        f"<div class='kpi-card'>"
        f"<div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value {cls}'>{value}</div>"
        f"<div class='kpi-sub'>{sub}</div></div>"
    )

cls_merma = "kpi-red" if pct_merma_util >= UMBRAL_CRIT else (
    "kpi-yellow" if pct_merma_util >= UMBRAL_ALERT else "kpi-green")

r1 = st.columns(4)
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

st.markdown("---")

# ──────────────────────────────────────────────────────────────────────────
# GAUGE + ALERTAS
# ──────────────────────────────────────────────────────────────────────────
g1, g2 = st.columns([1, 1.3])

with g1:
    st.subheader("🎯 % Merma global vs umbral")
    gcolor = (C_RED if pct_merma_util >= UMBRAL_CRIT else
              C_YELLOW if pct_merma_util >= UMBRAL_ALERT else C_GREEN)
    fig_g = go.Figure(go.Indicator(
        mode="gauge+number",
        value=round(pct_merma_util, 2),
        number={"suffix": "%", "font": {"color": C_TEXT, "size": 40}},
        gauge={
            "axis": {"range": [0, max(25, pct_merma_util * 1.2)],
                     "tickcolor": C_MUTED},
            "bar": {"color": gcolor},
            "bgcolor": C_PANEL,
            "borderwidth": 0,
            "steps": [
                {"range": [0, UMBRAL_ALERT], "color": "rgba(34,197,94,.25)"},
                {"range": [UMBRAL_ALERT, UMBRAL_CRIT], "color": "rgba(250,204,21,.25)"},
                {"range": [UMBRAL_CRIT, max(25, pct_merma_util * 1.2)],
                 "color": "rgba(239,68,68,.25)"},
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
    # % merma sobre utilizable por proveedor
    rows = []
    for p in sorted(d["PROVEEDOR"].unique()):
        sub = d[d["PROVEEDOR"] == p]
        ing = agg_kg(sub, "INGRESO")
        dev = agg_kg(sub, "DEVOLUCION")
        mer = agg_kg(sub, "MERMA_LIMPIEZA")
        util = ing - dev
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

# ──────────────────────────────────────────────────────────────────────────
# EVOLUCIÓN DIARIA (área: devoluciones vs merma limpieza)
# ──────────────────────────────────────────────────────────────────────────
st.subheader("📈 Evolución diaria de mermas")

daily = (d.pivot_table(index=d["FECHA"].dt.date, columns="ESTADO_N",
                       values="CANTIDAD", aggfunc="sum", fill_value=0)
           .reset_index().rename(columns={"index": "FECHA"}))
for col in ["DEVOLUCION", "MERMA_LIMPIEZA"]:
    if col not in daily.columns:
        daily[col] = 0
daily = daily.rename(columns={"FECHA": "DIA"})
if "DIA" not in daily.columns:
    daily = daily.rename(columns={daily.columns[0]: "DIA"})

fig_d = go.Figure()
if tipo in ("Ambas", "Limpieza"):
    fig_d.add_trace(go.Scatter(
        x=daily["DIA"], y=daily["MERMA_LIMPIEZA"], name="Merma limpieza",
        mode="lines", stackgroup="one", line=dict(color=C_RED, width=1.5),
        fillcolor="rgba(239,68,68,.35)"))
if tipo in ("Ambas", "Devolución"):
    fig_d.add_trace(go.Scatter(
        x=daily["DIA"], y=daily["DEVOLUCION"], name="Devolución",
        mode="lines", stackgroup="one", line=dict(color=C_YELLOW, width=1.5),
        fillcolor="rgba(250,204,21,.30)"))
fig_d.update_layout(template=PLOTLY_TEMPLATE, height=350,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    legend=dict(orientation="h", y=1.12, x=0),
                    margin=dict(l=10, r=10, t=30, b=10),
                    yaxis=dict(title="KG", gridcolor=C_GRID),
                    xaxis=dict(gridcolor=C_GRID))
st.plotly_chart(fig_d, use_container_width=True)

st.markdown("---")

# ──────────────────────────────────────────────────────────────────────────
# RANKING PROVEEDORES (% merma y costo)
# ──────────────────────────────────────────────────────────────────────────
st.subheader("🏆 Ranking de proveedores · ¿quién trae peor calidad?")

prov_rows = []
for p in sorted(d["PROVEEDOR"].unique()):
    sub = d[d["PROVEEDOR"] == p]
    ing = agg_kg(sub, "INGRESO")
    dev = agg_kg(sub, "DEVOLUCION")
    mer = agg_kg(sub, "MERMA_LIMPIEZA")
    util = ing - dev
    prov_rows.append({
        "Proveedor": p,
        "KG Ingreso": ing,
        "KG Devuelto": dev,
        "KG Utilizable": util,
        "KG Merma": mer,
        "% Merma (util)": (mer / util * 100) if util else 0.0,
        "% Devol.": (dev / ing * 100) if ing else 0.0,
        "Costo Merma Bs": agg_costo(sub, "MERMA_LIMPIEZA"),
        "Costo Devol. Bs": agg_costo(sub, "DEVOLUCION"),
    })
prov_df = pd.DataFrame(prov_rows)

rk1, rk2 = st.columns(2)
with rk1:
    pdf = prov_df.sort_values("% Merma (util)", ascending=True)
    colors = [C_RED if v >= UMBRAL_CRIT else C_YELLOW if v >= UMBRAL_ALERT
              else C_GREEN for v in pdf["% Merma (util)"]]
    fig_r1 = go.Figure(go.Bar(
        x=pdf["% Merma (util)"], y=pdf["Proveedor"], orientation="h",
        marker_color=colors,
        text=[f"{v:.1f}%" for v in pdf["% Merma (util)"]],
        textposition="outside"))
    fig_r1.add_vline(x=UMBRAL_CRIT, line_dash="dash", line_color=C_RED)
    fig_r1.add_vline(x=UMBRAL_ALERT, line_dash="dot", line_color=C_YELLOW)
    fig_r1.update_layout(template=PLOTLY_TEMPLATE, height=320,
                         title="% Merma sobre utilizable",
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                         margin=dict(l=10, r=30, t=40, b=10),
                         xaxis=dict(gridcolor=C_GRID), yaxis=dict(gridcolor=C_GRID))
    st.plotly_chart(fig_r1, use_container_width=True)

with rk2:
    pdf2 = prov_df.sort_values("Costo Merma Bs", ascending=True)
    fig_r2 = go.Figure(go.Bar(
        x=pdf2["Costo Merma Bs"], y=pdf2["Proveedor"], orientation="h",
        marker_color=C_CYAN,
        text=[f"Bs {v:,.0f}" for v in pdf2["Costo Merma Bs"]],
        textposition="outside"))
    fig_r2.update_layout(template=PLOTLY_TEMPLATE, height=320,
                         title="Costo de merma (Bs)",
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                         margin=dict(l=10, r=40, t=40, b=10),
                         xaxis=dict(gridcolor=C_GRID), yaxis=dict(gridcolor=C_GRID))
    st.plotly_chart(fig_r2, use_container_width=True)

# Tabla detalle proveedores
tbl = prov_df.copy()
tbl["% Merma (util)"] = tbl["% Merma (util)"].map(lambda v: f"{v:.1f}%")
tbl["% Devol."] = tbl["% Devol."].map(lambda v: f"{v:.1f}%")
for c in ["KG Ingreso", "KG Devuelto", "KG Utilizable", "KG Merma"]:
    tbl[c] = tbl[c].map(lambda v: f"{v:,.0f}")
for c in ["Costo Merma Bs", "Costo Devol. Bs"]:
    tbl[c] = tbl[c].map(lambda v: f"Bs {v:,.0f}")
st.dataframe(tbl, use_container_width=True, hide_index=True)

st.markdown("---")

# ──────────────────────────────────────────────────────────────────────────
# SEMANA VS SEMANA
# ──────────────────────────────────────────────────────────────────────────
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
fig_w.add_trace(go.Bar(x=wk["SEM_LBL"], y=wk["MERMA_LIMPIEZA"],
                       name="Merma limpieza (kg)", marker_color=C_RED))
fig_w.add_trace(go.Bar(x=wk["SEM_LBL"], y=wk["DEVOLUCION"],
                       name="Devolución (kg)", marker_color=C_YELLOW))
fig_w.add_trace(go.Scatter(x=wk["SEM_LBL"], y=wk["% MERMA"], name="% Merma util",
                           mode="lines+markers", yaxis="y2",
                           line=dict(color=C_CYAN, width=3)))
fig_w.update_layout(
    template=PLOTLY_TEMPLATE, height=380, barmode="group",
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    legend=dict(orientation="h", y=1.12, x=0),
    margin=dict(l=10, r=10, t=30, b=10),
    xaxis=dict(title="Semana (inicio)", gridcolor=C_GRID),
    yaxis=dict(title="KG", gridcolor=C_GRID),
    yaxis2=dict(title="% Merma", overlaying="y", side="right",
                showgrid=False, ticksuffix="%"))
st.plotly_chart(fig_w, use_container_width=True)

st.markdown("---")

st.caption(
    "Nota metodológica: el **% de merma por limpieza** se calcula sobre el "
    "**KG utilizable** (Ingreso − Devolución), porque la devolución se "
    "descuenta de la factura y no representa pérdida. Los costos usan "
    "CANTIDAD × PRECIO DE COMPRA en Bs."
)
