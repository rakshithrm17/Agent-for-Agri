"""Soil data collector — Layer 1 Ingestion.

Collects soil property data from SoilGrids (ISRIC) REST API.
SoilGrids is completely free, requires no API key, and provides
global soil data at 250m resolution.

API: https://rest.soilgrids.org/soilgrids/v2.0/properties/query
Properties collected: pH, organic carbon %, clay %, sand %, silt %
Depths: 0-5cm, 5-15cm, 15-30cm

Soil data is STATIC — collected once per taluk and stored permanently.
The collect() method checks if data already exists before making API calls.
"""

from datetime import date

from crop_agent.config.logging_config import get_logger
from crop_agent.config.settings import (
    DEFAULT_DISTRICT,
    MANDYA_TALUKS,
    SOILGRIDS_BASE_URL,
    SOILGRIDS_DEPTHS,
    SOILGRIDS_PROPERTIES,
)
from crop_agent.database.connection import get_session
from crop_agent.database.models import RawSoilProperties
from crop_agent.ingestion.base_collector import BaseCollector

logger = get_logger(__name__)

# Taluk coordinates for Mandya district (lat, lon, elevation_m)
_MANDYA_TALUK_COORDS: dict[str, tuple[float, float, float]] = {
    "Mandya":             (12.5234, 76.8961, 680.0),
    "Maddur":             (12.5807, 77.0466, 705.0),
    "Malavalli":          (12.3847, 77.0607, 720.0),
    "Nagamangala":        (12.8156, 76.7497, 770.0),
    "Pandavapura":        (12.4872, 76.6839, 660.0),
    "Shrirangapattana":   (12.4165, 76.6951, 650.0),
    "Krishnarajapete":    (12.6585, 76.3887, 820.0),
}

# Primary soil type per taluk — from NBSS&LUP Mandya district report
_MANDYA_SOIL_TYPES: dict[str, str] = {
    "Mandya":           "Red Sandy Loam",
    "Maddur":           "Red Sandy Loam",
    "Malavalli":        "Red Laterite",
    "Nagamangala":      "Black Cotton Soil",
    "Pandavapura":      "Red Sandy Loam",
    "Shrirangapattana": "Alluvial",
    "Krishnarajapete":  "Red Laterite",
}


