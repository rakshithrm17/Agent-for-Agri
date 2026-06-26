"""Central configuration for Crop Intelligence Agent.

This module contains ALL application constants and configuration values.
NO magic numbers or hardcoded paths are allowed anywhere else in the codebase.
Every constant here has a descriptive name that explains its purpose.

Design principle: To change any threshold, URL, or setting, only this file
needs to change — no hunting through code files.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

# Load .env file from project root (wherever the file is run from)
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_FILE)


# ─── Helper to require env vars ────────────────────────────────────────────────
def _require_env(key: str, default: str = "") -> str:
    """Get an environment variable, returning default if not set.

    Args:
    ----
        key: The environment variable name.
        default: Default value if variable is not set.

    Returns:
    -------
        The value of the environment variable, or default.

    """
    return os.environ.get(key, default)


# ─── Application ────────────────────────────────────────────────────────────────
APP_ENV: Final[str] = _require_env("APP_ENV", "development")
LOG_LEVEL: Final[str] = _require_env("LOG_LEVEL", "INFO")
LOG_DIR: Final[Path] = Path(_require_env("LOG_DIR", "crop_agent/logs"))

# ─── Database ────────────────────────────────────────────────────────────────────
# Phase 1: SQLite (sqlite:///./crop_agent.db)
# Phase 2: PostgreSQL (postgresql+psycopg2://user:pass@host:5432/db)
DATABASE_URL: Final[str] = _require_env("DATABASE_URL", "sqlite:///./crop_agent.db")

# ─── Geography — South Karnataka Dry Zone ────────────────────────────────────────
#
# Agro-Climatic Zoning (UAS Bangalore / ICAR):
#   Zone 5 — Southern Dry Zone  : Mandya, Mysuru, Chamarajanagar
#   Zone 6 — Eastern Dry Zone   : Kolar, Chikkaballapura, Bangalore Rural, Ramanagara
#   Zone 7 — Northern Dry Zone  : Tumkuru, Chitradurga (southern belt)
#   Zone 3 — Southern Transition: Hassan (dry taluks only)
#
# EXCLUDED (different agro-climatic conditions — never compare with above):
#   Coastal Zone  : Dakshina Kannada, Udupi, Uttara Kannada coast
#   Malnad Zone   : Kodagu, Chikkamagaluru, Shivamogga hills, Hassan hills
#
# These taluks share: semi-arid climate, red/black soils, 600-900mm rainfall,
# similar crops (paddy, ragi, sugarcane, tomato, groundnut, onion), and
# similar mandi price dynamics. Comparing across these is valid and useful.

MANDYA_LATITUDE: Final[float] = float(_require_env("MANDYA_LATITUDE", "12.5234"))
MANDYA_LONGITUDE: Final[float] = float(_require_env("MANDYA_LONGITUDE", "76.8961"))
DEFAULT_DISTRICT: Final[str] = _require_env("DEFAULT_DISTRICT", "Mandya")
DEFAULT_STATE: Final[str] = _require_env("DEFAULT_STATE", "Karnataka")

# ── Zone 5: Southern Dry Zone ─────────────────────────────────────────────────────
MANDYA_TALUKS: Final[list[str]] = [
    "Mandya", "Maddur", "Malavalli", "Nagamangala",
    "Pandavapura", "Shrirangapattana", "Krishnarajapete",
]

MYSURU_TALUKS: Final[list[str]] = [
    "Mysuru", "Hunsur", "Nanjangud", "T. Narasipura",
    "Periyapatna", "H.D. Kote", "Tirumakudalu Narasipura",
]

CHAMARAJANAGAR_TALUKS: Final[list[str]] = [
    "Chamarajanagar", "Gundlupet", "Kollegal", "Yelandur",
]

# ── Zone 6: Eastern Dry Zone ──────────────────────────────────────────────────────
RAMANAGARA_TALUKS: Final[list[str]] = [
    "Ramanagara", "Channapatna", "Kanakapura", "Magadi",
]

BANGALORE_RURAL_TALUKS: Final[list[str]] = [
    "Devanahalli", "Doddaballapura", "Hosakote", "Nelamangala",
]

KOLAR_TALUKS: Final[list[str]] = [
    "Kolar", "Malur", "Mulbagal", "Srinivaspur", "Bangarpet",
]

CHIKKABALLAPURA_TALUKS: Final[list[str]] = [
    "Chikkaballapura", "Bagepalli", "Chintamani",
    "Gouribidanur", "Gudibanda", "Sidlaghatta",
]

# ── Zone 7 / Transition: Northern & Southern Transition ──────────────────────────
TUMKURU_TALUKS: Final[list[str]] = [
    "Tumkuru", "Tiptur", "Turuvekere", "Madhugiri",
    "Gubbi", "Sira", "Pavagada", "Kunigal",
]

HASSAN_DRY_TALUKS: Final[list[str]] = [
    # Dry/transition taluks only — Sakleshpur (Malnad) excluded
    "Hassan", "Arsikere", "Channarayapatna", "Holenarasipur", "Belur",
]

# ── Combined: All South Karnataka Dry Zone Taluks ────────────────────────────────
# Use this for cross-taluk supply/demand analysis and price comparison
SOUTH_KARNATAKA_DRY_ZONE_TALUKS: Final[list[str]] = (
    MANDYA_TALUKS
    + MYSURU_TALUKS
    + CHAMARAJANAGAR_TALUKS
    + RAMANAGARA_TALUKS
    + BANGALORE_RURAL_TALUKS
    + KOLAR_TALUKS
    + CHIKKABALLAPURA_TALUKS
    + TUMKURU_TALUKS
    + HASSAN_DRY_TALUKS
)

# District → taluk mapping (for grouping and display)
DISTRICT_TALUKS_MAP: Final[dict[str, list[str]]] = {
    "Mandya":         MANDYA_TALUKS,
    "Mysuru":         MYSURU_TALUKS,
    "Chamarajanagar": CHAMARAJANAGAR_TALUKS,
    "Ramanagara":     RAMANAGARA_TALUKS,
    "Bangalore Rural": BANGALORE_RURAL_TALUKS,
    "Kolar":          KOLAR_TALUKS,
    "Chikkaballapura": CHIKKABALLAPURA_TALUKS,
    "Tumkuru":        TUMKURU_TALUKS,
    "Hassan":         HASSAN_DRY_TALUKS,
}

# Taluk → district reverse lookup
TALUK_TO_DISTRICT: Final[dict[str, str]] = {
    taluk: district
    for district, taluks in DISTRICT_TALUKS_MAP.items()
    for taluk in taluks
}


# ─── Crops ────────────────────────────────────────────────────────────────────────
# NOTE: The full all-India crop catalog (100+ crops) lives in:
#       data/seeds/crops_catalog.csv   ← committed to GitHub (seed/reference data)
#
# Use crop_agent.config.catalog module to query the catalog:
#   from crop_agent.config.catalog import get_crop_names, get_crops_by_category
#
# Fallback Mandya Phase 1 crops — used only during bootstrap before catalog loads
MANDYA_DEFAULT_CROPS: Final[list[str]] = [
    "Paddy (Rice)",
    "Sugarcane",
    "Ragi",
    "Maize (Corn)",
    "Sunflower",
    "Groundnut",
    "Tomato",
    "Horsegram",
]

# Seasons — matches ICAR crop calendar
SEASONS: Final[list[str]] = ["Kharif", "Rabi", "Summer", "Annual"]

# ─── Prediction Validity Ranges ──────────────────────────────────────────────────
# Loaded dynamically from catalog at runtime:
#   from crop_agent.config.catalog import get_crop_validity_ranges
#   ranges = get_crop_validity_ranges()
#
# Hardcoded fallback below is ONLY used in unit tests or if catalog is unavailable.
# Source: ICRISAT + Agmarknet 2018-2024 historical data for Mandya district.
CROP_VALIDITY_RANGES_FALLBACK: Final[dict[str, dict[str, float]]] = {
    "Paddy (Rice)": {"yield_min": 8.0,  "yield_max": 35.0,  "price_min": 1400.0,  "price_max": 3500.0},
    "Sugarcane":    {"yield_min": 150.0,"yield_max": 450.0, "price_min": 2800.0,  "price_max": 4200.0},
    "Ragi":         {"yield_min": 4.0,  "yield_max": 20.0,  "price_min": 1500.0,  "price_max": 3500.0},
    "Maize (Corn)": {"yield_min": 10.0, "yield_max": 40.0,  "price_min": 1200.0,  "price_max": 2800.0},
    "Sunflower":    {"yield_min": 3.0,  "yield_max": 14.0,  "price_min": 4000.0,  "price_max": 7500.0},
    "Groundnut":    {"yield_min": 5.0,  "yield_max": 18.0,  "price_min": 4500.0,  "price_max": 8000.0},
    "Tomato":       {"yield_min": 40.0, "yield_max": 200.0, "price_min": 100.0,   "price_max": 30000.0},
    "Horsegram":    {"yield_min": 2.0,  "yield_max": 10.0,  "price_min": 4000.0,  "price_max": 9000.0},
}

# ─── Anti-Hallucination Thresholds ──────────────────────────────────────────────
# Section 5 of spec — every threshold named, never a bare number
CROSS_SOURCE_PRICE_TOLERANCE_PCT: Final[float] = 15.0   # % diff before flagging mandi price
CROSS_SOURCE_WEATHER_TOLERANCE_PCT: Final[float] = 20.0  # % diff before flagging weather data
MAX_NULL_PCT_ALLOWED: Final[float] = 5.0                 # % nulls before blocking feature column
DROUGHT_THRESHOLD_PCT: Final[float] = 75.0               # seasonal rainfall < 75% of normal
FLOOD_THRESHOLD_PCT: Final[float] = 150.0                # seasonal rainfall > 150% of normal
HEAT_STRESS_TEMP_C: Final[float] = 35.0                  # days above this = heat stress
MIN_SHAP_VALUE: Final[float] = 0.01                      # feature dropped if SHAP below this
MIN_CORRELATION: Final[float] = 0.10                     # feature dropped if corr below this
MIN_FEATURE_IMPORTANCE: Final[float] = 0.005             # XGBoost feature_importance_ threshold

# ─── Model Quality Thresholds (Walk-Forward Pass/Fail) ─────────────────────────
# Phase targets from spec Section 6.4
YIELD_MAPE_THRESHOLD_PHASE1: Final[float] = 18.0  # % — Phase 1 baseline target
YIELD_MAPE_THRESHOLD_PHASE2: Final[float] = 15.0  # % — Phase 2 target
YIELD_MAPE_THRESHOLD_PHASE3: Final[float] = 12.0  # % — Phase 3 target
PRICE_MAPE_THRESHOLD_PHASE1: Final[float] = 20.0  # % — Phase 1 baseline target
PRICE_MAPE_THRESHOLD_PHASE2: Final[float] = 17.0  # % — Phase 2 target
PRICE_MAPE_THRESHOLD_PHASE3: Final[float] = 15.0  # % — Phase 3 target
MODEL_DRIFT_ALERT_MAPE: Final[float] = 15.0        # Trigger retraining if live MAPE drifts above

# ─── Risk Scoring Weights ────────────────────────────────────────────────────────
PRICE_RISK_WEIGHT: Final[float] = 0.6   # 60% weight on price volatility
YIELD_RISK_WEIGHT: Final[float] = 0.4   # 40% weight on yield volatility

# Risk thresholds — score 0.0 to 1.0
RISK_LOW_MAX: Final[float] = 0.35
RISK_MEDIUM_MAX: Final[float] = 0.65
# score > RISK_MEDIUM_MAX → HIGH risk

# Historical window for risk calculation (years)
RISK_HISTORY_YEARS: Final[int] = 5

# ─── Weather Features ────────────────────────────────────────────────────────────
# Kharif season months (June to November)
KHARIF_START_MONTH: Final[int] = 6
KHARIF_END_MONTH: Final[int] = 11

# Rabi season months (November to March)
RABI_START_MONTH: Final[int] = 11
RABI_END_MONTH: Final[int] = 3

# Summer season months (March to May)
SUMMER_START_MONTH: Final[int] = 3
SUMMER_END_MONTH: Final[int] = 5

# GDD base temperatures by crop (°C) — Growing Degree Days calculation
GDD_BASE_TEMP: Final[dict[str, float]] = {
    "Paddy": 10.0,
    "Sugarcane": 12.0,
    "Ragi": 8.0,
    "Maize": 10.0,
    "Sunflower": 6.0,
    "Groundnut": 10.0,
    "Tomato": 10.0,
    "Horsegram": 8.0,
}

# ─── Night Agent Scheduler ───────────────────────────────────────────────────────
NIGHT_AGENT_HOUR: Final[int] = int(_require_env("NIGHT_AGENT_HOUR", "1"))
NIGHT_AGENT_MINUTE: Final[int] = int(_require_env("NIGHT_AGENT_MINUTE", "0"))
MONTHLY_RETRAIN_HOUR: Final[int] = int(_require_env("MONTHLY_RETRAIN_HOUR", "3"))
MONTHLY_RETRAIN_MINUTE: Final[int] = int(_require_env("MONTHLY_RETRAIN_MINUTE", "0"))

# Task retry configuration
MAX_INGESTION_RETRIES: Final[int] = 3
RETRY_DELAY_SECONDS: Final[int] = 30

# ─── API URLs ────────────────────────────────────────────────────────────────────
OPEN_METEO_BASE_URL: Final[str] = _require_env(
    "OPEN_METEO_BASE_URL",
    "https://api.open-meteo.com/v1/forecast",
)
OPEN_METEO_ARCHIVE_URL: Final[str] = _require_env(
    "OPEN_METEO_ARCHIVE_URL",
    "https://archive-api.open-meteo.com/v1/archive",
)
NASA_POWER_BASE_URL: Final[str] = _require_env(
    "NASA_POWER_BASE_URL",
    "https://power.larc.nasa.gov/api/temporal/daily/point",
)
SOILGRIDS_BASE_URL: Final[str] = _require_env(
    "SOILGRIDS_BASE_URL",
    "https://rest.soilgrids.org/soilgrids/v2.0/properties/query",
)
AGMARKNET_API_KEY: Final[str] = _require_env("AGMARKNET_API_KEY", "")
AGMARKNET_BASE_URL: Final[str] = _require_env(
    "AGMARKNET_BASE_URL",
    "https://api.data.gov.in/resource/35985678-0d79-46b4-9ed6-6f13308a1d24",
)
IMD_RSS_URL: Final[str] = _require_env(
    "IMD_RSS_URL",
    "https://mausam.imd.gov.in/imd_latest/contents/rss/cyclone_warning.xml",
)
DD_KISAN_RSS_URL: Final[str] = _require_env(
    "DD_KISAN_RSS_URL",
    "https://ddkisan.gov.in/rss",
)

# ─── Storage Paths ────────────────────────────────────────────────────────────────
MODELS_DIR: Final[Path] = Path(_require_env("MODELS_DIR", "crop_agent/models"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# ─── Dashboard ────────────────────────────────────────────────────────────────────
DASHBOARD_PAGE_TITLE: Final[str] = _require_env(
    "DASHBOARD_PAGE_TITLE",
    "🌾 Crop Intelligence Agent — Mandya",
)
DASHBOARD_HOST: Final[str] = _require_env("DASHBOARD_HOST", "localhost")
DASHBOARD_PORT: Final[int] = int(_require_env("DASHBOARD_PORT", "8501"))

# Dashboard performance — data must be pre-computed, not queried at load time
DASHBOARD_MAX_LOAD_SECONDS: Final[int] = 3

# ─── Open-Meteo Variables to Collect ────────────────────────────────────────────
# Variable names as defined in the Open-Meteo API spec
OPEN_METEO_DAILY_VARIABLES: Final[list[str]] = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "relative_humidity_2m_max",
    "relative_humidity_2m_min",
    "wind_speed_10m_max",
    "shortwave_radiation_sum",
    "et0_fao_evapotranspiration",
]

# ─── NASA POWER Variables to Collect ─────────────────────────────────────────────
NASA_POWER_PARAMETERS: Final[str] = (
    "T2M_MAX,T2M_MIN,PRECTOTCORR,RH2M,WS10M,ALLSKY_SFC_SW_DWN"
)

# ─── SoilGrids Properties to Collect ─────────────────────────────────────────────
SOILGRIDS_PROPERTIES: Final[list[str]] = [
    "phh2o",
    "soc",
    "clay",
    "sand",
    "silt",
]
SOILGRIDS_DEPTHS: Final[list[str]] = [
    "0-5cm",
    "5-15cm",
    "15-30cm",
]

# ─── Feature Engineering Constants ───────────────────────────────────────────────
# Training data start year — use historical data from this year onwards
TRAINING_DATA_START_YEAR: Final[int] = 2020

# Minimum years of data required to train a model
MIN_TRAINING_YEARS: Final[int] = 3

# Optuna hyperparameter tuning — number of trials per training run
OPTUNA_N_TRIALS: Final[int] = 50

# Prophet price forecasting — months ahead to predict
PRICE_FORECAST_MONTHS: Final[int] = 6

# Quantile regression targets for price model
PRICE_QUANTILE_LOW: Final[float] = 0.10   # P10 — pessimistic scenario
PRICE_QUANTILE_MID: Final[float] = 0.50   # P50 — expected scenario
PRICE_QUANTILE_HIGH: Final[float] = 0.90  # P90 — optimistic scenario


@dataclass
class CropCalendar:
    """ICAR crop calendar entry for a single crop-season combination.

    Attributes
    ----------
        crop: The crop name.
        season: The growing season (Kharif/Rabi/Summer/Annual).
        sowing_start_month: Month when sowing typically begins (1-12).
        sowing_end_month: Month when sowing window closes (1-12).
        harvest_month: Typical harvest month (1-12).
        duration_days: Typical crop duration from sowing to harvest in days.

    """

    crop: str
    season: str
    sowing_start_month: int
    sowing_end_month: int
    harvest_month: int
    duration_days: int


# ICAR crop calendar for Mandya district — source: ICAR Crop Production Guide Karnataka
CROP_CALENDAR: Final[list[CropCalendar]] = [
    CropCalendar("Paddy",     "Kharif",  6,  7,  11, 120),
    CropCalendar("Paddy",     "Rabi",    11, 12, 3,  120),
    CropCalendar("Sugarcane", "Annual",  1,  3,  12, 365),
    CropCalendar("Ragi",      "Kharif",  6,  7,  10, 100),
    CropCalendar("Ragi",      "Rabi",    10, 11, 2,  100),
    CropCalendar("Maize",     "Kharif",  6,  7,  10, 110),
    CropCalendar("Maize",     "Rabi",    11, 12, 3,  110),
    CropCalendar("Sunflower", "Rabi",    10, 11, 2,  95),
    CropCalendar("Sunflower", "Summer",  1,  2,  5,  95),
    CropCalendar("Groundnut", "Kharif",  6,  7,  10, 110),
    CropCalendar("Groundnut", "Rabi",    10, 11, 2,  110),
    CropCalendar("Tomato",    "Kharif",  6,  7,  10, 90),
    CropCalendar("Tomato",    "Rabi",    10, 11, 1,  90),
    CropCalendar("Tomato",    "Summer",  1,  2,  5,  90),
    CropCalendar("Horsegram", "Rabi",    10, 11, 1,  75),
    CropCalendar("Horsegram", "Summer",  2,  3,  5,  75),
]
