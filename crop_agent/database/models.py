"""SQLAlchemy ORM models for all database tables.

This module defines all 12 tables across 3 categories:
  - Raw Data Tables (Layer 1 — Ingestion output)
  - Feature Tables (Layer 2 — Engineering output)
  - Model & Prediction Tables (Layers 3 & 4)

Design Rules:
  - Every table has a district column for scalability (Phase 3: all Karnataka)
  - All timestamps are stored in UTC
  - Raw data is NEVER modified after ingestion — immutable audit trail
  - All foreign key constraints enforced at DB level
"""

import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — RAW DATA TABLES (Ingestion Output)
# These tables store exactly what was received from the source.
# NEVER modify raw data after insertion — anomalies go to anomaly_log instead.
# ═══════════════════════════════════════════════════════════════════════════════


class RawMandiPrice(Base):
    """Daily mandi price and arrivals data from Agmarknet / Karnataka APMC.

    One row per: date × crop × mandi_name combination.
    Source cross-verification rule: Agmarknet vs APMC must agree within
    CROSS_SOURCE_PRICE_TOLERANCE_PCT (15%) or the row is flagged in anomaly_log.
    """

    __tablename__ = "raw_mandi_prices"
    __table_args__ = (
        UniqueConstraint("date", "crop", "mandi_name", "source_id", name="uq_mandi_daily"),
        Index("ix_mandi_date_crop", "date", "crop"),
        Index("ix_mandi_district", "district"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime.date] = mapped_column(DateTime, nullable=False)
    crop: Mapped[str] = mapped_column(String(64), nullable=False)
    mandi_name: Mapped[str] = mapped_column(String(128), nullable=False)
    district: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(128), nullable=False, default="Karnataka")
    price_inr_per_qtl: Mapped[float] = mapped_column(Float, nullable=False)
    arrivals_qtl: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_price_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_price_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    modal_price_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "agmarknet", "apmc"
    ingested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class RawWeatherDaily(Base):
    """Daily weather observations from Open-Meteo and NASA POWER.

    One row per: date × latitude × longitude × source_name combination.
    Cross-verification: Open-Meteo vs NASA POWER must agree within
    CROSS_SOURCE_WEATHER_TOLERANCE_PCT (20%) on rainfall.
    """

    __tablename__ = "raw_weather_daily"
    __table_args__ = (
        UniqueConstraint("date", "latitude", "longitude", "source_name", name="uq_weather_daily"),
        Index("ix_weather_date", "date"),
        Index("ix_weather_district", "district"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime.date] = mapped_column(DateTime, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    district: Mapped[str] = mapped_column(String(128), nullable=False)
    source_name: Mapped[str] = mapped_column(String(64), nullable=False)  # "open_meteo" | "nasa_power"
    rainfall_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    temp_max_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    temp_min_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    solar_radiation_wm2: Mapped[float | None] = mapped_column(Float, nullable=True)
    evapotranspiration_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    ingested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class RawNdviSentinel(Base):
    """Satellite NDVI/EVI data from Sentinel-2 or MODIS.

    One row per: sensing_date × block_id × satellite_pass combination.
    NDVI = Normalized Difference Vegetation Index (0.0 to 1.0).
    EVI  = Enhanced Vegetation Index (better for dense canopy like sugarcane).
    Note: Populated by satellite_collector.py. Stubbed with mock data in Phase 1
    until a Google Earth Engine account is registered.
    """

    __tablename__ = "raw_ndvi_sentinel"
    __table_args__ = (
        UniqueConstraint("sensing_date", "block_id", "satellite_pass", name="uq_ndvi_daily"),
        Index("ix_ndvi_date", "sensing_date"),
        Index("ix_ndvi_district", "district"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sensing_date: Mapped[datetime.date] = mapped_column(DateTime, nullable=False)
    block_id: Mapped[str] = mapped_column(String(128), nullable=False)
    district: Mapped[str] = mapped_column(String(128), nullable=False)
    ndvi: Mapped[float | None] = mapped_column(Float, nullable=True)
    evi: Mapped[float | None] = mapped_column(Float, nullable=True)
    cloud_cover_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    satellite_pass: Mapped[str] = mapped_column(String(64), nullable=False)  # "sentinel2" | "modis"
    is_mock_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ingested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class RawSoilProperties(Base):
    """Soil property data from SoilGrids (ISRIC) — static, collected once per taluk.

    One row per taluk. Soil properties change on geological timescales,
    so this table is populated once and treated as permanent reference data.
    """

    __tablename__ = "raw_soil_properties"
    __table_args__ = (
        UniqueConstraint("taluk", "district", "source_id", name="uq_soil_taluk"),
        Index("ix_soil_district", "district"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taluk: Mapped[str] = mapped_column(String(128), nullable=False)
    district: Mapped[str] = mapped_column(String(128), nullable=False)
    soil_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ph: Mapped[float | None] = mapped_column(Float, nullable=True)
    organic_carbon_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    clay_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    sand_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    silt_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)  # "soilgrids" | "nbss_lup"
    collected_date: Mapped[datetime.date] = mapped_column(DateTime, nullable=False)
    ingested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class RawCropYieldHistory(Base):
    """Historical crop yield and production statistics per district.

    Source: ICRISAT data portal (data.gov.in) + Karnataka Agriculture Dept.
    One row per: year × season × district × crop combination.
    This table forms the ground truth for walk-forward model validation.
    """

    __tablename__ = "raw_crop_yield_history"
    __table_args__ = (
        UniqueConstraint("year", "season", "district", "crop", "source_id", name="uq_yield_history"),
        Index("ix_yield_year_crop", "year", "crop"),
        Index("ix_yield_district", "district"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    season: Mapped[str] = mapped_column(String(32), nullable=False)  # Kharif | Rabi | Summer | Annual
    district: Mapped[str] = mapped_column(String(128), nullable=False)
    taluk: Mapped[str | None] = mapped_column(String(128), nullable=True)
    crop: Mapped[str] = mapped_column(String(64), nullable=False)
    area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    production_tonnes: Mapped[float | None] = mapped_column(Float, nullable=True)
    yield_qtl_per_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)  # "icrisat" | "karnataka_agri"
    ingested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class RawInputCosts(Base):
    """Annual crop input cost data from eNAM portal and KVK Mandya.

    One row per: year × season × crop × district combination.
    Input costs are the denominator in the profit calculation.
    """

    __tablename__ = "raw_input_costs"
    __table_args__ = (
        UniqueConstraint("year", "season", "crop", "district", name="uq_input_costs"),
        Index("ix_costs_year_crop", "year", "crop"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    season: Mapped[str] = mapped_column(String(32), nullable=False)
    crop: Mapped[str] = mapped_column(String(64), nullable=False)
    district: Mapped[str] = mapped_column(String(128), nullable=False)
    seed_inr_per_acre: Mapped[float | None] = mapped_column(Float, nullable=True)
    fertilizer_inr_per_acre: Mapped[float | None] = mapped_column(Float, nullable=True)
    pesticide_inr_per_acre: Mapped[float | None] = mapped_column(Float, nullable=True)
    labor_inr_per_acre: Mapped[float | None] = mapped_column(Float, nullable=True)
    irrigation_inr_per_acre: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class RawNewsAlert(Base):
    """News articles and agricultural advisories from RSS feeds.

    Sources: IMD agri-met advisories, Doordarshan Kisan, ICAR alerts.
    One row per article. Used to detect pest outbreaks, disease warnings,
    and weather advisories that could affect yield or price.
    """

    __tablename__ = "raw_news_alerts"
    __table_args__ = (
        Index("ix_news_published_at", "published_at"),
        Index("ix_news_alert_type", "alert_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    published_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    alert_type: Mapped[str | None] = mapped_column(String(64), nullable=True)  # pest | weather | disease | market
    crop_mentioned: Mapped[str | None] = mapped_column(String(256), nullable=True)
    district_mentioned: Mapped[str | None] = mapped_column(String(256), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)  # LOW | MEDIUM | HIGH
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class RawGroundwaterLevel(Base):
    """Groundwater depth data (static water level in meters below ground level)
    for Karnataka taluks. Sourced from Karnataka State Groundwater Department / CGWB.
    """

    __tablename__ = "raw_groundwater_levels"
    __table_args__ = (
        UniqueConstraint("taluk", "district", "year", name="uq_groundwater_taluk_year"),
        Index("ix_groundwater_district", "district"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taluk: Mapped[str] = mapped_column(String(128), nullable=False)
    district: Mapped[str] = mapped_column(String(128), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    depth_m: Mapped[float | None] = mapped_column(Float, nullable=True)  # depth in meters below ground level
    ingested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — FEATURE TABLES (Engineering Output)
# Built from raw tables. These are the direct inputs to the ML models.
# ═══════════════════════════════════════════════════════════════════════════════


class FeatureWeatherSeasonal(Base):
    """Aggregated seasonal weather features per district per season per year.

    One row per: year × season × district combination.
    Built by feature_builder.py from raw_weather_daily.
    """

    __tablename__ = "features_weather_seasonal"
    __table_args__ = (
        UniqueConstraint("year", "season", "district", name="uq_weather_seasonal"),
        Index("ix_weather_feat_year", "year", "season"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    season: Mapped[str] = mapped_column(String(32), nullable=False)
    district: Mapped[str] = mapped_column(String(128), nullable=False)

    # Core rainfall features
    rainfall_mm_seasonal: Mapped[float | None] = mapped_column(Float, nullable=True)
    rainfall_mm_june: Mapped[float | None] = mapped_column(Float, nullable=True)
    rainfall_deviation_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    rainfall_normal_mm: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Temperature features
    temp_max_avg_seasonal: Mapped[float | None] = mapped_column(Float, nullable=True)
    temp_min_avg_seasonal: Mapped[float | None] = mapped_column(Float, nullable=True)
    gdd_seasonal: Mapped[float | None] = mapped_column(Float, nullable=True)
    heat_stress_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Binary shock signals
    drought_flag: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 0 or 1
    flood_flag: Mapped[int | None] = mapped_column(Integer, nullable=True)     # 0 or 1

    # Derived features
    humidity_avg_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    sunshine_hours_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    onset_monsoon_julian: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dry_spell_max_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    built_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class FeatureSatelliteSeasonal(Base):
    """Satellite-derived vegetation index features per crop per season per year.

    One row per: year × season × district × crop combination.
    Built from raw_ndvi_sentinel by feature_builder.py.
    """

    __tablename__ = "features_satellite_seasonal"
    __table_args__ = (
        UniqueConstraint("year", "season", "district", "crop", name="uq_satellite_seasonal"),
        Index("ix_satellite_feat_year", "year", "crop"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    season: Mapped[str] = mapped_column(String(32), nullable=False)
    district: Mapped[str] = mapped_column(String(128), nullable=False)
    crop: Mapped[str] = mapped_column(String(64), nullable=False)
    is_mock_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    ndvi_at_sowing: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_at_mid_season: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_at_pre_harvest: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_max_season: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_trend_slope: Mapped[float | None] = mapped_column(Float, nullable=True)
    evi_mid_season: Mapped[float | None] = mapped_column(Float, nullable=True)
    lst_avg_seasonal: Mapped[float | None] = mapped_column(Float, nullable=True)
    evapotranspiration_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    crop_area_ha_district: Mapped[float | None] = mapped_column(Float, nullable=True)

    built_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class FeatureMarketSeasonal(Base):
    """Market and price features per crop per season per year.

    One row per: year × season × crop × district combination.
    Built from raw_mandi_prices by feature_builder.py.
    CRITICAL: mandi_price_at_harvest is the TARGET variable — never an input feature.
    """

    __tablename__ = "features_market_seasonal"
    __table_args__ = (
        UniqueConstraint("year", "season", "crop", "district", name="uq_market_seasonal"),
        Index("ix_market_feat_year_crop", "year", "crop"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    season: Mapped[str] = mapped_column(String(32), nullable=False)
    crop: Mapped[str] = mapped_column(String(64), nullable=False)
    district: Mapped[str] = mapped_column(String(128), nullable=False)

    # Safe input features (no data leakage — all pre-sowing or lagged)
    mandi_price_3m_before_sowing: Mapped[float | None] = mapped_column(Float, nullable=True)
    mandi_price_last_year_harvest: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_volatility_3yr: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_seasonality_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    msp_current_year: Mapped[float | None] = mapped_column(Float, nullable=True)
    arrivals_district_last_month: Mapped[float | None] = mapped_column(Float, nullable=True)
    arrivals_yoy_change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    export_demand_flag: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0 or 1

    # TARGET variable — used only for model training, NEVER as an input feature
    mandi_price_at_harvest: Mapped[float | None] = mapped_column(Float, nullable=True)

    built_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class FeatureMaster(Base):
    """Master feature table — final joined features, direct input to ML models.

    One row per: year × season × crop × taluk combination.
    This is the output of the full feature engineering pipeline.
    All features from weather, satellite, market, and location tables joined here.
    """

    __tablename__ = "features_master"
    __table_args__ = (
        UniqueConstraint("year", "season", "crop", "taluk", "district", name="uq_master"),
        Index("ix_master_year_crop", "year", "crop"),
        Index("ix_master_district", "district"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    season: Mapped[str] = mapped_column(String(32), nullable=False)
    crop: Mapped[str] = mapped_column(String(64), nullable=False)
    district: Mapped[str] = mapped_column(String(128), nullable=False)
    taluk: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Location features
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    elevation_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    soil_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    soil_ph: Mapped[float | None] = mapped_column(Float, nullable=True)
    soil_organic_carbon_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    clay_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    irrigation_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    distance_to_mandi_km: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Weather features (from features_weather_seasonal)
    rainfall_mm_seasonal: Mapped[float | None] = mapped_column(Float, nullable=True)
    rainfall_deviation_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    temp_max_avg_seasonal: Mapped[float | None] = mapped_column(Float, nullable=True)
    temp_min_avg_seasonal: Mapped[float | None] = mapped_column(Float, nullable=True)
    gdd_seasonal: Mapped[float | None] = mapped_column(Float, nullable=True)
    drought_flag: Mapped[int | None] = mapped_column(Integer, nullable=True)
    flood_flag: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heat_stress_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    onset_monsoon_julian: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dry_spell_max_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Satellite features (from features_satellite_seasonal)
    ndvi_at_sowing: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_at_mid_season: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_at_pre_harvest: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_trend_slope: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Crop-specific features
    crop_duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_irrigated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sowing_date_julian: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Market features (safe — no leakage)
    mandi_price_3m_before_sowing: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_volatility_3yr: Mapped[float | None] = mapped_column(Float, nullable=True)
    msp_current_year: Mapped[float | None] = mapped_column(Float, nullable=True)
    arrivals_yoy_change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Input cost features
    total_input_cost_per_acre: Mapped[float | None] = mapped_column(Float, nullable=True)
    fertilizer_inr_per_acre: Mapped[float | None] = mapped_column(Float, nullable=True)
    labor_inr_per_acre: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Target variables (filled in from yield history / actual prices)
    actual_yield_qtl_per_acre: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_price_inr_per_qtl: Mapped[float | None] = mapped_column(Float, nullable=True)

    built_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class FeatureImportanceLog(Base):
    """Log of feature importance scores from each ML training run.

    One row per: model_version × feature_name combination.
    Used to track which features are contributing and to enforce the
    MIN_SHAP_VALUE and MIN_FEATURE_IMPORTANCE thresholds from settings.
    """

    __tablename__ = "feature_importance_log"
    __table_args__ = (
        Index("ix_feat_imp_model", "model_version"),
        Index("ix_feat_imp_run_date", "run_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_name: Mapped[str] = mapped_column(String(128), nullable=False)
    importance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    shap_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    included_in_model: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    run_date: Mapped[datetime.date] = mapped_column(DateTime, nullable=False)
    logged_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LAYERS 3 & 4 — MODEL & PREDICTION TABLES
# ═══════════════════════════════════════════════════════════════════════════════


class ModelEvaluationLog(Base):
    """Results of every walk-forward validation and monthly model retrain.

    One row per: model_type × train_end_year × predict_year combination.
    This is the primary audit trail for model quality. If MAPE drifts above
    threshold, the system automatically keeps the old model.
    """

    __tablename__ = "model_evaluation_log"
    __table_args__ = (
        Index("ix_eval_model_type", "model_type"),
        Index("ix_eval_run_date", "run_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_type: Mapped[str] = mapped_column(String(64), nullable=False)  # "yield" | "price" | "rank"
    crop: Mapped[str | None] = mapped_column(String(64), nullable=True)
    train_end_year: Mapped[int] = mapped_column(Integer, nullable=False)
    predict_year: Mapped[int] = mapped_column(Integer, nullable=False)
    yield_rmse: Mapped[float | None] = mapped_column(Float, nullable=True)
    yield_mape: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_mape: Mapped[float | None] = mapped_column(Float, nullable=True)
    rank_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    random_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feature_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed_threshold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_date: Mapped[datetime.date] = mapped_column(DateTime, nullable=False)
    logged_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class PredictionCurrent(Base):
    """Latest predictions for the current or upcoming season.

    One row per: crop × district × taluk × season × year combination.
    This table is what the Streamlit dashboard reads directly.
    Every prediction includes confidence score and data freshness timestamp.
    """

    __tablename__ = "predictions_current"
    __table_args__ = (
        UniqueConstraint("crop", "district", "taluk", "season", "year", name="uq_prediction"),
        Index("ix_pred_curr_season", "season", "year"),
        Index("ix_pred_curr_district", "district"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    crop: Mapped[str] = mapped_column(String(64), nullable=False)
    district: Mapped[str] = mapped_column(String(128), nullable=False)
    taluk: Mapped[str | None] = mapped_column(String(128), nullable=True)
    season: Mapped[str] = mapped_column(String(32), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)

    # Yield prediction
    pred_yield_qtl: Mapped[float | None] = mapped_column(Float, nullable=True)
    pred_yield_lower: Mapped[float | None] = mapped_column(Float, nullable=True)   # confidence interval low
    pred_yield_upper: Mapped[float | None] = mapped_column(Float, nullable=True)   # confidence interval high

    # Price prediction (P10 / P50 / P90)
    pred_price_p10: Mapped[float | None] = mapped_column(Float, nullable=True)    # pessimistic
    pred_price_p50: Mapped[float | None] = mapped_column(Float, nullable=True)    # expected
    pred_price_p90: Mapped[float | None] = mapped_column(Float, nullable=True)    # optimistic

    # Profit prediction
    pred_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_in_bad_year: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_in_good_year: Mapped[float | None] = mapped_column(Float, nullable=True)
    break_even_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    years_profitable_of_5: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Risk scoring
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)        # 0.0 to 1.0
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)     # LOW | MEDIUM | HIGH
    confidence_pct: Mapped[float | None] = mapped_column(Float, nullable=True)    # 0 to 100

    # Ranking
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Data freshness — dashboard shows this to farmer
    generated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    data_freshness_hrs: Mapped[float | None] = mapped_column(Float, nullable=True)


class PredictionHistory(Base):
    """Archive of all past predictions with actual outcomes filled after harvest.

    Same structure as predictions_current plus actual_yield, actual_price, actual_profit.
    This is how the system measures its own accuracy over time.
    """

    __tablename__ = "predictions_history"
    __table_args__ = (
        Index("ix_pred_hist_year", "year", "crop"),
        Index("ix_pred_hist_district", "district"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    crop: Mapped[str] = mapped_column(String(64), nullable=False)
    district: Mapped[str] = mapped_column(String(128), nullable=False)
    taluk: Mapped[str | None] = mapped_column(String(128), nullable=True)
    season: Mapped[str] = mapped_column(String(32), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    pred_yield_qtl: Mapped[float | None] = mapped_column(Float, nullable=True)
    pred_price_p50: Mapped[float | None] = mapped_column(Float, nullable=True)
    pred_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Filled after harvest with real observed values
    actual_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_profit: Mapped[float | None] = mapped_column(Float, nullable=True)

    generated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    actuals_filled_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)


class AnomalyLog(Base):
    """All data quality issues flagged by the validator.

    This is the single most important quality-assurance table.
    Every failed data check writes here. No step can fail silently.
    Dashboard checks this table and shows a warning if anomalies are recent.
    """

    __tablename__ = "anomaly_log"
    __table_args__ = (
        Index("ix_anomaly_flagged_at", "flagged_at"),
        Index("ix_anomaly_table", "table_name"),
        Index("ix_anomaly_resolved", "resolved"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    column_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False)   # range_violation | null_excess | cross_source_mismatch | ingestion_failure
    issue_detail: Mapped[str] = mapped_column(Text, nullable=False)
    source_a_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_b_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")  # LOW | MEDIUM | HIGH
    flagged_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentRunLog(Base):
    """Summary of every nightly agent execution.

    One row per nightly run. Written at the very end of the night agent
    (03:45 AM) after all 16 tasks complete. Dashboard reads this to show
    the farmer when the last update happened and if everything is healthy.
    """

    __tablename__ = "agent_run_log"
    __table_args__ = (
        Index("ix_agent_run_date", "run_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_date: Mapped[datetime.date] = mapped_column(DateTime, nullable=False, unique=True)
    tasks_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tasks_success: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tasks_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data_freshness_hrs: Mapped[float | None] = mapped_column(Float, nullable=True)
    predictions_generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    anomalies_flagged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    run_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")  # SUCCESS | PARTIAL | FAILED
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    logged_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
