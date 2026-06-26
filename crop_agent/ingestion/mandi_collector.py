"""Mandi price data collector — Layer 1 Ingestion.

Collects daily mandi prices from Agmarknet via the data.gov.in open API.
Registration is free at https://data.gov.in/user/register

Cross-verification rule (per spec Section 5.2):
  Prices from Agmarknet are cross-checked against Karnataka APMC data weekly.
  If prices differ by more than CROSS_SOURCE_PRICE_TOLERANCE_PCT (15%),
  the row is flagged in anomaly_log and not used in feature engineering.

Fallback strategy:
  - If Agmarknet API is unavailable → retry 3 times
  - After all retries fail → log to anomaly_log, use previous day's prices
    for dashboard display (with stale data warning shown to farmer)

NOTE: If your API key is not configured yet (AGMARKNET_API_KEY is empty),
the collector will log a clear warning and skip — no silent failure.
"""

import datetime
from datetime import date
from typing import Any

from crop_agent.config.logging_config import get_logger
from crop_agent.config.settings import (
    AGMARKNET_API_KEY,
    AGMARKNET_BASE_URL,
    CROSS_SOURCE_PRICE_TOLERANCE_PCT,
    DEFAULT_DISTRICT,
    DEFAULT_STATE,
)
from crop_agent.database.connection import get_session
from crop_agent.database.models import AnomalyLog, RawMandiPrice
from crop_agent.ingestion.base_collector import BaseCollector

logger = get_logger(__name__)

# Mandya district mandis — official names as registered in Agmarknet
MANDYA_MANDIS: list[str] = [
    "Mandya",
    "Maddur",
    "Malavalli",
    "Nagamangala",
    "Pandavapura",
    "K.R.Pet",
]

# Agmarknet market state code for Karnataka
AGMARKNET_STATE_CODE: str = "Karnataka"


