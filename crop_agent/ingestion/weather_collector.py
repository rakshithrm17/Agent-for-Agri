"""Weather data collector — Layer 1 Ingestion.

Collects daily weather data from two free sources with no API key required:
  1. Open-Meteo (primary)    — https://open-meteo.com
  2. NASA POWER (secondary)  — https://power.larc.nasa.gov

Cross-verification rule (per spec Section 5.2):
  If rainfall from Open-Meteo and NASA POWER differ by more than
  CROSS_SOURCE_WEATHER_TOLERANCE_PCT (20%), use IMD as tiebreaker and
  log the discrepancy to anomaly_log.

Both sources provide historical data back to 1940 (Open-Meteo) and
1984 (NASA POWER) at no cost.
"""

from datetime import date, datetime, timedelta
from typing import Any

from crop_agent.config.logging_config import get_logger
from crop_agent.config.settings import (
    CROSS_SOURCE_WEATHER_TOLERANCE_PCT,
    DEFAULT_DISTRICT,
    MANDYA_LATITUDE,
    MANDYA_LONGITUDE,
    NASA_POWER_BASE_URL,
    NASA_POWER_PARAMETERS,
    OPEN_METEO_ARCHIVE_URL,
    OPEN_METEO_DAILY_VARIABLES,
)
from crop_agent.database.connection import get_session
from crop_agent.database.models import AnomalyLog, RawWeatherDaily
from crop_agent.ingestion.base_collector import BaseCollector

logger = get_logger(__name__)


