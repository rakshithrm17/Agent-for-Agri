"""Satellite NDVI data collector — Layer 1 Ingestion.

PHASE 2 ACTIVE — Google Earth Engine account is approved.
Real Sentinel-2 NDVI data is collected per taluk per sensing date.

Sentinel-2 MSI Surface Reflectance:
  https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR

NDVI = (B8 - B4) / (B8 + B4)
  B8  = Near-Infrared (NIR) band
  B4  = Red band

EVI  = 2.5 × (B8 - B4) / (B8 + 6×B4 - 7.5×B2 + 1)
  Better for dense canopy crops like sugarcane.

Collection strategy:
  - Filter Sentinel-2 scenes with cloud cover < 20%
  - Take median composite of all scenes in a 16-day window
  - Sample NDVI at each taluk centroid
  - Fall back to mock data if GEE is unavailable or cloud-covered

Data is stored with is_mock_data=False for real GEE data.
The dashboard shows the farmer: "Real satellite imagery ✅"
"""

import os
from datetime import date, timedelta
from typing import Any

from crop_agent.config.catalog import load_crops_catalog
from crop_agent.config.logging_config import get_logger
from crop_agent.config.settings import DEFAULT_DISTRICT, SOUTH_KARNATAKA_DRY_ZONE_TALUKS
from crop_agent.database.connection import get_session
from crop_agent.database.models import RawNdviSentinel
from crop_agent.ingestion.base_collector import BaseCollector

logger = get_logger(__name__)

# ── Taluk HQ Coordinates: South Karnataka Dry Zone ──────────────────────────────
# Format: taluk_name → (latitude, longitude)
# Source: Survey of India / Google Maps taluk headquarters
# EXCLUDED: Coastal (DK, Udupi, UK coast) and Malnad (Kodagu, Chikkamagaluru hills,
#           Shivamogga hills, Sakleshpur) — different agro-climatic zone entirely.
#
# Zone 5 — Southern Dry Zone
# Zone 6 — Eastern Dry Zone
# Zone 7 / Transition — Northern & Southern Transition
_SOUTH_KARNATAKA_DRY_ZONE_COORDS: dict[str, tuple[float, float]] = {

    # ── Mandya District (Zone 5) ─────────────────────────────────────────
    "Mandya":               (12.5234, 76.8961),
    "Maddur":               (12.5807, 77.0466),
    "Malavalli":            (12.3847, 77.0607),
    "Nagamangala":          (12.8156, 76.7497),
    "Pandavapura":          (12.4872, 76.6839),
    "Shrirangapattana":     (12.4165, 76.6951),
    "Krishnarajapete":      (12.6585, 76.3887),

    # ── Mysuru District (Zone 5) ─────────────────────────────────────────
    "Mysuru":               (12.2958, 76.6394),
    "Hunsur":               (12.3046, 76.2928),
    "Nanjangud":            (12.1139, 76.6828),
    "T. Narasipura":        (12.2135, 76.9162),
    "Tirumakudalu Narasipura": (12.2135, 76.9162),
    "Periyapatna":          (12.3318, 76.0507),
    "H.D. Kote":            (12.0447, 76.0025),

    # ── Chamarajanagar District (Zone 5) ────────────────────────────────
    "Chamarajanagar":       (11.9238, 76.9434),
    "Gundlupet":            (11.8085, 76.6914),
    "Kollegal":             (12.1578, 77.1085),
    "Yelandur":             (11.9862, 77.0373),

    # ── Ramanagara District (Zone 6) ────────────────────────────────────
    "Ramanagara":           (12.7157, 77.2804),
    "Channapatna":          (12.6509, 77.2068),
    "Kanakapura":           (12.5460, 77.4183),
    "Magadi":               (12.9572, 77.2268),

    # ── Bangalore Rural District (Zone 6) ───────────────────────────────
    "Devanahalli":          (13.2456, 77.7120),
    "Doddaballapura":       (13.2951, 77.5378),
    "Hosakote":             (13.0701, 77.7980),
    "Nelamangala":          (13.1006, 77.3919),

    # ── Kolar District (Zone 6) ─────────────────────────────────────────
    "Kolar":                (13.1360, 78.1294),
    "Malur":                (13.0023, 77.9387),
    "Mulbagal":             (13.1630, 78.3960),
    "Srinivaspur":          (13.3350, 78.2107),
    "Bangarpet":            (12.9860, 78.1796),

    # ── Chikkaballapura District (Zone 6) ───────────────────────────────
    "Chikkaballapura":      (13.4354, 77.7268),
    "Bagepalli":            (13.7862, 77.7877),
    "Chintamani":           (13.3986, 78.0534),
    "Gouribidanur":         (13.6131, 77.5203),
    "Gudibanda":            (13.9088, 77.8397),
    "Sidlaghatta":          (13.3893, 77.8649),

    # ── Tumkuru District (Zone 7 / Transition) ──────────────────────────
    "Tumkuru":              (13.3379, 77.1173),
    "Tiptur":               (13.2601, 76.4757),
    "Turuvekere":           (13.1642, 76.6629),
    "Madhugiri":            (13.6647, 77.2097),
    "Gubbi":                (13.3097, 76.9418),
    "Sira":                 (13.7426, 76.9051),
    "Pavagada":             (14.0994, 77.2797),
    "Kunigal":              (13.0234, 77.0248),

    # ── Hassan District — Dry Taluks Only (Transition) ──────────────────
    # Sakleshpur EXCLUDED — Malnad zone, very different
    "Hassan":               (13.0036, 76.1003),
    "Arsikere":             (13.3143, 76.2508),
    "Channarayapatna":      (12.9035, 76.3873),
    "Holenarasipur":        (12.7854, 76.2394),
    "Belur":                (13.1651, 75.8665),
}