class MandiCollector(BaseCollector):
    """Collects daily mandi prices from Agmarknet (data.gov.in) API.

    Prices are collected per crop × mandi × date combination.
    If the API key is not set, the collector logs a clear warning and returns 0
    without crashing — the night agent continues with other tasks.

    Attributes
    ----------
        district: District to collect prices for.
        state: State name for API filtering.
        mandis: List of mandi names to collect from.

    """

    def __init__(
        self,
        district: str = DEFAULT_DISTRICT,
        state: str = DEFAULT_STATE,
        mandis: list[str] | None = None,
    ) -> None:
        """Initialize the mandi price collector.

        Args:
        ----
            district: District name for DB tagging and API filtering.
            state: State name for API filtering.
            mandis: List of mandi names to collect. Defaults to Mandya mandis.

        """
        super().__init__(source_name="agmarknet")
        self.district = district
        self.state = state
        self.mandis = mandis or MANDYA_MANDIS

    def collect(self, target_date: date) -> int:
        """Collect mandi prices for all configured mandis for the given date.

        Args:
        ----
            target_date: Date to collect prices for.

        Returns:
        -------
            Number of price rows written to the database.

        """
        if not AGMARKNET_API_KEY:
            logger.warning(
                "mandi.api_key_missing",
                message=(
                    "AGMARKNET_API_KEY is not set in .env. "
                    "Register at https://data.gov.in/user/register to get a free API key. "
                    "Skipping mandi price collection for today."
                ),
            )
            return 0

        date_str = target_date.strftime("%d/%m/%Y")
        rows_written = 0

        try:
            params = {
                "api-key": AGMARKNET_API_KEY,
                "format": "json",
                "filters[State.keyword]": self.state,
                "filters[District.keyword]": self.district,
                "filters[Arrival_Date]": date_str,
                "limit": 500,  # Max records per request
                "offset": 0,
            }

            response = self._get(AGMARKNET_BASE_URL, params=params)
            records = response.get("records", [])

            if not records:
                logger.info(
                    "mandi.no_records",
                    date=date_str,
                    district=self.district,
                )
                return 0

            for record in records:
                rows_written += self._save_price_row(record, target_date)

            logger.info(
                "mandi.collected",
                date=date_str,
                district=self.district,
                records=len(records),
                rows_written=rows_written,
            )

        except Exception as exc:
            logger.error(
                "mandi.collect_failed",
                date=date_str,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise  # Re-raise so base class retry logic handles it

        return rows_written

    def _save_price_row(self, record: dict[str, Any], target_date: date) -> int:
        """Parse a single Agmarknet API record and save to database.

        Args:
        ----
            record: Raw API record dict from Agmarknet response.
            target_date: The date this record belongs to.

        Returns:
        -------
            1 if saved, 0 if duplicate or failed.

        """
        try:
            crop = record.get("Commodity", "").strip()
            mandi = record.get("Market", "").strip()
            modal_price = record.get("Modal_Price")
            min_price = record.get("Min_Price")
            max_price = record.get("Max_Price")
            arrivals = record.get("Arrivals_in_Qtl")

            if not crop or not mandi or modal_price is None:
                return 0

            modal_price_f = float(str(modal_price).replace(",", ""))
            min_price_f = float(str(min_price).replace(",", "")) if min_price else None
            max_price_f = float(str(max_price).replace(",", "")) if max_price else None
            arrivals_f = float(str(arrivals).replace(",", "")) if arrivals else None

            with get_session() as session:
                # Check for duplicate before inserting
                existing = (
                    session.query(RawMandiPrice)
                    .filter_by(
                        date=datetime.datetime.combine(target_date, datetime.time()),
                        crop=crop,
                        mandi_name=mandi,
                        source_id="agmarknet",
                    )
                    .first()
                )
                if existing:
                    return 0

                row = RawMandiPrice(
                    date=datetime.datetime.combine(target_date, datetime.time()),
                    crop=crop,
                    mandi_name=mandi,
                    district=self.district,
                    state=self.state,
                    price_inr_per_qtl=modal_price_f,
                    arrivals_qtl=arrivals_f,
                    min_price_inr=min_price_f,
                    max_price_inr=max_price_f,
                    modal_price_inr=modal_price_f,
                    source_id="agmarknet",
                )
                session.add(row)

            return 1

        except (ValueError, TypeError, KeyError) as exc:
            logger.warning(
                "mandi.parse_failed",
                record=str(record)[:200],
                error=str(exc),
            )
            return 0

    def cross_verify_with_apmc(
        self,
        crop: str,
        mandi: str,
        agmarknet_price: float,
        apmc_price: float,
        target_date: date,
    ) -> bool:
        """Cross-check Agmarknet price against Karnataka APMC data.

        Per spec Section 5.2: If prices differ by more than
        CROSS_SOURCE_PRICE_TOLERANCE_PCT (15%), flag in anomaly_log
        and return False — the price is not used in feature engineering.

        Args:
        ----
            crop: Crop name.
            mandi: Mandi name.
            agmarknet_price: Price from Agmarknet in INR/qtl.
            apmc_price: Price from Karnataka APMC in INR/qtl.
            target_date: Date of the price data.

        Returns:
        -------
            True if prices agree within tolerance, False if flagged.

        """
        if agmarknet_price <= 0 or apmc_price <= 0:
            return True  # Skip check if either price is zero/invalid

        max_price = max(agmarknet_price, apmc_price)
        diff_pct = abs(agmarknet_price - apmc_price) / max_price * 100.0

        if diff_pct <= CROSS_SOURCE_PRICE_TOLERANCE_PCT:
            return True

        detail = (
            f"Mandi price cross-verify FAILED on {target_date} "
            f"for {crop} at {mandi}: "
            f"Agmarknet=₹{agmarknet_price:.0f}/qtl, "
            f"APMC=₹{apmc_price:.0f}/qtl, "
            f"Diff={diff_pct:.1f}% (threshold={CROSS_SOURCE_PRICE_TOLERANCE_PCT}%)"
        )
        logger.warning("mandi.cross_verify_failed", detail=detail)

        try:
            with get_session() as session:
                anomaly = AnomalyLog(
                    table_name="raw_mandi_prices",
                    column_name="price_inr_per_qtl",
                    issue_type="cross_source_mismatch",
                    issue_detail=detail,
                    source_a_value=str(agmarknet_price),
                    source_b_value=str(apmc_price),
                    severity="MEDIUM",
                )
                session.add(anomaly)
        except Exception as exc:
            logger.error("mandi.anomaly_log_failed", error=str(exc))

        return False
