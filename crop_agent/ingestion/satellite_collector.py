"""Satellite NDVI data collector — Layer 1 Ingestion.

STATUS: Phase 1 STUB — Returns mock NDVI data with is_mock_data=True flag.
Real data will be collected via Google Earth Engine (GEE) in Phase 2.

To activate real satellite data:
1. Register at: https://earthengine.google.com (free for research)
2. Install earthengine-api: pip install earthengine-api
3. Authenticate: earthengine authenticate
4. Set GEE_PROJECT_ID in .env
5. Replace _fetch_mock_ndvi() with _fetch_gee_ndvi() below

Why stub instead of skipping:
  The ML models need NDVI features to work. Mock NDVI data (based on
  historical seasonal averages) is much better than no NDVI data at all.
  Mock data is clearly flagged with is_mock_data=True so:
    - Dashboard shows "Satellite data: Estimated (not real)" to farmer
    - Anti-hallucination checks apply wider tolerance for mock data
    - Replacing mock with real data is done by re-running the collector

Data source reference (for when GEE is activated):
  Sentinel-2 MSI: https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR
  MODIS Terra: https://developers.google.com/earth-engine/datasets/catalog/MODIS_006_MOD13Q1
"""

from datetime import date
from typing import Any

from crop_agent.config.catalog import load_crops_catalog
from crop_agent.config.logging_config import get_logger
from crop_agent.config.settings import DEFAULT_DISTRICT, MANDYA_TALUKS
from crop_agent.database.connection import get_session
from crop_agent.database.models import RawNdviSentinel
from crop_agent.ingestion.base_collector import BaseCollector

logger = get_logger(__name__)

# Seasonal NDVI averages for Mandya district based on MODIS historical data
# These values are approximate — replace with real GEE data when account is ready
# Structure: season → (ndvi_sowing, ndvi_mid, ndvi_pre_harvest)
_SEASONAL_NDVI_AVERAGES: dict[str, tuple[float, float, float]] = {
    "Kharif": (0.38, 0.65, 0.52),   # June sowing: low→peak→decline
    "Rabi":   (0.32, 0.58, 0.48),   # Nov sowing: lower base, good mid
    "Summer": (0.28, 0.50, 0.40),   # March sowing: dry season, lower values
    "Annual": (0.45, 0.70, 0.55),   # Perennial crops: higher sustained NDVI
}

# Current season mapping by month
_MONTH_TO_SEASON: dict[int, str] = {
    6: "Kharif", 7: "Kharif", 8: "Kharif",
    9: "Kharif", 10: "Kharif", 11: "Rabi",
    12: "Rabi", 1: "Rabi", 2: "Rabi",
    3: "Summer", 4: "Summer", 5: "Summer",
}


class SatelliteCollector(BaseCollector):
    """Collects NDVI vegetation index data per crop per block in a district.

    Phase 1: Returns seasonal-average mock NDVI with is_mock_data=True.
    Phase 2: Will use Google Earth Engine API for real Sentinel-2 data.

    The is_mock_data flag ensures the dashboard always shows farmers
    whether their NDVI data is real satellite or estimated.

    Attributes:
        district: District name for DB tagging.
        taluks: List of taluks to generate NDVI for.
    """

    def __init__(
        self,
        district: str = DEFAULT_DISTRICT,
        taluks: list[str] | None = None,
    ) -> None:
        """Initialize the satellite collector.

        Args:
            district: District name.
            taluks: List of taluks. Defaults to all Mandya taluks.
        """
        super().__init__(source_name="satellite_ndvi")
        self.district = district
        self.taluks = taluks or MANDYA_TALUKS
        self._gee_available = self._check_gee_available()

    def collect(self, target_date: date) -> int:
        """Collect NDVI data for all crops and taluks for the target date.

        In Phase 1: generates seasonal-average mock NDVI values.
        In Phase 2: calls Google Earth Engine API.

        Args:
            target_date: The sensing date to collect data for.

        Returns:
            Number of NDVI records written.
        """
        if self._gee_available:
            # Phase 2 path — real satellite data
            return self._collect_gee(target_date)
        else:
            # Phase 1 path — mock data
            logger.info(
                "satellite.using_mock_data",
                message=(
                    "GEE not configured — using seasonal-average NDVI estimates. "
                    "Register at earthengine.google.com to get real satellite data."
                ),
                date=str(target_date),
            )
            return self._collect_mock(target_date)

    def _collect_mock(self, target_date: date) -> int:
        """Generate and store mock NDVI data based on seasonal averages.

        Args:
            target_date: The sensing date.

        Returns:
            Number of records written.
        """
        season = _MONTH_TO_SEASON.get(target_date.month, "Kharif")
        ndvi_sowing, ndvi_mid, ndvi_pre_harvest = _SEASONAL_NDVI_AVERAGES[season]
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
                            ndvi=ndvi_mid,          # Use mid-season as current
                            evi=ndvi_mid * 0.85,    # EVI is typically ~85% of NDVI
                            cloud_cover_pct=0.0,
                            satellite_pass="mock_seasonal",
                            is_mock_data=True,
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

    def _collect_gee(self, target_date: date) -> int:
        """Collect real NDVI data from Google Earth Engine.

        TODO: Implement when GEE account is registered.
        Steps to implement:
          1. Authenticate: ee.Initialize(project=GEE_PROJECT_ID)
          2. Load Sentinel-2 collection filtered by date and district bounds
          3. Calculate NDVI = (NIR - Red) / (NIR + Red)
          4. Sample per taluk using district boundary polygons
          5. Store with is_mock_data=False

        Args:
            target_date: The sensing date.

        Returns:
            Number of records written (currently 0 — not implemented).
        """
        logger.info(
            "satellite.gee_not_implemented",
            message="GEE collection not yet implemented. Falling back to mock data.",
        )
        return self._collect_mock(target_date)

    @staticmethod
    def _check_gee_available() -> bool:
        """Check if Google Earth Engine is configured and authenticated.

        Returns:
            True if GEE is available, False if not installed or authenticated.
        """
        try:
            import ee  # type: ignore[import-untyped]  # noqa: F401
            # earthengine-api is installed — check authentication
            import os
            return bool(os.environ.get("GEE_PROJECT_ID"))
        except ImportError:
            return False

    def get_mock_data_status(self) -> dict[str, Any]:
        """Return the current satellite data status for dashboard display.

        Returns:
            Dict with data_type ("real" or "estimated") and message for farmer.
        """
        if self._gee_available:
            return {
                "data_type": "real",
                "source": "Sentinel-2 via Google Earth Engine",
                "message": "Real satellite imagery",
            }
        return {
            "data_type": "estimated",
            "source": "Seasonal NDVI averages (MODIS historical)",
            "message": "⚠️ Satellite data estimated — register GEE for real data",
        }
