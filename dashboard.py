"""
Crop Intelligence Dashboard — South Karnataka Dry Zone
Clean, high-contrast design — readable on all screens
"""

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from crop_agent.config.settings import (
    DISTRICT_TALUKS_MAP,
    MANDYA_TALUKS,
    SOUTH_KARNATAKA_DRY_ZONE_TALUKS,
    TALUK_TO_DISTRICT,
)
from crop_agent.database.connection import engine

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🌾 Crop Intelligence — South Karnataka",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CLEAN HIGH-CONTRAST CSS ───────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

* { font-family: 'Inter', sans-serif !important; }

/* Light background for main area */
.main .block-container {
    background: #f0f2f6;
    padding: 1.5rem 2rem;
}
.stApp { background: #f0f2f6; }

/* Sidebar — dark green theme, high contrast */
section[data-testid="stSidebar"] {
    background: #1a472a !important;
}
section[data-testid="stSidebar"] * {
    color: #ffffff !important;
}
section[data-testid="stSidebar"] .stSelectbox > div > div {
    background: #2d6a4f !important;
    color: #ffffff !important;
    border: 1px solid #40916c !important;
}
section[data-testid="stSidebar"] label {
    color: #b7e4c7 !important;
    font-weight: 600 !important;
    font-size: 12px !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
    color: #ffffff !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    padding: 6px 0;
}

/* Metric cards — white with strong text */
div[data-testid="metric-container"] {
    background: #ffffff;
    border: none;
    border-radius: 14px;
    padding: 18px 22px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    border-left: 4px solid #2d6a4f;
}
div[data-testid="metric-container"] label {
    color: #4a5568 !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}
div[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #1a202c !important;
    font-size: 28px !important;
    font-weight: 800 !important;
}

/* Section headers */
.sec-header {
    font-size: 20px;
    font-weight: 700;
    color: #1a202c;
    margin: 20px 0 10px 0;
    padding-bottom: 8px;
    border-bottom: 3px solid #2d6a4f;
    display: inline-block;
}

/* Alert cards */
.card-red {
    background: #fff5f5;
    border: 1.5px solid #fc8181;
    border-left: 5px solid #e53e3e;
    border-radius: 10px;
    padding: 12px 16px;
    margin: 6px 0;
    color: #742a2a;
    font-size: 14px;
    font-weight: 500;
}
.card-green {
    background: #f0fff4;
    border: 1.5px solid #68d391;
    border-left: 5px solid #38a169;
    border-radius: 10px;
    padding: 12px 16px;
    margin: 6px 0;
    color: #1c4532;
    font-size: 14px;
    font-weight: 500;
}
.card-yellow {
    background: #fffff0;
    border: 1.5px solid #f6e05e;
    border-left: 5px solid #d69e2e;
    border-radius: 10px;
    padding: 12px 16px;
    margin: 6px 0;
    color: #744210;
    font-size: 14px;
    font-weight: 500;
}
.card-blue {
    background: #ebf8ff;
    border: 1.5px solid #63b3ed;
    border-left: 5px solid #3182ce;
    border-radius: 10px;
    padding: 12px 16px;
    margin: 6px 0;
    color: #1a365d;
    font-size: 14px;
    font-weight: 500;
}

/* NDVI progress bars */
.ndvi-row {
    background: #ffffff;
    border-radius: 10px;
    padding: 10px 14px;
    margin: 4px 0;
    box-shadow: 0 1px 6px rgba(0,0,0,0.06);
}
.ndvi-label-row {
    display: flex;
    justify-content: space-between;
    margin-bottom: 5px;
}
.ndvi-name { font-size: 13px; font-weight: 600; color: #2d3748; }
.ndvi-val  { font-size: 13px; font-weight: 700; }
.ndvi-bg {
    background: #e2e8f0;
    border-radius: 6px;
    height: 18px;
    overflow: hidden;
}
.ndvi-fill {
    height: 100%;
    border-radius: 6px;
    transition: width 0.4s;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    background: #ffffff;
    border-radius: 12px;
    padding: 6px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: #4a5568 !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
}
.stTabs [aria-selected="true"] {
    background: #2d6a4f !important;
    color: #ffffff !important;
}

/* Forecast day cards */
.forecast-card {
    background: #ffffff;
    border-radius: 12px;
    padding: 14px 10px;
    text-align: center;
    box-shadow: 0 2px 10px rgba(0,0,0,0.08);
    border-top: 4px solid #2d6a4f;
}
.fc-day   { font-size: 11px; font-weight: 600; color: #718096; text-transform: uppercase; }
.fc-date  { font-size: 14px; font-weight: 700; color: #1a202c; }
.fc-icon  { font-size: 28px; margin: 4px 0; }
.fc-tmax  { font-size: 18px; font-weight: 800; color: #e53e3e; }
.fc-tmin  { font-size: 13px; font-weight: 600; color: #3182ce; }
.fc-rain  { font-size: 12px; color: #2b6cb0; margin-top: 4px; }

/* Crop tag chips */
.crop-chip {
    display: inline-block;
    background: #ebf8f1;
    border: 1.5px solid #48bb78;
    border-radius: 20px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 600;
    color: #276749;
    margin: 4px;
}
</style>
""", unsafe_allow_html=True)

# ── PLOTLY COMMON LAYOUT (light theme) ───────────────────────────────────────
PLOT_LAYOUT = dict(
    paper_bgcolor="#ffffff",
    plot_bgcolor="#f7fafc",
    font=dict(color="#2d3748", family="Inter"),
    title_font=dict(size=16, color="#1a202c"),
    margin=dict(l=10, r=10, t=45, b=10),
)

def apply_layout(fig, title="", height=420):
    fig.update_layout(
        **PLOT_LAYOUT,
        title=title,
        height=height,
        legend=dict(bgcolor="#f7fafc", bordercolor="#e2e8f0", borderwidth=1),
    )
    fig.update_xaxes(showgrid=False, linecolor="#e2e8f0")
    fig.update_yaxes(showgrid=True, gridcolor="#e2e8f0")
    return fig

# ── TALUK COORDINATES ─────────────────────────────────────────────────────────
TALUK_COORDS = {
    "Mandya":(12.5234,76.8961),"Maddur":(12.5807,77.0466),"Malavalli":(12.3847,77.0607),
    "Nagamangala":(12.8156,76.7497),"Pandavapura":(12.4872,76.6839),
    "Shrirangapattana":(12.4165,76.6951),"Krishnarajapete":(12.6585,76.3887),
    "Mysuru":(12.2958,76.6394),"Hunsur":(12.3046,76.2928),"Nanjangud":(12.1139,76.6828),
    "T. Narasipura":(12.2135,76.9162),"Periyapatna":(12.3318,76.0507),"H.D. Kote":(12.0447,76.0025),
    "Chamarajanagar":(11.9238,76.9434),"Gundlupet":(11.8085,76.6914),
    "Kollegal":(12.1578,77.1085),"Yelandur":(11.9862,77.0373),
    "Ramanagara":(12.7157,77.2804),"Channapatna":(12.6509,77.2068),
    "Kanakapura":(12.5460,77.4183),"Magadi":(12.9572,77.2268),
    "Devanahalli":(13.2456,77.7120),"Doddaballapura":(13.2951,77.5378),
    "Hosakote":(13.0701,77.7980),"Nelamangala":(13.1006,77.3919),
    "Kolar":(13.1360,78.1294),"Malur":(13.0023,77.9387),"Mulbagal":(13.1630,78.3960),
    "Srinivaspur":(13.3350,78.2107),"Bangarpet":(12.9860,78.1796),
    "Chikkaballapura":(13.4354,77.7268),"Bagepalli":(13.7862,77.7877),
    "Chintamani":(13.3986,78.0534),"Gouribidanur":(13.6131,77.5203),
    "Gudibanda":(13.9088,77.8397),"Sidlaghatta":(13.3893,77.8649),
    "Tumkuru":(13.3379,77.1173),"Tiptur":(13.2601,76.4757),"Turuvekere":(13.1642,76.6629),
    "Madhugiri":(13.6647,77.2097),"Gubbi":(13.3097,76.9418),"Sira":(13.7426,76.9051),
    "Pavagada":(14.0994,77.2797),"Kunigal":(13.0234,77.0248),
    "Hassan":(13.0036,76.1003),"Arsikere":(13.3143,76.2508),
    "Channarayapatna":(12.9035,76.3873),"Holenarasipur":(12.7854,76.2394),"Belur":(13.1651,75.8665),
}

def ndvi_color_hex(v):
    if v < 0:    return "#e53e3e"
    if v < 0.1:  return "#fc8181"
    if v < 0.2:  return "#f6ad55"
    if v < 0.3:  return "#faf089"
    if v < 0.4:  return "#68d391"
    return "#276749"

def ndvi_text_color(v):
    if v < 0.3: return "#1a202c"  # dark text on light bars
    return "#ffffff"

def ndvi_label(v):
    if v < 0.05: return "🔴 Bare Soil"
    if v < 0.15: return "🟠 Very Sparse"
    if v < 0.25: return "🟡 Sparse"
    if v < 0.35: return "🟢 Moderate"
    if v < 0.45: return "💚 Good"
    return "🌿 Dense/Healthy"

def supply_signal(v):
    if v < 0.1:  return "📈 Supply VERY LOW → Price HIGH"
    if v < 0.25: return "📈 Supply Low → Price above normal"
    if v < 0.4:  return "➡️  Supply Normal → Normal Price"
    return "📉 Supply Good → Price may soften"

# ── DATA LOADERS ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_ndvi():
    try:
        df = pd.read_sql(
            "SELECT sensing_date,block_id,district,ndvi,is_mock_data FROM raw_ndvi_sentinel ORDER BY sensing_date DESC",
            engine
        )
        df["sensing_date"] = pd.to_datetime(df["sensing_date"])
        df["taluk"] = df["block_id"].str.replace("__sentinel2","",regex=False)\
                                     .str.replace("__mock_seasonal","",regex=False)
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_weather(taluk):
    try:
        df = pd.read_sql(
            f"SELECT date,taluk,temp_max,temp_min,precipitation,humidity_max,wind_speed_max FROM raw_weather WHERE taluk='{taluk}' ORDER BY date DESC LIMIT 400",
            engine
        )
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_weather_multi(taluks):
    try:
        tlist = "','".join(taluks)
        df = pd.read_sql(
            f"SELECT date,taluk,temp_max,temp_min,precipitation,humidity_max FROM raw_weather WHERE taluk IN ('{tlist}') ORDER BY date DESC",
            engine
        )
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def get_forecast(lat, lon):
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude":lat,"longitude":lon,
            "daily":"temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
            "timezone":"Asia/Kolkata","forecast_days":7
        }, timeout=10)
        return r.json().get("daily", {})
    except Exception:
        return {}

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🌾 Crop Intelligence")
    st.markdown("##### South Karnataka Dry Zone")
    st.markdown("---")

    page = st.radio("📋 Navigation", [
        "🏠 Overview",
        "🛰️ Satellite NDVI",
        "🌦️ Weather & Forecast",
        "💰 Crop Prices",
        "📈 Compare Regions",
        "🗺️ Taluk Deep Dive",
    ])

    st.markdown("---")
    dist_opts = ["All Districts"] + list(DISTRICT_TALUKS_MAP.keys())
    sel_district = st.selectbox(
        "📍 District",
        dist_opts,
        key="district_select",
        help="Select a district to filter all charts"
    )
    taluk_opts = (
        SOUTH_KARNATAKA_DRY_ZONE_TALUKS
        if sel_district == "All Districts"
        else DISTRICT_TALUKS_MAP[sel_district]
    )
    sel_taluk = st.selectbox(
        "🏘️ Taluk",
        taluk_opts,
        key="taluk_select",
        help="Select a taluk for detailed view"
    )

    # Show what is currently active
    st.markdown("---")
    st.markdown(f"**🔍 Viewing:**")
    if sel_district == "All Districts":
        st.markdown(f"All 9 Districts · 50 Taluks")
    else:
        st.markdown(f"📍 **{sel_district}**")
        st.markdown(f"🏘️ **{sel_taluk}**")

    st.markdown("---")
    st.markdown(f"📅 **{date.today().strftime('%d %b %Y')}**")
    st.markdown("🛰️ Sentinel-2 **✅ Live**")
    st.markdown("☁️ Weather **✅ Live**")
    st.markdown("🌧️ Season: **Kharif 2026**")

# ═══════════════════════════════════════════════════════════════
# PAGE: OVERVIEW
# ═══════════════════════════════════════════════════════════════
if page == "🏠 Overview":
    # Show current filter banner
    if sel_district == "All Districts":
        st.markdown("# 🌾 Crop Intelligence Dashboard")
        st.markdown("**South Karnataka Dry Zone** — All 9 Districts · 50 Taluks")
    else:
        st.markdown(f"# 🌾 {sel_district} District Dashboard")
        st.markdown(f"**Showing:** {sel_district} district · {len(DISTRICT_TALUKS_MAP.get(sel_district,[]))} taluks")
    st.markdown("---")

    ndvi_df = load_ndvi()
    real = ndvi_df[ndvi_df["is_mock_data"]==False].copy() if not ndvi_df.empty else pd.DataFrame()

    if not real.empty:
        real["district"] = real["taluk"].map(TALUK_TO_DISTRICT).fillna("Other")
        # ✅ FILTER by selected district
        if sel_district != "All Districts":
            real = real[real["district"] == sel_district]

    # Top KPI row — adjust to filtered data
    c1,c2,c3,c4,c5 = st.columns(5)
    taluks_shown = len(DISTRICT_TALUKS_MAP.get(sel_district,[])) if sel_district != "All Districts" else 50
    dist_shown   = 1 if sel_district != "All Districts" else 9
    with c1: st.metric("🗺️ Taluks", str(taluks_shown))
    with c2: st.metric("🏛️ Districts", str(dist_shown))
    with c3:
        if not real.empty:
            avg = real.drop_duplicates("taluk")["ndvi"].mean()
            st.metric("🛰️ Avg NDVI", f"{avg:.3f}")
        else:
            st.metric("🛰️ Avg NDVI", "—")
    with c4: st.metric("☁️ Weather Records", "53,391")
    with c5: st.metric("📅 Data Since", "2005")

    st.markdown("---")

    if not real.empty:
        latest = real.sort_values("sensing_date",ascending=False).drop_duplicates("taluk").copy()

        chart_title = (
            f"NDVI — {sel_district} District"
            if sel_district != "All Districts"
            else "NDVI Value by Taluk — All Districts"
        )
        # ── NDVI bar chart with CLEAR color scale ─────────────────────────
        st.markdown(f'<div class="sec-header">🛰️ Crop Greenness Map — {"All Taluks" if sel_district=="All Districts" else sel_district+" District"} Today</div>', unsafe_allow_html=True)

        latest_sorted = latest.sort_values("ndvi", ascending=True).copy()

        fig = go.Figure()
        for _, row in latest_sorted.iterrows():
            fig.add_trace(go.Bar(
                x=[row["ndvi"]],
                y=[row["taluk"]],
                orientation="h",
                marker_color=ndvi_color_hex(row["ndvi"]),
                marker_line_width=0,
                text=f"{row['ndvi']:.3f}",
                textposition="outside",
                textfont=dict(size=11, color="#2d3748"),
                name=row["district"],
                showlegend=False,
                hovertemplate=(
                    f"<b>{row['taluk']}</b><br>"
                    f"District: {row['district']}<br>"
                    f"NDVI: {row['ndvi']:.3f}<br>"
                    f"{ndvi_label(row['ndvi'])}<extra></extra>"
                ),
            ))

        fig.update_layout(
            paper_bgcolor="#ffffff", plot_bgcolor="#f7fafc",
            font=dict(color="#2d3748", family="Inter"),
            title="NDVI Value by Taluk (Red=No Crop, Orange=Sparse, Yellow=Moderate, Green=Healthy)",
            title_font=dict(size=14, color="#1a202c"),
            height=1000,
            barmode="stack",
            xaxis=dict(
                title="NDVI (0 = Bare Soil → 0.6 = Dense Crops)",
                range=[0, 0.72],
                showgrid=True, gridcolor="#e2e8f0",
                tickfont=dict(size=11, color="#2d3748"),
            ),
            yaxis=dict(
                tickfont=dict(size=11, color="#1a202c"),
                showgrid=False,
            ),
            margin=dict(l=20, r=80, t=55, b=40),
        )

        # Add threshold lines
        fig.add_vline(x=0.1, line_dash="dot", line_color="#e53e3e", line_width=1.5,
                      annotation_text="Bare", annotation_font_color="#e53e3e",
                      annotation_position="top right")
        fig.add_vline(x=0.25, line_dash="dot", line_color="#d69e2e", line_width=1.5,
                      annotation_text="Sparse", annotation_font_color="#d69e2e",
                      annotation_position="top right")
        fig.add_vline(x=0.4, line_dash="dot", line_color="#38a169", line_width=1.5,
                      annotation_text="Healthy", annotation_font_color="#38a169",
                      annotation_position="top right")

        st.plotly_chart(fig, use_container_width=True)

        # Color legend
        st.markdown("""
        <div style="display:flex;gap:16px;flex-wrap:wrap;margin:8px 0 16px 0">
          <span style="background:#fc8181;color:#1a202c;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600">🔴 Below 0.1 — Bare Soil</span>
          <span style="background:#f6ad55;color:#1a202c;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600">🟠 0.1–0.2 — Very Sparse</span>
          <span style="background:#faf089;color:#1a202c;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600">🟡 0.2–0.3 — Sparse</span>
          <span style="background:#68d391;color:#1a202c;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600">🟢 0.3–0.4 — Moderate</span>
          <span style="background:#276749;color:#ffffff;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600">🌿 Above 0.4 — Healthy/Dense</span>
        </div>
        """, unsafe_allow_html=True)

        # ── Supply alerts ─────────────────────────────────────────────────
        st.markdown("---")
        ca, cb = st.columns(2)
        with ca:
            st.markdown("### ⚠️ Low Supply Areas (Prices will be HIGH)")
            low = latest[latest["ndvi"] < 0.2].sort_values("ndvi")
            if low.empty:
                st.success("No critically low NDVI areas right now.")
            for _, r in low.iterrows():
                st.markdown(f'<div class="card-red">🔴 <b>{r["taluk"]}</b> ({r["district"]}) — NDVI {r["ndvi"]:.3f} — {ndvi_label(r["ndvi"])}</div>', unsafe_allow_html=True)

        with cb:
            st.markdown("### ✅ High Supply Areas (Prices will be NORMAL)")
            high = latest[latest["ndvi"] > 0.42].sort_values("ndvi", ascending=False)
            if high.empty:
                st.info("No taluks with very high NDVI currently.")
            for _, r in high.iterrows():
                st.markdown(f'<div class="card-green">🌿 <b>{r["taluk"]}</b> ({r["district"]}) — NDVI {r["ndvi"]:.3f} — {ndvi_label(r["ndvi"])}</div>', unsafe_allow_html=True)

        # ── District summary table ────────────────────────────────────────
        st.markdown("---")
        st.markdown("### 📊 District Summary Table")
        summary = (
            latest.groupby("district")["ndvi"]
            .agg(["mean","min","max","count"])
            .round(3).reset_index()
        )
        summary.columns = ["District","Avg NDVI","Min NDVI","Max NDVI","Taluks"]
        summary["Overall Status"] = summary["Avg NDVI"].apply(ndvi_label)
        summary["Supply Signal"] = summary["Avg NDVI"].apply(supply_signal)
        summary = summary.sort_values("Avg NDVI", ascending=False)
        st.dataframe(summary, use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════════════
# PAGE: SATELLITE NDVI
# ═══════════════════════════════════════════════════════════════
elif page == "🛰️ Satellite NDVI":
    st.markdown("# 🛰️ Satellite NDVI — Sentinel-2 Real Data")
    st.markdown("**10m resolution · ESA Copernicus · Updated daily**")
    st.markdown("---")

    ndvi_df = load_ndvi()
    if ndvi_df.empty:
        st.warning("No NDVI data yet.")
        st.stop()

    real = ndvi_df[ndvi_df["is_mock_data"]==False].copy()
    real["district"] = real["taluk"].map(TALUK_TO_DISTRICT).fillna("Other")

    if sel_district != "All Districts":
        real = real[real["district"] == sel_district]

    latest = real.sort_values("sensing_date",ascending=False).drop_duplicates("taluk").copy()

    # KPIs
    c1,c2,c3,c4 = st.columns(4)
    with c1: st.metric("🛰️ Records Today", f"{len(latest)}")
    with c2: st.metric("📅 Last Update", latest["sensing_date"].max().strftime("%d %b %Y") if not latest.empty else "—")
    with c3: st.metric("🌿 Highest NDVI", f"{latest['ndvi'].max():.3f}" if not latest.empty else "—")
    with c4: st.metric("🔴 Lowest NDVI", f"{latest['ndvi'].min():.3f}" if not latest.empty else "—")

    st.markdown("---")
    st.markdown("### 🌿 NDVI Progress Bars — All Taluks")

    cols = st.columns(2)
    for i, (_, row) in enumerate(latest.sort_values("ndvi",ascending=False).iterrows()):
        pct = max(0, min(100, row["ndvi"] / 0.65 * 100))
        color = ndvi_color_hex(row["ndvi"])
        val_color = ndvi_text_color(row["ndvi"])
        with cols[i % 2]:
            st.markdown(f"""
            <div class="ndvi-row">
              <div class="ndvi-label-row">
                <span class="ndvi-name">{row['taluk']}</span>
                <span class="ndvi-val" style="color:{color if row['ndvi'] >= 0.3 else '#e53e3e'}">{row['ndvi']:.3f} — {ndvi_label(row['ndvi'])}</span>
              </div>
              <div class="ndvi-bg">
                <div class="ndvi-fill" style="width:{pct:.1f}%;background:{color}"></div>
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 📊 NDVI by District — Comparison")

    real["district"] = real["taluk"].map(TALUK_TO_DISTRICT).fillna("Other")
    latest2 = real.sort_values("sensing_date",ascending=False).drop_duplicates("taluk").copy()

    fig = px.box(
        latest2, x="district", y="ndvi", color="district",
        color_discrete_sequence=px.colors.qualitative.Set2,
        title="NDVI Distribution per District",
        labels={"ndvi":"NDVI Value","district":"District"},
        height=420,
    )
    fig.add_hline(y=0.1, line_dash="dot", line_color="#e53e3e", line_width=2,
                  annotation_text="Bare threshold (0.1)", annotation_font_color="#e53e3e")
    fig.add_hline(y=0.35, line_dash="dot", line_color="#38a169", line_width=2,
                  annotation_text="Good growth (0.35)", annotation_font_color="#38a169")
    fig = apply_layout(fig, height=420)
    fig.update_xaxes(tickangle=-30)
    st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: WEATHER & FORECAST
# ═══════════════════════════════════════════════════════════════
elif page == "🌦️ Weather & Forecast":
    st.markdown(f"# 🌦️ Weather — {sel_taluk}")
    lat, lon = TALUK_COORDS.get(sel_taluk, (12.5, 76.9))
    st.markdown(f"📍 {TALUK_TO_DISTRICT.get(sel_taluk,'')} District · {lat}°N, {lon}°E")
    st.markdown("---")

    forecast = get_forecast(lat, lon)
    if forecast:
        st.markdown("### 📅 7-Day Forecast")
        days  = forecast.get("time",[])
        tmaxs = forecast.get("temperature_2m_max",[])
        tmins = forecast.get("temperature_2m_min",[])
        rains = forecast.get("precipitation_sum",[])

        cols = st.columns(len(days))
        for i,(d,tm,tn,r) in enumerate(zip(days,tmaxs,tmins,rains)):
            day = datetime.strptime(d,"%Y-%m-%d")
            icon = "⛈️" if r>10 else "🌧️" if r>2 else "🌥️" if r>0 else "☀️"
            with cols[i]:
                st.markdown(f"""
                <div class="forecast-card">
                  <div class="fc-day">{day.strftime('%a')}</div>
                  <div class="fc-date">{day.strftime('%d %b')}</div>
                  <div class="fc-icon">{icon}</div>
                  <div class="fc-tmax">{tm:.0f}°C</div>
                  <div class="fc-tmin">{tn:.0f}°C</div>
                  <div class="fc-rain">💧 {r:.1f}mm</div>
                </div>""", unsafe_allow_html=True)

    st.markdown("---")
    weather_df = load_weather(sel_taluk)
    if weather_df.empty:
        st.info(f"No historical weather stored for {sel_taluk} yet.")
        st.stop()

    # Summary stats — 30 days
    r30 = weather_df.head(30)
    st.markdown("### 📋 Last 30 Days Summary")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("🌡️ Avg Max Temp", f"{r30['temp_max'].mean():.1f}°C")
    c2.metric("🌡️ Avg Min Temp", f"{r30['temp_min'].mean():.1f}°C")
    c3.metric("🌧️ Total Rainfall", f"{r30['precipitation'].sum():.0f}mm")
    c4.metric("💧 Avg Humidity", f"{r30['humidity_max'].mean():.0f}%")
    c5.metric("🌬️ Max Wind", f"{r30['wind_speed_max'].max():.0f}km/h")

    st.markdown("---")
    tab1, tab2, tab3 = st.tabs(["🌡️ Temperature", "🌧️ Rainfall", "💧 Humidity"])

    with tab1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=weather_df["date"], y=weather_df["temp_max"],
            name="Max Temp", line=dict(color="#e53e3e", width=2.5)))
        fig.add_trace(go.Scatter(x=weather_df["date"], y=weather_df["temp_min"],
            name="Min Temp", line=dict(color="#3182ce", width=2),
            fill="tonexty", fillcolor="rgba(49,130,206,0.08)"))
        fig = apply_layout(fig, f"Temperature History — {sel_taluk}", 380)
        fig.update_yaxes(title="°C")
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        mon = weather_df.groupby(weather_df["date"].dt.to_period("M"))["precipitation"].sum().reset_index()
        mon["date"] = mon["date"].astype(str)
        fig = px.bar(mon, x="date", y="precipitation",
            color="precipitation",
            color_continuous_scale=["#bee3f8","#3182ce","#2c5282"],
            labels={"precipitation":"Rainfall (mm)","date":"Month"},
            title=f"Monthly Rainfall — {sel_taluk}")
        fig = apply_layout(fig, height=380)
        fig.update_xaxes(tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        fig = px.area(weather_df, x="date", y="humidity_max",
            color_discrete_sequence=["#805ad5"],
            labels={"humidity_max":"Humidity (%)","date":"Date"},
            title=f"Humidity — {sel_taluk}")
        fig = apply_layout(fig, height=380)
        st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: CROP PRICES
# ═══════════════════════════════════════════════════════════════
elif page == "💰 Crop Prices":
    st.markdown("# 💰 Crop Prices — All Crops")
    st.markdown("---")

    st.markdown('<div class="card-yellow">⚠️ <b>Live Agmarknet price collection is being connected.</b> Showing Karnataka reference price ranges + satellite supply signals below.</div>', unsafe_allow_html=True)
    st.markdown("")

    # Supply intelligence — filtered by selected district
    ndvi_df = load_ndvi()
    if not ndvi_df.empty:
        real = ndvi_df[ndvi_df["is_mock_data"]==False].copy()
        real["district"] = real["taluk"].map(TALUK_TO_DISTRICT).fillna("Other")
        # ✅ Filter by district
        if sel_district != "All Districts":
            real = real[real["district"] == sel_district]
        latest = real.sort_values("sensing_date",ascending=False).drop_duplicates("taluk").copy()
        latest["Supply Signal"] = latest["ndvi"].apply(supply_signal)
        latest["NDVI Status"]   = latest["ndvi"].apply(ndvi_label)

        label = sel_district if sel_district != "All Districts" else "All Districts"
        st.markdown(f"### 🛰️ Current Supply Signals — {label}")
        st.dataframe(
            latest[["taluk","district","ndvi","NDVI Status","Supply Signal"]]
            .sort_values("ndvi").rename(columns={"taluk":"Taluk","district":"District","ndvi":"NDVI"}),
            use_container_width=True, hide_index=True,
        )

    st.markdown("---")
    st.markdown("### 📊 Karnataka Price Reference Ranges")

    price_data = [
        {"Crop":"Paddy (Rice)","Min":1800,"Max":2300,"Unit":"₹/quintal","Season":"Kharif+Rabi"},
        {"Crop":"Ragi","Min":2000,"Max":3800,"Unit":"₹/quintal","Season":"Kharif+Rabi"},
        {"Crop":"Maize","Min":1400,"Max":2400,"Unit":"₹/quintal","Season":"Kharif+Rabi"},
        {"Crop":"Sunflower","Min":5000,"Max":7500,"Unit":"₹/quintal","Season":"Rabi+Summer"},
        {"Crop":"Groundnut","Min":5000,"Max":8000,"Unit":"₹/quintal","Season":"Kharif+Rabi"},
        {"Crop":"Tomato","Min":300,"Max":28000,"Unit":"₹/quintal","Season":"All Seasons"},
        {"Crop":"Onion","Min":500,"Max":9000,"Unit":"₹/quintal","Season":"Rabi"},
        {"Crop":"Potato","Min":700,"Max":3200,"Unit":"₹/quintal","Season":"Rabi"},
        {"Crop":"Sugarcane","Min":2800,"Max":3400,"Unit":"₹/tonne","Season":"Annual"},
        {"Crop":"Horsegram","Min":4500,"Max":8500,"Unit":"₹/quintal","Season":"Rabi"},
        {"Crop":"Arhar (Tur)","Min":6000,"Max":9500,"Unit":"₹/quintal","Season":"Kharif"},
        {"Crop":"Moong","Min":7000,"Max":10500,"Unit":"₹/quintal","Season":"Summer"},
        {"Crop":"Turmeric","Min":7000,"Max":16000,"Unit":"₹/quintal","Season":"Annual"},
        {"Crop":"Chilli","Min":8000,"Max":22000,"Unit":"₹/quintal","Season":"Rabi"},
        {"Crop":"Coconut","Min":12,"Max":38,"Unit":"₹/nut","Season":"Annual"},
        {"Crop":"Arecanut","Min":25000,"Max":55000,"Unit":"₹/quintal","Season":"Annual"},
        {"Crop":"Banana","Min":700,"Max":3500,"Unit":"₹/quintal","Season":"Annual"},
    ]
    pdf = pd.DataFrame(price_data)

    fig = go.Figure()
    fig.add_trace(go.Bar(x=pdf["Crop"], y=pdf["Min"], name="Min Price",
                         marker_color="#90cdf4", text=pdf["Min"],
                         texttemplate="%{y:,}", textposition="inside"))
    fig.add_trace(go.Bar(x=pdf["Crop"], y=pdf["Max"]-pdf["Min"], name="Range",
                         marker_color="#2b6cb0",
                         base=pdf["Min"]))
    fig.update_layout(
        barmode="stack",
        paper_bgcolor="#ffffff", plot_bgcolor="#f7fafc",
        font=dict(color="#2d3748",family="Inter"),
        title="Price Range (Min–Max) per Crop — Karnataka Mandis",
        title_font=dict(size=15,color="#1a202c"),
        yaxis_title="Price (₹)",
        legend=dict(bgcolor="#f7fafc"),
        height=460,
        margin=dict(t=50,b=120),
    )
    fig.update_xaxes(tickangle=-40, showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="#e2e8f0")
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(pdf, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: COMPARE REGIONS
# ═══════════════════════════════════════════════════════════════
elif page == "📈 Compare Regions":
    st.markdown("# 📈 Compare Regions — Districts & Taluks")
    st.markdown("---")

    ndvi_df = load_ndvi()
    if not ndvi_df.empty:
        real = ndvi_df[ndvi_df["is_mock_data"]==False].copy()
        real["district"] = real["taluk"].map(TALUK_TO_DISTRICT).fillna("Other")
        latest = real.sort_values("sensing_date",ascending=False).drop_duplicates("taluk").copy()

        # Grouped bar by district
        dist_avg = latest.groupby("district")["ndvi"].mean().sort_values(ascending=False).reset_index()
        colors_list = [ndvi_color_hex(v) for v in dist_avg["ndvi"]]
        fig = go.Figure(go.Bar(
            x=dist_avg["district"], y=dist_avg["ndvi"],
            marker_color=colors_list,
            marker_line_color="#2d3748", marker_line_width=1,
            text=[f"{v:.3f}" for v in dist_avg["ndvi"]],
            textposition="outside",
            textfont=dict(color="#1a202c", size=12),
        ))
        fig.add_hline(y=0.25, line_dash="dash", line_color="#d69e2e", line_width=2,
                      annotation_text="Sparse threshold", annotation_font_color="#d69e2e")
        fig.add_hline(y=0.4,  line_dash="dash", line_color="#38a169", line_width=2,
                      annotation_text="Good growth", annotation_font_color="#38a169")
        fig.update_layout(
            paper_bgcolor="#ffffff", plot_bgcolor="#f7fafc",
            font=dict(color="#2d3748",family="Inter"),
            title="Average NDVI by District — Today",
            title_font=dict(size=16,color="#1a202c"),
            yaxis=dict(title="NDVI",range=[0,0.7],showgrid=True,gridcolor="#e2e8f0"),
            xaxis=dict(showgrid=False),
            height=420, margin=dict(t=50,b=60),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Scatter: all taluks
        fig2 = px.scatter(
            latest, x="district", y="ndvi",
            color="ndvi",
            color_continuous_scale=["#fc8181","#f6ad55","#faf089","#68d391","#276749"],
            range_color=[0, 0.6],
            size=[abs(v)+0.05 for v in latest["ndvi"]],
            size_max=28,
            hover_data={"taluk":True,"ndvi":":.3f","district":True},
            title="Individual Taluk NDVI — All Districts",
            labels={"ndvi":"NDVI","district":"District"},
            height=420,
        )
        fig2 = apply_layout(fig2, height=420)
        fig2.update_xaxes(tickangle=-30)
        st.plotly_chart(fig2, use_container_width=True)

    # Weather comparison
    st.markdown("---")
    st.markdown("### 🌧️ Rainfall Comparison — Last 30 Days")
    taluks_to_compare = DISTRICT_TALUKS_MAP.get(sel_district, MANDYA_TALUKS) if sel_district != "All Districts" else MANDYA_TALUKS
    wdf = load_weather_multi(taluks_to_compare)
    if not wdf.empty:
        cutoff = datetime.now() - timedelta(days=30)
        r30 = wdf[wdf["date"] >= cutoff]
        if not r30.empty:
            rain30 = r30.groupby("taluk")["precipitation"].sum().sort_values(ascending=False).reset_index()
            fig3 = px.bar(rain30, x="taluk", y="precipitation",
                color="precipitation",
                color_continuous_scale=["#bee3f8","#3182ce","#1a365d"],
                labels={"precipitation":"Rainfall (mm)","taluk":"Taluk"},
                title="Total Rainfall — Last 30 Days",
                text="precipitation",
                height=380)
            fig3.update_traces(texttemplate="%{text:.0f}mm", textposition="outside",
                               textfont=dict(color="#2d3748"))
            fig3 = apply_layout(fig3, height=380)
            fig3.update_xaxes(tickangle=-35)
            st.plotly_chart(fig3, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: TALUK DEEP DIVE
# ═══════════════════════════════════════════════════════════════
elif page == "🗺️ Taluk Deep Dive":
    district = TALUK_TO_DISTRICT.get(sel_taluk, "Unknown")
    lat, lon  = TALUK_COORDS.get(sel_taluk, (12.5, 76.9))

    st.markdown(f"# 🗺️ {sel_taluk}")
    st.markdown(f"**District:** {district} &nbsp;·&nbsp; **{lat}°N, {lon}°E** &nbsp;·&nbsp; Agro-Climate: South Karnataka Dry Zone")
    st.markdown("---")

    ndvi_df    = load_ndvi()
    weather_df = load_weather(sel_taluk)
    forecast   = get_forecast(lat, lon)

    col1, col2 = st.columns([1,1])

    with col1:
        st.markdown("#### 🛰️ Satellite NDVI — Current")
        if not ndvi_df.empty:
            t_ndvi = ndvi_df[(ndvi_df["taluk"]==sel_taluk)&(ndvi_df["is_mock_data"]==False)]
            if not t_ndvi.empty:
                v = t_ndvi.sort_values("sensing_date",ascending=False).iloc[0]["ndvi"]
                color = ndvi_color_hex(v)
                pct = max(0, min(100, v/0.65*100))
                st.metric("NDVI Value", f"{v:.3f}")
                st.markdown(f"**Status:** {ndvi_label(v)}")
                st.markdown(f"**Supply:** {supply_signal(v)}")
                st.markdown(f"""
                <div style="margin-top:10px">
                  <div style="display:flex;justify-content:space-between;margin-bottom:4px">
                    <span style="font-size:12px;color:#4a5568;font-weight:600">NDVI Progress</span>
                    <span style="font-size:12px;font-weight:700;color:{color}">{v:.3f}</span>
                  </div>
                  <div class="ndvi-bg">
                    <div class="ndvi-fill" style="width:{pct:.1f}%;background:{color}"></div>
                  </div>
                  <div style="display:flex;justify-content:space-between;margin-top:2px">
                    <span style="font-size:10px;color:#718096">0.0 (Bare)</span>
                    <span style="font-size:10px;color:#718096">0.65 (Dense)</span>
                  </div>
                </div>""", unsafe_allow_html=True)
                st.markdown('<div class="card-blue">🛰️ <b>Real Sentinel-2 data</b> — 10m resolution · ESA Copernicus</div>', unsafe_allow_html=True)
            else:
                st.info("No NDVI data for this taluk yet.")

    with col2:
        st.markdown("#### 🌦️ Today's Weather Forecast")
        if forecast and forecast.get("time"):
            tmax = forecast["temperature_2m_max"][0]
            tmin = forecast["temperature_2m_min"][0]
            rain = forecast["precipitation_sum"][0]
            wind = forecast.get("wind_speed_10m_max",[0])[0]
            icon = "⛈️" if rain>10 else "🌧️" if rain>2 else "🌤️"
            st.markdown(f"""
            <div style="background:#f0fff4;border-radius:14px;padding:20px;border:2px solid #68d391">
              <div style="font-size:36px;text-align:center">{icon}</div>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px">
                <div style="background:#fff;border-radius:10px;padding:12px;text-align:center">
                  <div style="color:#e53e3e;font-size:22px;font-weight:800">{tmax:.0f}°C</div>
                  <div style="color:#718096;font-size:11px">MAX TEMP</div>
                </div>
                <div style="background:#fff;border-radius:10px;padding:12px;text-align:center">
                  <div style="color:#3182ce;font-size:22px;font-weight:800">{tmin:.0f}°C</div>
                  <div style="color:#718096;font-size:11px">MIN TEMP</div>
                </div>
                <div style="background:#fff;border-radius:10px;padding:12px;text-align:center">
                  <div style="color:#2b6cb0;font-size:22px;font-weight:800">{rain:.1f}mm</div>
                  <div style="color:#718096;font-size:11px">RAINFALL</div>
                </div>
                <div style="background:#fff;border-radius:10px;padding:12px;text-align:center">
                  <div style="color:#553c9a;font-size:22px;font-weight:800">{wind:.0f}km/h</div>
                  <div style="color:#718096;font-size:11px">WIND</div>
                </div>
              </div>
            </div>""", unsafe_allow_html=True)

    # Weather chart
    if not weather_df.empty:
        st.markdown("---")
        st.markdown("#### 📊 Historical Weather — Last 365 Days")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=weather_df["date"], y=weather_df["precipitation"],
                             name="Rainfall(mm)", marker_color="#90cdf4", yaxis="y2", opacity=0.7))
        fig.add_trace(go.Scatter(x=weather_df["date"], y=weather_df["temp_max"],
                                 name="Max Temp(°C)", line=dict(color="#e53e3e",width=2.5)))
        fig.add_trace(go.Scatter(x=weather_df["date"], y=weather_df["temp_min"],
                                 name="Min Temp(°C)", line=dict(color="#3182ce",width=1.5),
                                 fill="tonexty", fillcolor="rgba(49,130,206,0.06)"))
        fig.update_layout(
            paper_bgcolor="#ffffff", plot_bgcolor="#f7fafc",
            font=dict(color="#2d3748",family="Inter"),
            title=f"Temperature & Rainfall — {sel_taluk}",
            height=400,
            yaxis=dict(title="Temperature (°C)", showgrid=True, gridcolor="#e2e8f0", side="left"),
            yaxis2=dict(title="Rainfall (mm)", overlaying="y", side="right", showgrid=False),
            legend=dict(bgcolor="#f7fafc"),
            margin=dict(t=45,b=30),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Suitable crops
    st.markdown("---")
    st.markdown("#### 🌾 Suitable Crops — This Taluk")
    CROP_MAP = {
        "Malavalli":["Paddy 🌾","Sugarcane 🎋","Ragi 🌿","Tomato 🍅","Banana 🍌","Coconut 🥥"],
        "Mandya":["Sugarcane 🎋","Paddy 🌾","Ragi 🌿","Sunflower 🌻"],
        "Mysuru":["Paddy 🌾","Ragi 🌿","Sunflower 🌻","Onion 🧅","Potato 🥔"],
        "Kolar":["Tomato 🍅","Potato 🥔","Groundnut 🥜","Ragi 🌿","Mulberry 🌱"],
        "Chikkaballapura":["Tomato 🍅","Groundnut 🥜","Ragi 🌿","Sunflower 🌻"],
        "Tumkuru":["Coconut 🥥","Arecanut 🌴","Groundnut 🥜","Ragi 🌿"],
        "Pavagada":["Ragi 🌿","Groundnut 🥜","Sunflower 🌻","Horsegram 🫘"],
        "Chamarajanagar":["Paddy 🌾","Ragi 🌿","Groundnut 🥜","Turmeric 🟡"],
    }
    crops = CROP_MAP.get(sel_taluk, ["Ragi 🌿","Paddy 🌾","Groundnut 🥜","Sunflower 🌻","Horsegram 🫘"])
    chips = " ".join(f'<span class="crop-chip">{c}</span>' for c in crops)
    st.markdown(f'<div style="padding:10px 0">{chips}</div>', unsafe_allow_html=True)


# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    '<div style="text-align:center;color:#718096;font-size:12px;padding:8px">'
    '🌾 Crop Intelligence Agent · South Karnataka Dry Zone · '
    '🛰️ Sentinel-2 (GEE) · ☁️ Open-Meteo · '
    'Built for farmers of Malavalli & surrounding taluks'
    '</div>',
    unsafe_allow_html=True,
)
