"""
Crop Intelligence Dashboard — South Karnataka Dry Zone
Designed from a FARMER's perspective:
  "What do I need to know TODAY to make the RIGHT decision?"

Data dimensions:
  1. Time    — Today / This week / This season / Last 20 years
  2. Space   — My field / My taluk / Nearby taluks / Whole region
  3. Crop    — Crop health / Price / Supply / Risk
  4. Action  — Plant now? Sell now? Wait?
"""

import os, sys, warnings
from datetime import date, datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from crop_agent.config.settings import (
    DISTRICT_TALUKS_MAP, SOUTH_KARNATAKA_DRY_ZONE_TALUKS, TALUK_TO_DISTRICT
)
from crop_agent.database.connection import engine

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🌾 Crop Intelligence — South Karnataka",
    page_icon="🌾", layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS — clean, readable, farmer-friendly ───────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
* { font-family:'Inter',sans-serif!important; }

/* App background */
.stApp, .main .block-container { background:#f4f6f9; }
.main .block-container { padding:1.2rem 2rem; }

/* Sidebar */
section[data-testid="stSidebar"] { background:#1b4332!important; }
section[data-testid="stSidebar"] * { color:#fff!important; }
section[data-testid="stSidebar"] .stSelectbox>div>div,
section[data-testid="stSidebar"] .stRadio>div {
    background:#2d6a4f!important; border-radius:8px; padding:4px;
}
section[data-testid="stSidebar"] label {
    color:#b7e4c7!important; font-size:11px!important;
    font-weight:700!important; text-transform:uppercase; letter-spacing:.5px;
}

/* KPI cards */
div[data-testid="metric-container"] {
    background:#fff; border-radius:14px; padding:16px 20px;
    box-shadow:0 1px 8px rgba(0,0,0,.07);
    border-top:4px solid #2d6a4f;
}
div[data-testid="metric-container"] label { color:#64748b!important; font-size:11px!important; font-weight:700!important; text-transform:uppercase; letter-spacing:.5px; }
div[data-testid="metric-container"] [data-testid="stMetricValue"] { color:#0f172a!important; font-size:26px!important; font-weight:800!important; }

/* Section title */
.stitle { font-size:17px; font-weight:700; color:#1e293b; border-left:4px solid #2d6a4f; padding-left:10px; margin:20px 0 10px; }

/* Traffic light signal */
.signal { display:flex; align-items:center; gap:8px; padding:12px 16px; border-radius:12px; margin:6px 0; font-size:14px; font-weight:600; }
.signal-green  { background:#dcfce7; color:#166534; border:1.5px solid #86efac; }
.signal-yellow { background:#fef9c3; color:#854d0e; border:1.5px solid #fde047; }
.signal-red    { background:#fee2e2; color:#991b1b; border:1.5px solid #fca5a5; }
.signal-blue   { background:#dbeafe; color:#1e3a8a; border:1.5px solid #93c5fd; }

/* Card white box */
.card { background:#fff; border-radius:14px; padding:18px 20px; box-shadow:0 1px 8px rgba(0,0,0,.07); margin-bottom:12px; }

/* Forecast card */
.fcast { background:#fff; border-radius:12px; padding:14px 8px; text-align:center;
         box-shadow:0 1px 6px rgba(0,0,0,.08); border-top:3px solid #2d6a4f; }
.fcast .day  { font-size:10px; color:#94a3b8; font-weight:700; text-transform:uppercase; }
.fcast .dt   { font-size:13px; font-weight:700; color:#1e293b; }
.fcast .icon { font-size:26px; margin:4px 0; }
.fcast .hi   { font-size:17px; font-weight:800; color:#dc2626; }
.fcast .lo   { font-size:12px; font-weight:600; color:#2563eb; }
.fcast .rn   { font-size:11px; color:#2563eb; margin-top:3px; }

/* NDVI bar */
.nvbar-bg { background:#e2e8f0; border-radius:6px; height:16px; overflow:hidden; margin-top:3px; }
.nvbar-fill { height:100%; border-radius:6px; }

/* Tab styling */
.stTabs [data-baseweb="tab-list"] { background:#fff; border-radius:12px; padding:5px; box-shadow:0 1px 6px rgba(0,0,0,.07); }
.stTabs [data-baseweb="tab"] { background:transparent!important; color:#475569!important; font-weight:600!important; border-radius:8px!important; }
.stTabs [aria-selected="true"] { background:#2d6a4f!important; color:#fff!important; }
</style>
""", unsafe_allow_html=True)

# ── Constants & helpers ───────────────────────────────────────────────────────
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

CROP_CALENDAR = {
    "Kharif (Jun–Oct)":  ["Paddy","Ragi","Maize","Groundnut","Soybean","Arhar","Sesame","Cotton"],
    "Rabi (Nov–Feb)":    ["Wheat","Sunflower","Safflower","Horsegram","Onion","Potato","Mustard"],
    "Summer (Mar–May)":  ["Moong","Urad","Groundnut","Watermelon","Vegetables"],
    "Annual / Perennial":["Sugarcane","Banana","Coconut","Arecanut","Turmeric","Ginger"],
}

PRICE_RANGES = {
    "Paddy":     (1800,2300,"Kharif+Rabi"),  "Ragi":      (2000,3800,"Kharif+Rabi"),
    "Maize":     (1400,2400,"Kharif+Rabi"),  "Sunflower": (5000,7500,"Rabi"),
    "Groundnut": (5000,8000,"Kharif+Rabi"),  "Tomato":    (500,28000,"All Seasons"),
    "Onion":     (500,9000,"Rabi"),           "Potato":    (700,3200,"Rabi"),
    "Sugarcane": (2800,3400,"Annual"),        "Horsegram": (4500,8500,"Rabi"),
    "Arhar":     (6000,9500,"Kharif"),        "Moong":     (7000,10500,"Summer"),
    "Turmeric":  (7000,16000,"Annual"),       "Chilli":    (8000,22000,"Rabi"),
    "Banana":    (700,3500,"Annual"),         "Coconut":   (1200,3800,"Annual"),
    "Arecanut":  (25000,55000,"Annual"),
}

def ndvi_color(v):
    if v < 0.05: return "#ef4444"
    if v < 0.15: return "#f97316"
    if v < 0.25: return "#eab308"
    if v < 0.35: return "#22c55e"
    return "#15803d"

def ndvi_label(v):
    if v < 0.05: return ("🔴 Bare Soil","red")
    if v < 0.15: return ("🟠 Very Sparse","orange")
    if v < 0.25: return ("🟡 Sparse","yellow")
    if v < 0.35: return ("🟢 Moderate","green")
    return ("🌿 Healthy Crops","green")

def playout(fig, h=380):
    fig.update_layout(
        paper_bgcolor="#fff", plot_bgcolor="#f8fafc",
        font=dict(color="#334155",family="Inter"),
        height=h, margin=dict(t=45,b=20,l=10,r=10),
        legend=dict(bgcolor="#f8fafc",bordercolor="#e2e8f0"),
    )
    fig.update_xaxes(showgrid=False, linecolor="#e2e8f0")
    fig.update_yaxes(showgrid=True, gridcolor="#e2e8f0")
    return fig

def signal_box(icon, text, kind="green"):
    return f'<div class="signal signal-{kind}">{icon} {text}</div>'

# ── Data loaders ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_ndvi_all():
    try:
        df = pd.read_sql(
            "SELECT sensing_date,block_id,ndvi,evi,cloud_cover_pct,is_mock_data FROM raw_ndvi_sentinel ORDER BY sensing_date DESC",
            engine)
        df["sensing_date"] = pd.to_datetime(df["sensing_date"])
        df["taluk"] = df["block_id"].str.replace("__sentinel2","",regex=False)\
                                     .str.replace("__mock_seasonal","",regex=False)
        df["district"] = df["taluk"].map(TALUK_TO_DISTRICT).fillna("Other")
        return df
    except Exception as e:
        st.error(f"EXCEPTION IN load_ndvi_all: {e}")
        import traceback
        st.code(traceback.format_exc())
        return pd.DataFrame(columns=["sensing_date", "block_id", "ndvi", "evi", "cloud_cover_pct", "is_mock_data", "taluk", "district"])

@st.cache_data(ttl=300)
def load_weather_taluk(taluk):
    try:
        df = pd.read_sql(
            f"SELECT date,rainfall_mm,temp_max_c,temp_min_c,humidity_pct,wind_kmh,solar_radiation,et0_mm "
            f"FROM raw_weather WHERE taluk='{taluk}' ORDER BY date",
            engine)
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception as e:
        st.error(f"EXCEPTION IN load_weather_taluk: {e}")
        import traceback
        st.code(traceback.format_exc())
        return pd.DataFrame(columns=["date", "rainfall_mm", "temp_max_c", "temp_min_c", "humidity_pct", "wind_kmh", "solar_radiation", "et0_mm", "taluk", "district"])

@st.cache_data(ttl=300)
def load_weather_recent(taluk, days=90):
    try:
        df = pd.read_sql(
            f"SELECT date,rainfall_mm,temp_max_c,temp_min_c,humidity_pct,wind_kmh "
            f"FROM raw_weather WHERE taluk='{taluk}' "
            f"ORDER BY date DESC LIMIT {days}",
            engine)
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values("date")
    except Exception as e:
        st.error(f"EXCEPTION IN load_weather_recent: {e}")
        import traceback
        st.code(traceback.format_exc())
        return pd.DataFrame(columns=["date", "rainfall_mm", "temp_max_c", "temp_min_c", "humidity_pct", "wind_kmh", "taluk", "district"])

@st.cache_data(ttl=300)
def load_weather_multi_taluks(taluks):
    try:
        tl = "','".join(taluks)
        df = pd.read_sql(
            f"SELECT date,taluk,district,rainfall_mm,temp_max_c,temp_min_c,humidity_pct "
            f"FROM raw_weather WHERE taluk IN ('{tl}') ORDER BY date DESC",
            engine)
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception as e:
        st.error(f"EXCEPTION IN load_weather_multi_taluks: {e}")
        import traceback
        st.code(traceback.format_exc())
        return pd.DataFrame(columns=["date", "taluk", "district", "rainfall_mm", "temp_max_c", "temp_min_c", "humidity_pct"])

@st.cache_data(ttl=300)
def load_seasonal_rain_compare(taluk):
    """Monthly average rain: this year vs 5-year avg vs 20-year avg"""
    try:
        df = pd.read_sql(
            f"SELECT date,rainfall_mm FROM raw_weather WHERE taluk='{taluk}' ORDER BY date",
            engine)
        df["date"]  = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.month
        df["year"]  = df["date"].dt.year
        return df
    except Exception as e:
        st.error(f"EXCEPTION IN load_seasonal_rain_compare: {e}")
        import traceback
        st.code(traceback.format_exc())
        return pd.DataFrame(columns=["date", "rainfall_mm", "month", "year"])



@st.cache_data(ttl=600)
def get_forecast(lat, lon):
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude":lat,"longitude":lon,
            "daily":"temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode,wind_speed_10m_max",
            "timezone":"Asia/Kolkata","forecast_days":7
        }, timeout=8)
        return r.json().get("daily",{})
    except: return {}

def wmo_icon(code, rain):
    if code in [0,1]: return "☀️"
    if code in [2]:   return "🌤️"
    if code in [3]:   return "☁️"
    if code in [45,48]: return "🌫️"
    if rain > 15:     return "⛈️"
    if rain > 2:      return "🌧️"
    if rain > 0:      return "🌦️"
    return "🌤️"

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🌾 Crop Intelligence")
    st.markdown("*South Karnataka Dry Zone*")
    st.markdown("---")

    PAGE_ICONS = {
        "🌅 Morning Briefing":   "Start here every morning",
        "🌿 My Field":           "Your taluk — soil, crops, NDVI",
        "🌧️ Rain & Weather":     "20 years of rainfall data",
        "💰 Market & Prices":    "Prices, supply, when to sell",
        "🌍 Region NDVI Map":    "Crop cover across 50 taluks",
        "📅 Crop Calendar":      "What to plant, when",
        "📊 Season Analysis":    "This year vs historical",
    }
    page = st.radio("📋 Page", list(PAGE_ICONS.keys()), format_func=lambda x: x)
    st.caption(f"*{PAGE_ICONS[page]}*")

    st.markdown("---")
    dist_opts = ["All Districts"] + list(DISTRICT_TALUKS_MAP.keys())
    sel_dist  = st.selectbox("📍 District", dist_opts, key="dist")
    t_opts    = SOUTH_KARNATAKA_DRY_ZONE_TALUKS if sel_dist == "All Districts" else DISTRICT_TALUKS_MAP[sel_dist]
    sel_taluk = st.selectbox("🏘️ My Taluk", t_opts, key="taluk")

    lat, lon = TALUK_COORDS.get(sel_taluk, (12.52, 76.90))
    district = TALUK_TO_DISTRICT.get(sel_taluk, "")

    st.markdown("---")
    st.markdown(f"**🔍 Viewing:** {sel_taluk}")
    st.markdown(f"**📍 District:** {district}")
    st.markdown(f"**📅 Today:** {date.today().strftime('%d %b %Y')}")

# ═══════════════════════════════════════════════════════════════
# PAGE 1: MORNING BRIEFING  — "What do I need to know TODAY?"
# ═══════════════════════════════════════════════════════════════
if page == "🌅 Morning Briefing":
    today = date.today()
    month = today.month
    season = ("Kharif" if 6<=month<=10 else "Rabi" if 11<=month<=2 else "Summer")

    st.markdown(f"# 🌅 Good Morning — {sel_taluk}")
    st.markdown(f"**{today.strftime('%A, %d %B %Y')}** · {season} Season · {district} District")
    st.markdown("---")

    # ── NDVI + Forecast + Rain in one row ─────────────────────────
    ndvi_df = load_ndvi_all()
    forecast = get_forecast(lat, lon)
    wdf_r    = load_weather_recent(sel_taluk, 7)

    # Today NDVI
    t_ndvi = ndvi_df[(ndvi_df["taluk"]==sel_taluk)&(ndvi_df["is_mock_data"]==False)]
    ndvi_val = t_ndvi.sort_values("sensing_date",ascending=False)["ndvi"].values[0] if not t_ndvi.empty else None
    nl, nc = ndvi_label(ndvi_val) if ndvi_val else ("⚪ No data","blue")

    # Today forecast
    f_tmax  = forecast.get("temperature_2m_max",[None])[0]
    f_tmin  = forecast.get("temperature_2m_min",[None])[0]
    f_rain  = forecast.get("precipitation_sum",[0])[0] or 0
    f_code  = forecast.get("weathercode",[0])[0] or 0
    f_icon  = wmo_icon(f_code, f_rain)

    # Rain this month
    wdf_all = load_weather_taluk(sel_taluk)
    if not wdf_all.empty:
        this_month_rain = wdf_all[wdf_all["date"].dt.month==month]["rainfall_mm"].sum()
        last_yr_same    = wdf_all[
            (wdf_all["date"].dt.month==month)&
            (wdf_all["date"].dt.year==today.year-1)
        ]["rainfall_mm"].sum()
        rain_diff_pct = ((this_month_rain - last_yr_same)/max(last_yr_same,1)*100) if last_yr_same else 0
    else:
        this_month_rain, last_yr_same, rain_diff_pct = 0, 0, 0

    # ── Top KPI strip ──────────────────────────────────────────────
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric(f"{f_icon} Today Max", f"{f_tmax:.0f}°C" if f_tmax else "—")
    c2.metric("🌡️ Today Min",  f"{f_tmin:.0f}°C" if f_tmin else "—")
    c3.metric("🌧️ Rain Today", f"{f_rain:.1f}mm")
    c4.metric("🌧️ This Month", f"{this_month_rain:.0f}mm",
              delta=f"{rain_diff_pct:+.0f}% vs last yr")
    c5.metric("🛰️ Field NDVI", f"{ndvi_val:.3f}" if ndvi_val else "—")

    st.markdown("---")

    # ── 7-day forecast strip ───────────────────────────────────────
    st.markdown('<div class="stitle">📅 7-Day Forecast</div>', unsafe_allow_html=True)
    days   = forecast.get("time",[])
    tmaxs  = forecast.get("temperature_2m_max",[])
    tmins  = forecast.get("temperature_2m_min",[])
    rains  = forecast.get("precipitation_sum",[])
    codes  = forecast.get("weathercode",[0]*7)

    fcols = st.columns(7)
    total_rain_7d = sum(rains) if rains else 0
    for i,(d,tm,tn,r,cd) in enumerate(zip(days,tmaxs,tmins,rains,codes)):
        dy = datetime.strptime(d,"%Y-%m-%d")
        icon = wmo_icon(cd, r)
        bg = "#dbeafe" if r > 5 else "#fff"
        with fcols[i]:
            st.markdown(f"""<div class="fcast" style="background:{bg}">
              <div class="day">{dy.strftime('%a')}</div>
              <div class="dt">{dy.strftime('%d %b')}</div>
              <div class="icon">{icon}</div>
              <div class="hi">{tm:.0f}°</div>
              <div class="lo">{tn:.0f}°</div>
              <div class="rn">💧 {r:.1f}mm</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── Farmer Action Signals ─────────────────────────────────────
    st.markdown('<div class="stitle">⚡ Today\'s Farming Signals</div>', unsafe_allow_html=True)

    signals = []

    # Rain signal
    if total_rain_7d > 50:
        signals.append(signal_box("🌧️", f"Heavy rain expected this week ({total_rain_7d:.0f}mm). Avoid spraying pesticides. Ensure drainage in fields.", "blue"))
    elif total_rain_7d > 10:
        signals.append(signal_box("🌦️", f"Moderate rain coming ({total_rain_7d:.0f}mm). Good for Kharif sowing if fields are prepared.", "green"))
    elif f_rain < 1 and month in [6,7,8,9]:
        signals.append(signal_box("⚠️", "No rain today. June–October is monsoon — if dry spell continues >10 days, consider irrigation.", "yellow"))
    else:
        signals.append(signal_box("☀️", f"Dry day expected. Good for field work, harvesting, or drying crops.", "green"))

    # NDVI signal
    if ndvi_val is not None:
        if ndvi_val < 0.15:
            signals.append(signal_box("🔴", f"Your area NDVI is very low ({ndvi_val:.3f}). Very few crops growing nearby. Supply will be SHORT → prices will be HIGH. Good time to grow vegetables.", "red"))
        elif ndvi_val < 0.3:
            signals.append(signal_box("🟡", f"NDVI moderate ({ndvi_val:.3f}). Average crop coverage. Normal supply expected.", "yellow"))
        else:
            signals.append(signal_box("🌿", f"NDVI healthy ({ndvi_val:.3f}). Good crop coverage in your area. Plan your harvest timing carefully — supply will be adequate.", "green"))

    # Season signal
    if month == 6:
        signals.append(signal_box("🌱", "June: Prime Kharif sowing time! Ragi, Maize, Groundnut, Paddy — sow before mid-July for best yields.", "green"))
    elif month == 7:
        signals.append(signal_box("🌱", "July: Last chance for Kharif sowing. Focus on Ragi, Maize, Arhar if not yet sown.", "yellow"))
    elif month in [10,11]:
        signals.append(signal_box("🌾", "Kharif harvest season. Monitor moisture — delay can reduce quality. Rabi planning: prepare fields for Onion, Sunflower, Horsegram.", "blue"))
    elif month == 11:
        signals.append(signal_box("🌱", "November: Rabi sowing time! Sunflower, Horsegram, Onion — best planted now.", "green"))

    for s in signals:
        st.markdown(s, unsafe_allow_html=True)

    st.markdown("---")

    # ── Compare my taluk NDVI vs neighbours ───────────────────────
    if not ndvi_df.empty and sel_dist != "All Districts":
        st.markdown('<div class="stitle">🗺️ My Taluk vs Neighbours — NDVI</div>', unsafe_allow_html=True)
        dist_taluks = DISTRICT_TALUKS_MAP.get(sel_dist, [])
        nb = ndvi_df[
            (ndvi_df["taluk"].isin(dist_taluks)) & (ndvi_df["is_mock_data"]==False)
        ].sort_values("sensing_date",ascending=False).drop_duplicates("taluk").copy()

        if not nb.empty:
            nb_s = nb.sort_values("ndvi",ascending=True)
            colors = [ndvi_color(v) for v in nb_s["ndvi"]]
            fig = go.Figure(go.Bar(
                x=nb_s["ndvi"], y=nb_s["taluk"], orientation="h",
                marker_color=colors,
                text=[f"{v:.3f}" for v in nb_s["ndvi"]],
                textposition="outside",
                textfont=dict(color="#334155"),
            ))
            fig.add_vline(x=ndvi_val or 0, line_dash="dash", line_color="#7c3aed", line_width=2,
                          annotation_text=f"← {sel_taluk}", annotation_font_color="#7c3aed")
            fig.update_layout(
                paper_bgcolor="#fff", plot_bgcolor="#f8fafc",
                font=dict(color="#334155",family="Inter"),
                title=f"NDVI Comparison — {sel_dist} District Taluks",
                xaxis=dict(title="NDVI",range=[0,0.7],showgrid=True,gridcolor="#e2e8f0"),
                yaxis=dict(showgrid=False),
                height=max(280, len(nb)*42),
                margin=dict(t=45,b=20,l=10,r=80),
            )
            st.plotly_chart(fig, use_container_width=True)

# ═══════════════════════════════════════════════════════════════
# PAGE 2: MY FIELD
# ═══════════════════════════════════════════════════════════════
elif page == "🌿 My Field":
    st.markdown(f"# 🌿 My Field — {sel_taluk}")
    st.markdown(f"**{district} District** · {lat}°N, {lon}°E")
    st.markdown("---")

    ndvi_df = load_ndvi_all()
    t_ndvi  = ndvi_df[(ndvi_df["taluk"]==sel_taluk)&(ndvi_df["is_mock_data"]==False)]
    wdf     = load_weather_taluk(sel_taluk)
    forecast = get_forecast(lat, lon)

    col1, col2 = st.columns([1,1])

    with col1:
        st.markdown('<div class="stitle">🛰️ Field Health (Satellite)</div>', unsafe_allow_html=True)
        if not t_ndvi.empty:
            latest = t_ndvi.sort_values("sensing_date",ascending=False).iloc[0]
            v = latest["ndvi"]
            nl, nc = ndvi_label(v)
            pct = max(0, min(100, v/0.65*100))
            color = ndvi_color(v)

            # Gauge chart
            fig_g = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=v,
                delta={"reference":0.35,"valueformat":".3f"},
                title={"text":"NDVI — Crop Greenness","font":{"size":14,"color":"#334155"}},
                number={"font":{"size":36,"color":color},"valueformat":".3f"},
                gauge={
                    "axis":{"range":[0,0.65],"tickwidth":1,"tickcolor":"#64748b"},
                    "bar":{"color":color,"thickness":0.3},
                    "bgcolor":"#f1f5f9",
                    "borderwidth":1,"bordercolor":"#e2e8f0",
                    "steps":[
                        {"range":[0,0.1],"color":"#fee2e2"},
                        {"range":[0.1,0.25],"color":"#fef3c7"},
                        {"range":[0.25,0.4],"color":"#dcfce7"},
                        {"range":[0.4,0.65],"color":"#bbf7d0"},
                    ],
                    "threshold":{"line":{"color":"#334155","width":2},"thickness":0.75,"value":0.35}
                }
            ))
            fig_g.update_layout(paper_bgcolor="#fff",height=240,margin=dict(t=30,b=10,l=30,r=30))
            st.plotly_chart(fig_g, use_container_width=True)
            st.markdown(f'<div class="signal signal-{nc}">{nl} — NDVI {v:.3f}</div>', unsafe_allow_html=True)
            st.caption(f"Last updated: {latest['sensing_date'].strftime('%d %b %Y')} · Sentinel-2 satellite")
        else:
            st.info("No NDVI data for this taluk.")

    with col2:
        st.markdown('<div class="stitle">🌦️ Weather This Week</div>', unsafe_allow_html=True)
        if forecast and forecast.get("time"):
            days  = forecast["time"][:7]
            tmaxs = forecast.get("temperature_2m_max",[])[:7]
            tmins = forecast.get("temperature_2m_min",[])[:7]
            rains = forecast.get("precipitation_sum",[])[:7]
            codes = forecast.get("weathercode",[0]*7)[:7]

            fig_f = make_subplots(specs=[[{"secondary_y":True}]])
            fig_f.add_trace(go.Bar(x=days, y=rains, name="Rain (mm)",
                                   marker_color="#60a5fa", opacity=0.8), secondary_y=True)
            fig_f.add_trace(go.Scatter(x=days, y=tmaxs, name="Max °C",
                                       line=dict(color="#dc2626",width=2.5)), secondary_y=False)
            fig_f.add_trace(go.Scatter(x=days, y=tmins, name="Min °C",
                                       line=dict(color="#2563eb",width=2),
                                       fill="tonexty", fillcolor="rgba(37,99,235,0.06)"), secondary_y=False)
            fig_f.update_layout(
                paper_bgcolor="#fff", plot_bgcolor="#f8fafc",
                font=dict(color="#334155",family="Inter"),
                title="7-Day Forecast", height=240,
                margin=dict(t=40,b=20,l=5,r=5),
                legend=dict(orientation="h",y=-0.2,bgcolor="#fff"),
            )
            fig_f.update_yaxes(title_text="Temperature (°C)",secondary_y=False,showgrid=True,gridcolor="#e2e8f0")
            fig_f.update_yaxes(title_text="Rain (mm)",secondary_y=True,showgrid=False)
            fig_f.update_xaxes(showgrid=False)
            st.plotly_chart(fig_f, use_container_width=True)

    # ── 30-day weather history ────────────────────────────────────
    st.markdown("---")
    st.markdown('<div class="stitle">📊 Last 30 Days — Field Conditions</div>', unsafe_allow_html=True)

    if not wdf.empty:
        wdf30 = wdf.tail(30).copy()
        k1,k2,k3,k4 = st.columns(4)
        k1.metric("🌡️ Avg Max Temp",  f"{wdf30['temp_max_c'].mean():.1f}°C")
        k2.metric("🌡️ Avg Min Temp",  f"{wdf30['temp_min_c'].mean():.1f}°C")
        k3.metric("🌧️ Total Rainfall", f"{wdf30['rainfall_mm'].sum():.0f}mm")
        k4.metric("💧 Avg Humidity",   f"{wdf30['humidity_pct'].mean():.0f}%")

        tab1,tab2,tab3 = st.tabs(["🌡️ Temperature","🌧️ Rainfall","🌿 ET₀ (Crop Water Need)"])

        with tab1:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=wdf30["date"],y=wdf30["temp_max_c"],name="Max Temp",line=dict(color="#dc2626",width=2.5)))
            fig.add_trace(go.Scatter(x=wdf30["date"],y=wdf30["temp_min_c"],name="Min Temp",line=dict(color="#2563eb",width=2),fill="tonexty",fillcolor="rgba(37,99,235,0.06)"))
            playout(fig); fig.update_yaxes(title="°C")
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            fig = px.bar(wdf30, x="date", y="rainfall_mm", color="rainfall_mm",
                color_continuous_scale=["#bfdbfe","#1d4ed8"],
                labels={"rainfall_mm":"Rain (mm)","date":"Date"},
                title="Daily Rainfall — Last 30 Days")
            playout(fig)
            st.plotly_chart(fig, use_container_width=True)

        with tab3:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=wdf30["date"],y=wdf30["et0_mm"],name="ET₀",
                fill="tozeroy",line=dict(color="#7c3aed",width=2),fillcolor="rgba(124,58,237,0.1)"))
            fig.update_layout(paper_bgcolor="#fff",plot_bgcolor="#f8fafc",
                font=dict(color="#334155",family="Inter"),height=380,margin=dict(t=45,b=20))
            fig.update_xaxes(showgrid=False); fig.update_yaxes(showgrid=True,gridcolor="#e2e8f0",title="ET₀ (mm/day)")
            st.markdown("ℹ️ ET₀ = how much water crops need per day. Higher = more irrigation required.")
            st.plotly_chart(fig, use_container_width=True)

# ═══════════════════════════════════════════════════════════════
# PAGE 3: RAIN & WEATHER (20-year historical)
# ═══════════════════════════════════════════════════════════════
elif page == "🌧️ Rain & Weather":
    st.markdown(f"# 🌧️ Rain & Weather — {sel_taluk}")
    st.markdown("**20 years of historical data (2005–2026) · Open-Meteo**")
    st.markdown("---")

    wdf = load_weather_taluk(sel_taluk)
    if wdf.empty:
        st.warning(f"No weather data for {sel_taluk}. Only Mandya taluks have 20-year data currently.")
        st.stop()

    wdf["year"]  = wdf["date"].dt.year
    wdf["month"] = wdf["date"].dt.month
    wdf["month_name"] = wdf["date"].dt.strftime("%b")

    # ── KPIs ─────────────────────────────────────────────────────
    k1,k2,k3,k4,k5 = st.columns(5)
    k1.metric("📅 Data Years",      f"{wdf['year'].nunique()}")
    k2.metric("🌧️ Total Records",   f"{len(wdf):,}")
    k3.metric("🌧️ Avg Annual Rain", f"{wdf.groupby('year')['rainfall_mm'].sum().mean():.0f}mm")
    k4.metric("🌡️ Avg Max Temp",    f"{wdf['temp_max_c'].mean():.1f}°C")
    k5.metric("💧 Avg Humidity",    f"{wdf['humidity_pct'].mean():.0f}%")

    st.markdown("---")
    tab1,tab2,tab3,tab4 = st.tabs(["🌧️ Annual Rainfall","📅 Monthly Pattern","🌡️ Temperature Trend","☀️ 20-Year Heatmap"])

    with tab1:
        ann = wdf.groupby("year")["rainfall_mm"].sum().reset_index()
        avg20 = ann["rainfall_mm"].mean()
        colors = ["#15803d" if v >= avg20 else "#dc2626" for v in ann["rainfall_mm"]]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=ann["year"],y=ann["rainfall_mm"],
            marker_color=colors,name="Annual Rain",
            text=[f"{v:.0f}" for v in ann["rainfall_mm"]],textposition="outside",
            textfont=dict(size=10,color="#334155")))
        fig.add_hline(y=avg20,line_dash="dash",line_color="#7c3aed",line_width=2,
                      annotation_text=f"20-yr avg: {avg20:.0f}mm",annotation_font_color="#7c3aed")
        fig.update_layout(paper_bgcolor="#fff",plot_bgcolor="#f8fafc",
            font=dict(color="#334155",family="Inter"),
            title=f"Annual Rainfall — {sel_taluk} (2005–2026)",
            yaxis_title="Rainfall (mm)",height=400,margin=dict(t=50,b=30))
        fig.update_xaxes(showgrid=False,dtick=1,tickangle=-45)
        fig.update_yaxes(showgrid=True,gridcolor="#e2e8f0")
        st.plotly_chart(fig, use_container_width=True)
        # Simple drought/flood analysis
        good = ann[ann["rainfall_mm"]>=avg20*0.9]
        poor = ann[ann["rainfall_mm"]<avg20*0.7]
        c1,c2 = st.columns(2)
        with c1:
            st.markdown(signal_box("🟢",f"Good rainfall years (≥90% avg): {', '.join(good['year'].astype(str).tolist()[-5:])}","green"),unsafe_allow_html=True)
        with c2:
            st.markdown(signal_box("🔴",f"Drought years (<70% avg): {', '.join(poor['year'].astype(str).tolist()) if not poor.empty else 'None in recent 5 yrs'}","red"),unsafe_allow_html=True)

    with tab2:
        mon = wdf.groupby(["year","month","month_name"])["rainfall_mm"].sum().reset_index()
        mon_avg = wdf.groupby("month")["rainfall_mm"].mean().reset_index()
        mon_names = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
        mon_avg["month_name"] = mon_avg["month"].map(mon_names)
        this_yr = mon[mon["year"]==date.today().year]

        fig = go.Figure()
        fig.add_trace(go.Bar(x=mon_avg["month_name"],y=mon_avg["rainfall_mm"],
            name="20-yr Monthly Avg",marker_color="#93c5fd",opacity=0.8))
        if not this_yr.empty:
            fig.add_trace(go.Scatter(x=this_yr["month_name"],y=this_yr["rainfall_mm"],
                name=f"{date.today().year}",line=dict(color="#dc2626",width=3),
                mode="lines+markers",marker=dict(size=8)))
        fig.update_layout(paper_bgcolor="#fff",plot_bgcolor="#f8fafc",
            font=dict(color="#334155",family="Inter"),
            title=f"Monthly Rainfall Pattern — {sel_taluk}",
            yaxis_title="Rainfall (mm)",height=400,barmode="overlay",margin=dict(t=50,b=30))
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=True,gridcolor="#e2e8f0")
        st.plotly_chart(fig, use_container_width=True)
        st.markdown(signal_box("💡","Peak monsoon: Jul–Oct. Pre-monsoon rain (May–Jun) is crucial for Kharif sowing timing.","blue"),unsafe_allow_html=True)

    with tab3:
        ann_temp = wdf.groupby("year")[["temp_max_c","temp_min_c"]].mean().reset_index()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=ann_temp["year"],y=ann_temp["temp_max_c"],name="Avg Max Temp",line=dict(color="#dc2626",width=2.5)))
        fig.add_trace(go.Scatter(x=ann_temp["year"],y=ann_temp["temp_min_c"],name="Avg Min Temp",line=dict(color="#2563eb",width=2),fill="tonexty",fillcolor="rgba(37,99,235,0.06)"))
        # Trend line
        import numpy as np
        z = np.polyfit(ann_temp["year"],ann_temp["temp_max_c"],1)
        trend_y = np.poly1d(z)(ann_temp["year"])
        fig.add_trace(go.Scatter(x=ann_temp["year"],y=trend_y,name="Warming Trend",
            line=dict(color="#7c3aed",width=1.5,dash="dot")))
        fig.update_layout(paper_bgcolor="#fff",plot_bgcolor="#f8fafc",
            font=dict(color="#334155",family="Inter"),
            title=f"Temperature Trend (20 years) — {sel_taluk}",
            yaxis_title="°C",height=400,margin=dict(t=50,b=30))
        fig.update_xaxes(showgrid=False,dtick=1,tickangle=-45)
        fig.update_yaxes(showgrid=True,gridcolor="#e2e8f0")
        st.plotly_chart(fig, use_container_width=True)
        temp_change = ann_temp["temp_max_c"].iloc[-1] - ann_temp["temp_max_c"].iloc[0]
        if abs(temp_change) > 0.5:
            direction = "risen" if temp_change > 0 else "fallen"
            st.markdown(signal_box("🌡️",f"Max temperature has {direction} by {abs(temp_change):.1f}°C over 20 years. Plan heat-tolerant crop varieties.","yellow"),unsafe_allow_html=True)

    with tab4:
        pivot = wdf.groupby(["year","month"])["rainfall_mm"].sum().reset_index()
        pivot["month_name"] = pivot["month"].map({1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"})
        heat_data = pivot.pivot(index="month_name",columns="year",values="rainfall_mm")
        month_order = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        heat_data = heat_data.reindex([m for m in month_order if m in heat_data.index])

        fig = px.imshow(heat_data, color_continuous_scale=["#fff7ed","#fed7aa","#60a5fa","#1d4ed8","#1e3a8a"],
                        title=f"Rainfall Heatmap (mm) — {sel_taluk} · Each cell = monthly total",
                        labels={"x":"Year","y":"Month","color":"mm"})
        fig.update_layout(paper_bgcolor="#fff",font=dict(color="#334155",family="Inter"),
                          height=420,margin=dict(t=50,b=20))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("🔵 Dark blue = very heavy rain · 🟠 Orange = dry month · White = no rain")

# ═══════════════════════════════════════════════════════════════
# PAGE 4: MARKET & PRICES
# ═══════════════════════════════════════════════════════════════
elif page == "💰 Market & Prices":
    st.markdown("# 💰 Market & Price Intelligence")
    st.markdown("**Supply signals from satellite + reference price ranges + best selling windows**")
    st.markdown("---")

    ndvi_df = load_ndvi_all()

    # ── Supply-Demand heatmap ─────────────────────────────────────
    st.markdown('<div class="stitle">🗺️ Supply Map — Where is crop growing? (NDVI)</div>', unsafe_allow_html=True)

    if not ndvi_df.empty:
        real = ndvi_df[ndvi_df["is_mock_data"]==False].sort_values("sensing_date",ascending=False).drop_duplicates("taluk").copy()

        # Filter by district
        if sel_dist != "All Districts":
            real = real[real["district"]==sel_dist]

        real["Supply"] = real["ndvi"].apply(lambda v:
            "🔴 Very Low"  if v < 0.1 else
            "🟠 Low"        if v < 0.25 else
            "🟡 Moderate"   if v < 0.4 else
            "🟢 Good")
        real["Price Outlook"] = real["ndvi"].apply(lambda v:
            "📈 Prices HIGH"       if v < 0.1 else
            "📈 Prices Above Avg"  if v < 0.25 else
            "➡️ Normal Prices"     if v < 0.4 else
            "📉 Prices may drop at harvest")

        # Color-coded table
        st.dataframe(
            real[["taluk","district","ndvi","Supply","Price Outlook"]]
            .sort_values("ndvi")
            .rename(columns={"taluk":"Taluk","district":"District","ndvi":"NDVI"}),
            use_container_width=True, hide_index=True, height=280
        )

    st.markdown("---")

    # ── Price range by crop ───────────────────────────────────────
    st.markdown('<div class="stitle">💰 Crop Price Reference — Karnataka Mandis</div>', unsafe_allow_html=True)

    # Filter by season
    month = date.today().month
    season_now = ("Kharif" if 6<=month<=10 else "Rabi" if 11<=month<=2 else "Summer")
    show_all = st.toggle("Show all crops", value=False)

    pdf_rows = []
    for crop,(mn,mx,season) in PRICE_RANGES.items():
        is_current = season_now in season or season=="All Seasons" or "Annual" in season
        if show_all or is_current:
            pdf_rows.append({"Crop":crop,"Min ₹":mn,"Max ₹":mx,"Avg ₹":(mn+mx)//2,"Season":season,"Current":is_current})

    pdf = pd.DataFrame(pdf_rows).sort_values("Avg ₹",ascending=False)

    c1,c2 = st.columns([2,1])
    with c1:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=pdf["Crop"],y=pdf["Min ₹"],name="Min Price",marker_color="#93c5fd"))
        fig.add_trace(go.Bar(x=pdf["Crop"],y=pdf["Max ₹"]-pdf["Min ₹"],name="Upside Range",
                             base=pdf["Min ₹"],marker_color="#1d4ed8"))
        fig.update_layout(barmode="stack",paper_bgcolor="#fff",plot_bgcolor="#f8fafc",
            font=dict(color="#334155",family="Inter"),
            title=f"Price Range — {season_now} Season Crops",
            yaxis_title="₹/quintal",height=420,margin=dict(t=50,b=100))
        fig.update_xaxes(tickangle=-40,showgrid=False)
        fig.update_yaxes(showgrid=True,gridcolor="#e2e8f0")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.markdown("**High profit potential crops:**")
        top = pdf.nlargest(6,"Max ₹")
        for _,r in top.iterrows():
            pct = int((r["Max ₹"]-r["Min ₹"])/r["Max ₹"]*100)
            st.markdown(f"""<div style="background:#fff;border-radius:10px;padding:10px 14px;
                margin:4px 0;box-shadow:0 1px 4px rgba(0,0,0,.08);border-left:4px solid #2d6a4f">
                <div style="font-weight:700;color:#1e293b;font-size:14px">{r['Crop']}</div>
                <div style="color:#15803d;font-size:13px">Max: ₹{r['Max ₹']:,}/quintal</div>
                <div style="color:#64748b;font-size:11px">Range: {pct}% upside · {r['Season']}</div>
                </div>""", unsafe_allow_html=True)

    # ── Best selling windows ──────────────────────────────────────
    st.markdown("---")
    st.markdown('<div class="stitle">📅 Best Selling Windows (Seasonal Price Intelligence)</div>', unsafe_allow_html=True)

    selling_tips = [
        ("🍅","Tomato",      "Jan–Feb & Jun",   "Supply low after winter harvest gap",    "#fee2e2"),
        ("🧅","Onion",       "Jun–Aug",          "Pre-kharif stock depletes, prices peak", "#fff7ed"),
        ("🥜","Groundnut",   "Apr–Jun",          "Before new Kharif arrives",              "#fef9c3"),
        ("🌾","Ragi",        "Jan–Mar",          "Festival demand + stock running out",    "#f0fdf4"),
        ("🌻","Sunflower",   "Jun–Aug",          "Oil mills buying before Kharif season",  "#fef9c3"),
        ("🥥","Coconut",     "Oct–Dec",          "Festive season demand spike",            "#eff6ff"),
    ]
    cols = st.columns(3)
    for i,(icon,crop,window,reason,bg) in enumerate(selling_tips):
        with cols[i%3]:
            st.markdown(f"""<div style="background:{bg};border-radius:12px;padding:14px;margin:4px 0;box-shadow:0 1px 4px rgba(0,0,0,.06)">
                <div style="font-size:24px">{icon}</div>
                <div style="font-weight:700;color:#1e293b;font-size:15px">{crop}</div>
                <div style="color:#15803d;font-weight:700;font-size:13px">Best: {window}</div>
                <div style="color:#475569;font-size:12px;margin-top:4px">{reason}</div>
                </div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# PAGE 5: REGION NDVI MAP
# ═══════════════════════════════════════════════════════════════
elif page == "🌍 Region NDVI Map":
    st.markdown("# 🌍 Region Crop Cover Map — All 50 Taluks")
    st.markdown("**Satellite NDVI · Today · Red=No crops, Green=Healthy crops**")
    st.markdown("---")

    ndvi_df = load_ndvi_all()
    if ndvi_df.empty:
        st.warning("No NDVI data available."); st.stop()

    real = ndvi_df[ndvi_df["is_mock_data"]==False].sort_values("sensing_date",ascending=False).drop_duplicates("taluk").copy()

    # Add coordinates
    real["lat"] = real["taluk"].map(lambda t: TALUK_COORDS.get(t,(0,0))[0])
    real["lon"] = real["taluk"].map(lambda t: TALUK_COORDS.get(t,(0,0))[1])
    real["color"] = real["ndvi"].apply(ndvi_color)
    real["status"] = real["ndvi"].apply(lambda v: ndvi_label(v)[0])
    real["supply"] = real["ndvi"].apply(lambda v:
        "Supply VERY LOW → Prices HIGH"  if v < 0.1 else
        "Supply Low → Prices above avg"  if v < 0.25 else
        "Supply Normal → Normal prices"  if v < 0.4 else
        "Good supply → Harvest coming")

    # ── Map using plotly scatter_geo ──────────────────────────────
    fig = px.scatter_mapbox(
        real, lat="lat", lon="lon",
        color="ndvi",
        color_continuous_scale=["#ef4444","#f97316","#eab308","#22c55e","#15803d"],
        range_color=[0, 0.6],
        size=[max(0.05, v)*40 for v in real["ndvi"]],
        size_max=30,
        hover_name="taluk",
        hover_data={"district":True,"ndvi":":.3f","status":True,"supply":True,"lat":False,"lon":False},
        zoom=7, center={"lat":12.8,"lon":77.0},
        mapbox_style="carto-positron",
        title="South Karnataka Dry Zone — Crop Cover Today",
        height=520,
    )
    fig.update_layout(paper_bgcolor="#fff",font=dict(color="#334155",family="Inter"),
                      margin=dict(t=50,b=10,l=0,r=0),
                      coloraxis_colorbar=dict(title="NDVI",tickvals=[0,.15,.3,.45,.6],
                                              ticktext=["Bare","Sparse","Moderate","Good","Dense"]))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("""<div style="display:flex;gap:12px;flex-wrap:wrap;margin:8px 0">
      <span style="background:#fee2e2;color:#991b1b;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:700">🔴 NDVI < 0.1 — Bare Soil</span>
      <span style="background:#ffedd5;color:#9a3412;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:700">🟠 0.1–0.25 — Very Sparse</span>
      <span style="background:#fef9c3;color:#854d0e;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:700">🟡 0.25–0.35 — Sparse</span>
      <span style="background:#dcfce7;color:#166534;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:700">🟢 0.35–0.5 — Moderate</span>
      <span style="background:#bbf7d0;color:#14532d;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:700">🌿 > 0.5 — Dense/Healthy</span>
    </div>""", unsafe_allow_html=True)

    st.markdown("---")
    # District ranking
    st.markdown('<div class="stitle">📊 District Ranking — Crop Greenness</div>', unsafe_allow_html=True)
    dist_rank = real.groupby("district").agg(
        avg_ndvi=("ndvi","mean"), max_ndvi=("ndvi","max"), min_ndvi=("ndvi","min"), taluks=("taluk","count")
    ).round(3).reset_index().sort_values("avg_ndvi",ascending=False)
    dist_rank["Rank"] = range(1, len(dist_rank)+1)
    dist_rank["Status"] = dist_rank["avg_ndvi"].apply(lambda v: ndvi_label(v)[0])
    st.dataframe(dist_rank[["Rank","district","avg_ndvi","min_ndvi","max_ndvi","taluks","Status"]]
                 .rename(columns={"district":"District","avg_ndvi":"Avg NDVI","min_ndvi":"Min","max_ndvi":"Max","taluks":"Taluks"}),
                 use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════════════
# PAGE 6: CROP CALENDAR
# ═══════════════════════════════════════════════════════════════
elif page == "📅 Crop Calendar":
    st.markdown(f"# 📅 Crop Calendar — {sel_taluk}")
    st.markdown(f"**What to plant · When to plant · Expected returns**")
    st.markdown("---")

    month = date.today().month
    season = ("Kharif" if 6<=month<=10 else "Rabi" if 11<=month<=2 else "Summer")

    st.markdown(f'<div class="signal signal-green">🗓️ Current Season: <b>{season}</b> · Month: <b>{date.today().strftime("%B %Y")}</b></div>', unsafe_allow_html=True)
    st.markdown("")

    # ── Calendar grid ─────────────────────────────────────────────
    st.markdown('<div class="stitle">🌾 Full Year Crop Calendar</div>', unsafe_allow_html=True)

    cal_data = {
        "Paddy":     {"sow":[6,7],"harvest":[10,11],"duration":"120-140 days","water":"High","profit":"Medium","season":"Kharif"},
        "Ragi":      {"sow":[6,7],"harvest":[10,11],"duration":"100-120 days","water":"Low","profit":"Medium","season":"Kharif+Rabi"},
        "Maize":     {"sow":[6,7],"harvest":[9,10], "duration":"90-100 days","water":"Medium","profit":"Medium","season":"Kharif"},
        "Groundnut": {"sow":[6,7],"harvest":[10,11],"duration":"105-120 days","water":"Low","profit":"High","season":"Kharif+Rabi"},
        "Sunflower": {"sow":[10,11],"harvest":[2,3],"duration":"90-100 days","water":"Medium","profit":"High","season":"Rabi"},
        "Onion":     {"sow":[10,11],"harvest":[2,3],"duration":"100-120 days","water":"Medium","profit":"High","season":"Rabi"},
        "Tomato":    {"sow":[6,10],"harvest":[9,2], "duration":"60-80 days","water":"High","profit":"Very High","season":"All"},
        "Horsegram": {"sow":[9,10],"harvest":[1,2], "duration":"90-100 days","water":"Very Low","profit":"Medium","season":"Rabi"},
        "Sugarcane": {"sow":[1,2],"harvest":[12,1], "duration":"12 months","water":"Very High","profit":"Stable","season":"Annual"},
    }

    MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    # Build calendar matrix
    rows = []
    for crop, info in cal_data.items():
        row = {"Crop": crop}
        for i, m in enumerate(MONTHS, 1):
            if i in info["sow"]:    row[m] = "🌱 Sow"
            elif i in info["harvest"]: row[m] = "🌾 Harvest"
            elif (min(info["sow"]) < i < max(info["harvest"]) or
                  (max(info["sow"]) < i or i < min(info["harvest"]) and info["harvest"][0] < info["sow"][0])):
                row[m] = "🌿 Growing"
            else:
                row[m] = ""
        row["Water"] = info["water"]
        row["Profit"] = info["profit"]
        rows.append(row)

    cal_df = pd.DataFrame(rows)
    st.dataframe(cal_df, use_container_width=True, hide_index=True, height=380)

    # ── Season crop cards ─────────────────────────────────────────
    st.markdown("---")
    st.markdown(f'<div class="stitle">🌱 Plant NOW — {season} Season Recommendations</div>', unsafe_allow_html=True)

    season_crops = {
        "Kharif": [
            ("🌾","Paddy",     "₹1,800–2,300/q","High water, canal/borewell needed","120-140 days"),
            ("🌿","Ragi",      "₹2,000–3,800/q","Low water, drought tolerant, ideal for dry areas","100-120 days"),
            ("🌽","Maize",     "₹1,400–2,400/q","Good for fodder + grain","90-100 days"),
            ("🥜","Groundnut", "₹5,000–8,000/q","Best profit in dry zone, needs sandy soil","105-120 days"),
            ("🍅","Tomato",    "₹500–28,000/q", "Highest profit but HIGH RISK — price very volatile","60-80 days"),
        ],
        "Rabi": [
            ("🌻","Sunflower", "₹5,000–7,500/q","Good oil crop, low input cost","90-100 days"),
            ("🧅","Onion",     "₹500–9,000/q",  "Very high profit if timing is right","100-120 days"),
            ("🫘","Horsegram", "₹4,500–8,500/q","Very low water, best for risky dry years","90-100 days"),
            ("🥔","Potato",    "₹700–3,200/q",  "Needs irrigation, good yield","90-100 days"),
        ],
        "Summer": [
            ("🫘","Moong",    "₹7,000–10,500/q","60 days, quick cash, low input","55-65 days"),
            ("🌿","Urad",     "₹6,000–8,000/q", "Short duration, good pulse price","60-70 days"),
        ],
    }

    crops_now = season_crops.get(season, season_crops["Kharif"])
    cols = st.columns(min(3, len(crops_now)))
    for i,(icon,crop,price_range,note,duration) in enumerate(crops_now):
        profit_color = "#15803d" if "High" in price_range or "28,000" in price_range else "#0369a1"
        with cols[i%3]:
            st.markdown(f"""<div class="card">
              <div style="font-size:32px">{icon}</div>
              <div style="font-weight:800;font-size:16px;color:#1e293b;margin:4px 0">{crop}</div>
              <div style="font-weight:700;color:{profit_color};font-size:14px">💰 {price_range}</div>
              <div style="color:#64748b;font-size:12px;margin-top:6px">⏱️ {duration}</div>
              <div style="color:#475569;font-size:12px;margin-top:4px;border-top:1px solid #e2e8f0;padding-top:6px">{note}</div>
            </div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# PAGE 7: SEASON ANALYSIS
# ═══════════════════════════════════════════════════════════════
elif page == "📊 Season Analysis":
    st.markdown(f"# 📊 Season Analysis — {sel_taluk}")
    st.markdown("**This year vs historical · Drought risk · Crop performance outlook**")
    st.markdown("---")

    wdf = load_weather_taluk(sel_taluk)
    if wdf.empty:
        st.warning(f"No historical weather data for {sel_taluk}. Available for Mandya district taluks only."); st.stop()

    wdf["year"]  = wdf["date"].dt.year
    wdf["month"] = wdf["date"].dt.month

    cur_yr = date.today().year
    wdf_cur = wdf[wdf["year"]==cur_yr]
    wdf_his = wdf[wdf["year"]<cur_yr]

    # ── This year vs historical ────────────────────────────────────
    st.markdown('<div class="stitle">🌧️ This Year vs 20-Year Average</div>', unsafe_allow_html=True)

    mon_his_avg = wdf_his.groupby("month")["rainfall_mm"].mean()
    mon_cur     = wdf_cur.groupby("month")["rainfall_mm"].sum() if not wdf_cur.empty else pd.Series()
    mon_5yr_avg = wdf[wdf["year"]>=cur_yr-5].groupby("month")["rainfall_mm"].mean()

    MNAMES = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
    months_so_far = sorted(wdf_cur["month"].unique()) if not wdf_cur.empty else list(range(1, date.today().month+1))

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[MNAMES[m] for m in range(1,13)],
        y=[mon_his_avg.get(m,0) for m in range(1,13)],
        name="20-yr Avg",marker_color="#bfdbfe",opacity=0.8))
    if not mon_cur.empty:
        fig.add_trace(go.Scatter(
            x=[MNAMES[m] for m in sorted(mon_cur.index)],
            y=[mon_cur.get(m,0) for m in sorted(mon_cur.index)],
            name=f"{cur_yr} Actual",line=dict(color="#dc2626",width=3),
            mode="lines+markers",marker=dict(size=10,symbol="circle")))
    fig.add_trace(go.Scatter(
        x=[MNAMES[m] for m in range(1,13)],
        y=[mon_5yr_avg.get(m,0) for m in range(1,13)],
        name="5-yr Avg",line=dict(color="#7c3aed",width=1.5,dash="dot")))
    fig.update_layout(paper_bgcolor="#fff",plot_bgcolor="#f8fafc",
        font=dict(color="#334155",family="Inter"),
        title=f"{cur_yr} Rainfall vs Historical — {sel_taluk}",
        yaxis_title="Rainfall (mm)",height=420,margin=dict(t=50,b=30),
        legend=dict(orientation="h",y=-0.15,bgcolor="#fff"))
    fig.update_xaxes(showgrid=False); fig.update_yaxes(showgrid=True,gridcolor="#e2e8f0")
    st.plotly_chart(fig, use_container_width=True)

    # ── Drought / Excess rain risk assessment ────────────────────
    st.markdown("---")
    st.markdown('<div class="stitle">⚡ Season Risk Assessment</div>', unsafe_allow_html=True)

    if not wdf_cur.empty:
        ann_cur = wdf_cur["rainfall_mm"].sum()
        ann_his = wdf_his.groupby("year")["rainfall_mm"].sum().mean()
        pct_vs_normal = (ann_cur - ann_his) / ann_his * 100

        r1,r2,r3 = st.columns(3)
        r1.metric("🌧️ This Year (so far)", f"{ann_cur:.0f}mm")
        r2.metric("📊 20-Yr Normal", f"{ann_his:.0f}mm")
        r3.metric("📈 vs Normal", f"{pct_vs_normal:+.1f}%",
                  delta_color="normal" if pct_vs_normal >= 0 else "inverse")

        if pct_vs_normal < -30:
            st.markdown(signal_box("🔴",f"DROUGHT RISK: {cur_yr} rainfall is {abs(pct_vs_normal):.0f}% BELOW normal. Consider drought-tolerant crops: Horsegram, Ragi. Avoid paddy without irrigation.","red"),unsafe_allow_html=True)
        elif pct_vs_normal < -15:
            st.markdown(signal_box("🟠",f"Below Normal: Rainfall {abs(pct_vs_normal):.0f}% below average. Plan for water-saving crops. Check irrigation sources.","yellow"),unsafe_allow_html=True)
        elif pct_vs_normal > 30:
            st.markdown(signal_box("🔵",f"EXCESS RAIN: {cur_yr} is {pct_vs_normal:.0f}% ABOVE normal. Risk of waterlogging, fungal disease. Ensure drainage. Delay sowing if fields wet.","blue"),unsafe_allow_html=True)
        else:
            st.markdown(signal_box("🟢",f"NORMAL Year: Rainfall within {abs(pct_vs_normal):.0f}% of average. Good conditions for all major Kharif crops.","green"),unsafe_allow_html=True)

    # ── Monthly comparison table ──────────────────────────────────
    st.markdown("---")
    st.markdown('<div class="stitle">📋 Month-by-Month Comparison</div>', unsafe_allow_html=True)
    rows = []
    for m in range(1, date.today().month+1):
        his_avg = mon_his_avg.get(m, 0)
        cur_val = mon_cur.get(m, 0) if not mon_cur.empty else 0
        diff    = cur_val - his_avg
        rows.append({
            "Month": MNAMES[m],
            f"{cur_yr} Rain (mm)": round(cur_val, 1),
            "20-yr Avg (mm)":      round(his_avg, 1),
            "Difference (mm)":     round(diff, 1),
            "Status": "🟢 Normal" if abs(diff) < his_avg*0.3 else ("🔴 Deficit" if diff < 0 else "🔵 Surplus"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    '<div style="text-align:center;color:#94a3b8;font-size:12px;padding:8px">'
    '🌾 Crop Intelligence Agent · South Karnataka Dry Zone · '
    '🛰️ Sentinel-2 NDVI · ☁️ Open-Meteo (20yr) · '
    '📊 Designed for farmers of Malavalli & 50 dry zone taluks'
    '</div>', unsafe_allow_html=True
)