class SoilCollector(BaseCollector):
    """Collects soil property data from SoilGrids REST API per taluk.

    Data is collected once per taluk and treated as permanent reference.
    If a taluk already has soil data in the database, it is skipped.

    Attributes:
        district: District name for DB tagging.
        taluks: List of taluks to collect soil data for.
    """

    def __init__(
        self,
        district: str = DEFAULT_DISTRICT,
        taluks: list[str] | None = None,
    ) -> None:
        """Initialize the soil collector.

        Args:
            district: District name (used for DB tagging).
            taluks: List of taluks to collect. Defaults to all Mandya taluks.
        """
        super().__init__(source_name="soilgrids")
        self.district = district
        self.taluks = taluks or MANDYA_TALUKS

    def collect(self, target_date: date) -> int:
        """Collect soil data for all taluks that don't have data yet.

        The target_date parameter is accepted for interface compatibility
        but soil data is not date-specific — it is collected once per taluk.

        Args:
            target_date: Date of collection (stored as collected_date).

        Returns:
            Number of new taluk records written.
        """
        rows_written = 0

        for taluk in self.taluks:
            if taluk not in _MANDYA_TALUK_COORDS:
                logger.warning("soil.unknown_taluk", taluk=taluk, district=self.district)
                continue

            # Skip if already collected (soil data is static)
            if self._already_collected(taluk):
                logger.debug("soil.already_exists", taluk=taluk)
                continue

            lat, lon, _ = _MANDYA_TALUK_COORDS[taluk]
            soil_data = self._fetch_soilgrids(lat, lon, taluk)

            if soil_data:
                rows_written += self._save_soil_row(taluk, soil_data, target_date)

        return rows_written

    def _already_collected(self, taluk: str) -> bool:
        """Check if soil data for this taluk already exists in the database.

        Args:
            taluk: Taluk name to check.

        Returns:
            True if data exists, False if we need to collect.
        """
        try:
            with get_session() as session:
                existing = (
                    session.query(RawSoilProperties)
                    .filter_by(taluk=taluk, district=self.district, source_id="soilgrids")
                    .first()
                )
                return existing is not None
        except Exception as exc:
            logger.warning("soil.check_failed", taluk=taluk, error=str(exc))
            return False

    def _fetch_soilgrids(
        self, lat: float, lon: float, taluk: str
    ) -> dict[str, float | None] | None:
        """Fetch soil properties from SoilGrids REST API for a coordinate.

        SoilGrids returns values as mean ± uncertainty at multiple depths.
        We take the 0-5cm surface layer as the primary value, and average
        down to 30cm depth as the secondary value for deeper-rooted crops.

        Args:
            lat: Latitude in decimal degrees.
            lon: Longitude in decimal degrees.
            taluk: Taluk name (for logging only).

        Returns:
            Dict of soil property values, or None if fetch failed.
        """
        params = {
            "lon": lon,
            "lat": lat,
            "property": SOILGRIDS_PROPERTIES,
            "depth": SOILGRIDS_DEPTHS,
            "value": "mean",
        }

        try:
            response = self._get(SOILGRIDS_BASE_URL, params=params)
            properties = response.get("properties", {}).get("layers", [])

            if not properties:
                logger.warning(
                    "soil.no_data_from_soilgrids",
                    taluk=taluk,
                    lat=lat,
                    lon=lon,
                )
                return None

            # Parse response — SoilGrids returns a list of layers
            result: dict[str, float | None] = {}
            for layer in properties:
                prop_name = layer.get("name", "")
                depths_data = layer.get("depths", [])

                # Take the 0-5cm surface value
                surface_val: float | None = None
                for depth_entry in depths_data:
                    if depth_entry.get("label") == "0-5cm":
                        values = depth_entry.get("values", {})
                        mean = values.get("mean")
                        if mean is not None:
                            surface_val = float(mean)
                        break

                # Map SoilGrids property names to our column names
                # SoilGrids returns values in natural units × 10 for some
                if prop_name == "phh2o" and surface_val is not None:
                    result["ph"] = surface_val / 10.0   # SoilGrids pH is × 10
                elif prop_name == "soc" and surface_val is not None:
                    result["organic_carbon_pct"] = surface_val / 10.0  # × 10 in SoilGrids
                elif prop_name == "clay":
                    result["clay_pct"] = surface_val / 10.0 if surface_val is not None else None
                elif prop_name == "sand":
                    result["sand_pct"] = surface_val / 10.0 if surface_val is not None else None
                elif prop_name == "silt":
                    result["silt_pct"] = surface_val / 10.0 if surface_val is not None else None

            logger.info(
                "soil.fetched",
                taluk=taluk,
                lat=lat,
                lon=lon,
                properties_found=list(result.keys()),
            )
            return result

        except Exception as exc:
            logger.warning(
                "soil.fetch_failed",
                taluk=taluk,
                lat=lat,
                lon=lon,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return None

    def _save_soil_row(
        self,
        taluk: str,
        soil_data: dict[str, float | None],
        collected_date: date,
    ) -> int:
        """Persist a soil property row to the database.

        Args:
            taluk: Taluk name.
            soil_data: Dict of soil property values from SoilGrids.
            collected_date: Date when data was collected.

        Returns:
            1 if written successfully, 0 if failed.
        """
        try:
            with get_session() as session:
                row = RawSoilProperties(
                    taluk=taluk,
                    district=self.district,
                    soil_type=_MANDYA_SOIL_TYPES.get(taluk),
                    ph=soil_data.get("ph"),
                    organic_carbon_pct=soil_data.get("organic_carbon_pct"),
                    clay_pct=soil_data.get("clay_pct"),
                    sand_pct=soil_data.get("sand_pct"),
                    silt_pct=soil_data.get("silt_pct"),
                    source_id="soilgrids",
                    collected_date=collected_date,
                )
                session.add(row)

            logger.info(
                "soil.saved",
                taluk=taluk,
                district=self.district,
                ph=soil_data.get("ph"),
                organic_carbon=soil_data.get("organic_carbon_pct"),
            )
            return 1

        except Exception as exc:
            logger.error(
                "soil.save_failed",
                taluk=taluk,
                error=str(exc),
            )
            return 0

    def collect_all_taluks(self, target_date: date | None = None) -> int:
        """Collect soil data for all configured taluks.

        Convenience method to seed the entire district at once.
        Safe to call multiple times — skips already-collected taluks.

        Args:
            target_date: Collection date. Defaults to today.

        Returns:
            Total rows written.
        """
        from datetime import date as date_type
        run_date = target_date or date_type.today()
        return self.run(run_date)