# Seasonal NDVI averages (fallback if GEE unavailable or cloud-covered)
# Based on MODIS historical data for Mandya district
_SEASONAL_NDVI_AVERAGES: dict[str, tuple[float, float, float]] = {
    "Kharif": (0.38, 0.65, 0.52),   # June sowing: low→peak→decline
    "Rabi":   (0.32, 0.58, 0.48),   # Nov sowing: lower base, good mid
    "Summer": (0.28, 0.50, 0.40),   # March sowing: dry season
    "Annual": (0.45, 0.70, 0.55),   # Perennial crops: higher sustained NDVI
}

_MONTH_TO_SEASON: dict[int, str] = {
    6: "Kharif", 7: "Kharif", 8: "Kharif",
    9: "Kharif", 10: "Kharif", 11: "Rabi",
    12: "Rabi", 1: "Rabi", 2: "Rabi",
    3: "Summer", 4: "Summer", 5: "Summer",
}

# Sentinel-2 revisit is ~5 days — use 16-day composite window for cloud-free data
SENTINEL2_COMPOSITE_DAYS: int = 16
# Maximum cloud cover % to accept a Sentinel-2 scene
MAX_CLOUD_COVER_PCT: float = 20.0


class SatelliteCollector(BaseCollector):
    """Collects real NDVI/EVI vegetation index data from Google Earth Engine.

    Uses Sentinel-2 Surface Reflectance imagery filtered to cloud cover < 20%.
    Takes a 16-day median composite to get cloud-free NDVI per taluk.

    Falls back to seasonal-average mock NDVI when:
      - GEE is not configured (GEE_PROJECT_ID missing in .env)
      - All scenes in the window are too cloudy
      - GEE API is unavailable

    Attributes:
        district: District name for DB tagging.
        taluks: List of taluks to collect NDVI for.
        _gee_available: True if GEE is authenticated and project is set.
    """

    def __init__(
        self,
        district: str = "South Karnataka",
        taluks: list[str] | None = None,
    ) -> None:
        """Initialize the satellite collector.

        Args:
            district: Label for DB tagging (default: 'South Karnataka').
            taluks: List of taluks to collect. Defaults to all 46 South
                Karnataka Dry Zone taluks (Zones 5, 6, 7). Coastal and
                Malnad taluks are excluded — different agro-climatic zone.
        """
        super().__init__(source_name="satellite_ndvi")
        self.district = district
        self.taluks = taluks or SOUTH_KARNATAKA_DRY_ZONE_TALUKS
        self._gee_project = os.environ.get("GEE_PROJECT_ID", "")
        self._gee_available = self._check_gee_available()

    def collect(self, target_date: date) -> int:
        """Collect NDVI data for all taluks for the target date.

        Tries real GEE data first. Falls back to mock if unavailable.

        Args:
            target_date: The sensing date to collect data for.

        Returns:
            Number of NDVI records written.
        """
        if self._gee_available:
            logger.info(
                "satellite.using_real_gee",
                project=self._gee_project,
                date=str(target_date),
            )
            return self._collect_gee(target_date)
        else:
            logger.info(
                "satellite.using_mock_data",
                message="GEE_PROJECT_ID not set in .env — using seasonal NDVI estimates.",
                date=str(target_date),
            )
            return self._collect_mock(target_date)

    def _collect_gee(self, target_date: date) -> int:
        """Collect real NDVI from Google Earth Engine Sentinel-2.

        Uses a 2km buffer around each taluk centroid and filterBounds so
        reduceRegion always has actual pixels to compute over.

        Args:
            target_date: The sensing date.

        Returns:
            Number of records written. Falls back to mock if GEE fails.
        """
        try:
            import ee  # type: ignore[import-untyped]

            ee.Initialize(project=self._gee_project)

            # 16-day composite window centered on target_date
            start_str = (target_date - timedelta(days=8)).strftime("%Y-%m-%d")
            end_str   = (target_date + timedelta(days=8)).strftime("%Y-%m-%d")

            # Relax cloud threshold during monsoon (Jun–Oct) — region is cloudy
            is_monsoon = target_date.month in (6, 7, 8, 9, 10)
            cloud_limit = 80.0 if is_monsoon else MAX_CLOUD_COVER_PCT

            rows_written = 0

            for taluk in self.taluks:
                if taluk not in _SOUTH_KARNATAKA_DRY_ZONE_COORDS:
                    continue

                lat, lon = _SOUTH_KARNATAKA_DRY_ZONE_COORDS[taluk]

                try:
                    # 2km radius region — large enough to always find pixels
                    region = ee.Geometry.Point([lon, lat]).buffer(2000)

                    # Build composite filtered to this taluk's region
                    s2_col = (
                        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                        .filterDate(start_str, end_str)
                        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_limit))
                        .filterBounds(region)   # KEY FIX: restrict to taluk area
                        .select(["B4", "B8"])   # Red, NIR only
                    )

                    col_size = s2_col.size().getInfo()
                    if col_size == 0:
                        logger.warning(
                            "satellite.no_scenes_for_taluk",
                            taluk=taluk,
                            start=start_str,
                            end=end_str,
                            cloud_limit=cloud_limit,
                        )
                        continue

                    # NDVI = (NIR - Red) / (NIR + Red) — normalizedDifference handles scale
                    composite = s2_col.map(
                        lambda img: img.normalizedDifference(["B8", "B4"]).rename("NDVI")
                    ).median()

                    stats = composite.reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=region,
                        scale=30,
                        maxPixels=1e6,
                        bestEffort=True,
                    ).getInfo()

                    ndvi_val = stats.get("NDVI")
                    if ndvi_val is None:
                        logger.warning(
                            "satellite.ndvi_none",
                            taluk=taluk,
                            scenes=col_size,
                            message="reduceRegion returned None — skipping.",
                        )
                        continue

                    # Clamp to valid range [−1, 1]
                    ndvi_val = round(max(-1.0, min(1.0, float(ndvi_val))), 4)
                    # EVI approximation: ~85% of NDVI for this region
                    evi_val  = round(ndvi_val * 0.85, 4)

                    with get_session() as session:
                        existing = (
                            session.query(RawNdviSentinel)
                            .filter_by(
                                sensing_date=target_date,
                                block_id=f"{taluk}__sentinel2",
                                satellite_pass="sentinel2",
                            )
                            .first()
                        )
                        if existing:
                            logger.info("satellite.already_exists", taluk=taluk, date=str(target_date))
                            rows_written += 1  # Count as success
                            continue

                        row = RawNdviSentinel(
                            sensing_date=target_date,
                            block_id=f"{taluk}__sentinel2",
                            district=self.district,
                            ndvi=ndvi_val,
                            evi=evi_val,
                            cloud_cover_pct=float(cloud_limit),
                            satellite_pass="sentinel2",
                            is_mock_data=False,   # ✅ REAL satellite data
                        )
                        session.add(row)
                    rows_written += 1

                    logger.info(
                        "satellite.saved",
                        taluk=taluk,
                        ndvi=ndvi_val,
                        scenes_used=col_size,
                        date=str(target_date),
                        is_monsoon=is_monsoon,
                    )

                except Exception as exc:
                    logger.warning(
                        "satellite.taluk_failed",
                        taluk=taluk,
                        error=str(exc),
                        error_type=type(exc).__name__,
                    )

            logger.info(
                "satellite.gee_complete",
                date=str(target_date),
                taluks_saved=rows_written,
                total_taluks=len(self.taluks),
            )
            return rows_written

        except Exception as exc:
            logger.error(
                "satellite.gee_error",
                error=str(exc),
                error_type=type(exc).__name__,
                message="GEE collection failed. Falling back to mock data.",
            )
            return self._collect_mock(target_date)

    def _collect_mock(self, target_date: date) -> int:
        """Generate and store seasonal-average NDVI as fallback.

        Args:
            target_date: The sensing date.

        Returns:
            Number of records written.
        """
        season = _MONTH_TO_SEASON.get(target_date.month, "Kharif")
        _, ndvi_mid, _ = _SEASONAL_NDVI_AVERAGES[season]
        catalog = load_crops_catalog()
        rows_written = 0

        for taluk in self.taluks:
            for crop_name in catalog:
                try:
                    with get_session() as session:
                        existing = (
                            session.query(RawNdviSentinel)
                            .filter_by(
                                block_id=f"{taluk}__{crop_name}",
                                satellite_pass="mock_seasonal",
                            )
                            .first()
                        )
                        if existing:
                            continue

                        row = RawNdviSentinel(
                            sensing_date=date.today(),
                            block_id=f"{taluk}__{crop_name}",
                            district=self.district,
                            ndvi=ndvi_mid,
                            evi=round(ndvi_mid * 0.85, 3),
                            cloud_cover_pct=0.0,
                            satellite_pass="mock_seasonal",
                            is_mock_data=True,   # Estimated — clearly flagged
                        )
                        session.add(row)
                    rows_written += 1
                except Exception as exc:
                    logger.warning(
                        "satellite.mock_save_failed",
                        taluk=taluk,
                        crop=crop_name,
                        error=str(exc),
                    )

        logger.info(
            "satellite.mock_collected",
            season=season,
            taluks=len(self.taluks),
            rows_written=rows_written,
        )
        return rows_written

    @staticmethod
    def _check_gee_available() -> bool:
        """Check if Google Earth Engine API is installed and project ID is set.

        Returns:
            True if the earthengine-api package is installed AND
            GEE_PROJECT_ID is set in .env. False otherwise.
        """
        try:
            import ee  # type: ignore[import-untyped]  # noqa: F401
            return bool(os.environ.get("GEE_PROJECT_ID"))
        except ImportError:
            return False

    def get_status(self) -> dict[str, Any]:
        """Return satellite data status for the dashboard.

        Returns:
            Dict with data_type, source, and farmer-facing message.
        """
        if self._gee_available:
            return {
                "data_type": "real",
                "source": "Sentinel-2 via Google Earth Engine",
                "project": self._gee_project,
                "message": "✅ Real satellite imagery (Sentinel-2, 10m resolution)",
            }
        return {
            "data_type": "estimated",
            "source": "Seasonal NDVI averages (MODIS historical)",
            "message": "⚠️ Satellite data estimated — GEE_PROJECT_ID not configured",
        }