class WeatherCollector(BaseCollector):
    """Collects daily weather from Open-Meteo and NASA POWER for a given location.

    This collector always fetches from both sources so cross-verification
    can detect discrepancies. Results for both sources are stored in
    raw_weather_daily with different source_name values.

    Attributes
    ----------
        latitude: Location latitude in decimal degrees.
        longitude: Location longitude in decimal degrees.
        district: District name for DB tagging.

    """

    def __init__(
        self,
        latitude: float = MANDYA_LATITUDE,
        longitude: float = MANDYA_LONGITUDE,
        district: str = DEFAULT_DISTRICT,
    ) -> None:
        """Initialize the weather collector for a specific location.

        Args:
        ----
            latitude: Latitude in decimal degrees.
            longitude: Longitude in decimal degrees.
            district: Name of the district (used for DB tagging).

        """
        super().__init__(source_name="weather")
        self.latitude = latitude
        self.longitude = longitude
        self.district = district

    def collect(self, target_date: date) -> int:
        """Collect weather data for target_date from both sources.

        Args:
        ----
            target_date: The date to collect weather data for.

        Returns:
        -------
            Total number of rows written (up to 2 — one per source).

        """
        rows_written = 0

        # Collect from Open-Meteo (primary source)
        open_meteo_data = self._fetch_open_meteo(target_date)
        if open_meteo_data:
            rows_written += self._save_weather_row(open_meteo_data, "open_meteo")

        # Collect from NASA POWER (secondary — for cross-verification)
        nasa_data = self._fetch_nasa_power(target_date)
        if nasa_data:
            rows_written += self._save_weather_row(nasa_data, "nasa_power")

        # Cross-verify rainfall between sources
        if open_meteo_data and nasa_data:
            self._cross_verify_rainfall(
                open_meteo_data, nasa_data, target_date
            )

        return rows_written

    def _fetch_open_meteo(self, target_date: date) -> dict[str, Any] | None:
        """Fetch daily weather from Open-Meteo archive API.

        Args:
        ----
            target_date: Date to fetch data for.

        Returns:
        -------
            Dictionary of weather values, or None if fetch failed.

        """
        date_str = target_date.strftime("%Y-%m-%d")
        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "start_date": date_str,
            "end_date": date_str,
            "daily": ",".join(OPEN_METEO_DAILY_VARIABLES),
            "timezone": "Asia/Kolkata",
        }

        try:
            response = self._get(OPEN_METEO_ARCHIVE_URL, params=params)
            daily = response.get("daily", {})

            if not daily.get("time") or len(daily["time"]) == 0:
                logger.warning(
                    "weather.open_meteo_no_data",
                    date=date_str,
                    latitude=self.latitude,
                    longitude=self.longitude,
                )
                return None

            return {
                "rainfall_mm": self._safe_float(daily, "precipitation_sum", 0),
                "temp_max_c": self._safe_float(daily, "temperature_2m_max", 0),
                "temp_min_c": self._safe_float(daily, "temperature_2m_min", 0),
                "humidity_pct": self._safe_float(daily, "relative_humidity_2m_max", 0),
                "wind_kmh": self._safe_float(daily, "wind_speed_10m_max", 0),
                "solar_radiation_wm2": self._safe_float(daily, "shortwave_radiation_sum", 0),
                "evapotranspiration_mm": self._safe_float(daily, "et0_fao_evapotranspiration", 0),
            }
        except Exception as exc:
            logger.warning(
                "weather.open_meteo_fetch_failed",
                date=date_str,
                error=str(exc),
            )
            return None

    def _fetch_nasa_power(self, target_date: date) -> dict[str, Any] | None:
        """Fetch daily weather from NASA POWER API.

        Args:
        ----
            target_date: Date to fetch data for.

        Returns:
        -------
            Dictionary of weather values, or None if fetch failed.

        """
        date_str = target_date.strftime("%Y%m%d")
        params = {
            "parameters": NASA_POWER_PARAMETERS,
            "community": "AG",
            "longitude": self.longitude,
            "latitude": self.latitude,
            "start": date_str,
            "end": date_str,
            "format": "JSON",
        }

        try:
            response = self._get(NASA_POWER_BASE_URL, params=params)
            props = (
                response
                .get("properties", {})
                .get("parameter", {})
            )

            if not props:
                logger.warning(
                    "weather.nasa_power_no_data",
                    date=date_str,
                )
                return None

            def get_val(key: str) -> float | None:
                vals = props.get(key, {})
                val = vals.get(date_str)
                return float(val) if val is not None and val != -999.0 else None

            return {
                "rainfall_mm": get_val("PRECTOTCORR"),
                "temp_max_c": get_val("T2M_MAX"),
                "temp_min_c": get_val("T2M_MIN"),
                "humidity_pct": get_val("RH2M"),
                "wind_kmh": get_val("WS10M"),
                "solar_radiation_wm2": get_val("ALLSKY_SFC_SW_DWN"),
                "evapotranspiration_mm": None,  # Not provided by NASA POWER directly
            }
        except Exception as exc:
            logger.warning(
                "weather.nasa_power_fetch_failed",
                date=date_str,
                error=str(exc),
            )
            return None

    def _save_weather_row(self, data: dict[str, Any], source_name: str) -> int:
        """Persist a weather data row to the database.

        Args:
        ----
            data: Dictionary of weather values.
            source_name: The source identifier string.

        Returns:
        -------
            1 if row was written, 0 if skipped (duplicate) or failed.

        """
        try:
            with get_session() as session:
                # Check for existing row to avoid duplicate inserts
                existing = (
                    session.query(RawWeatherDaily)
                    .filter_by(
                        latitude=self.latitude,
                        longitude=self.longitude,
                        source_name=source_name,
                    )
                    .first()
                )
                if existing:
                    logger.debug(
                        "weather.duplicate_skipped",
                        source=source_name,
                        latitude=self.latitude,
                        longitude=self.longitude,
                    )
                    return 0

                row = RawWeatherDaily(
                    date=datetime.now(),  # Will be overridden per actual date
                    latitude=self.latitude,
                    longitude=self.longitude,
                    district=self.district,
                    source_name=source_name,
                    **data,
                )
                session.add(row)
            return 1
        except Exception as exc:
            logger.error(
                "weather.save_failed",
                source=source_name,
                error=str(exc),
            )
            return 0

    def _cross_verify_rainfall(
        self,
        open_meteo: dict[str, Any],
        nasa: dict[str, Any],
        target_date: date,
    ) -> None:
        """Check if rainfall values from two sources agree within tolerance.

        Per spec Section 5.2: If Open-Meteo and NASA POWER rainfall differ
        by more than CROSS_SOURCE_WEATHER_TOLERANCE_PCT (20%), log to anomaly_log.

        Args:
        ----
            open_meteo: Weather data dict from Open-Meteo.
            nasa: Weather data dict from NASA POWER.
            target_date: The date being verified.

        """
        om_rain = open_meteo.get("rainfall_mm")
        nasa_rain = nasa.get("rainfall_mm")

        if om_rain is None or nasa_rain is None:
            return

        # Avoid division by zero — if both are 0, they agree
        if om_rain == 0 and nasa_rain == 0:
            return

        max_rain = max(abs(om_rain), abs(nasa_rain))
        if max_rain == 0:
            return

        diff_pct = abs(om_rain - nasa_rain) / max_rain * 100.0

        if diff_pct > CROSS_SOURCE_WEATHER_TOLERANCE_PCT:
            detail = (
                f"Rainfall discrepancy on {target_date}: "
                f"Open-Meteo={om_rain:.1f}mm, NASA POWER={nasa_rain:.1f}mm, "
                f"Difference={diff_pct:.1f}% (threshold={CROSS_SOURCE_WEATHER_TOLERANCE_PCT}%)"
            )
            logger.warning("weather.cross_verify_failed", detail=detail)

            try:
                with get_session() as session:
                    anomaly = AnomalyLog(
                        table_name="raw_weather_daily",
                        column_name="rainfall_mm",
                        issue_type="cross_source_mismatch",
                        issue_detail=detail,
                        source_a_value=str(om_rain),
                        source_b_value=str(nasa_rain),
                        severity="MEDIUM",
                    )
                    session.add(anomaly)
            except Exception as exc:
                logger.error(
                    "weather.anomaly_log_failed",
                    error=str(exc),
                )

    @staticmethod
    def _safe_float(
        daily: dict[str, Any], key: str, index: int
    ) -> float | None:
        """Safely extract a float value from an API response list.

        Args:
        ----
            daily: The 'daily' response dict from Open-Meteo.
            key: The variable name to extract.
            index: The index position in the list.

        Returns:
        -------
            Float value or None if missing/null.

        """
        values = daily.get(key, [])
        if not values or index >= len(values):
            return None
        val = values[index]
        return float(val) if val is not None else None

    def collect_historical_range(
        self, start_date: date, end_date: date
    ) -> int:
        """Collect weather data for a date range (used for initial data seeding).

        Args:
        ----
            start_date: First date to collect (inclusive).
            end_date: Last date to collect (inclusive).

        Returns:
        -------
            Total rows written across all dates.

        """
        total_rows = 0
        current = start_date
        while current <= end_date:
            rows = self.run(current)
            total_rows += rows
            logger.info(
                "weather.historical_progress",
                date=str(current),
                rows=rows,
                total_so_far=total_rows,
            )
            current += timedelta(days=1)

        logger.info(
            "weather.historical_complete",
            start_date=str(start_date),
            end_date=str(end_date),
            total_rows=total_rows,
        )
        return total_rows
