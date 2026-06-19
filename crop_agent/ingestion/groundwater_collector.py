"""Groundwater data collector — Layer 1 Ingestion.

Collects historical groundwater levels from OpenCity (sourced from GoK Antharjala).
Maps spelling variations of districts/taluks to match application settings.
"""

import os
from datetime import date, datetime
import pandas as pd
import requests
from sqlalchemy import text

from crop_agent.config.logging_config import get_logger
from crop_agent.config.settings import DISTRICT_TALUKS_MAP, TALUK_TO_DISTRICT
from crop_agent.database.connection import get_session
from crop_agent.database.models import RawGroundwaterLevel
from crop_agent.ingestion.base_collector import BaseCollector

logger = get_logger(__name__)

CSV_URL = "https://data.opencity.in/dataset/0e211af6-21a2-43a3-88e0-8115c06e8f95/resource/cde2c8ff-7730-45ee-b29f-f17c642adf1e/download/85634e40-d372-436b-861e-46b062d41b2a.csv"
LOCAL_CACHE_PATH = "data/raw_downloads/groundwater_karnataka.csv"

# Spelling mapping from our config settings (keys) to CSV values (values)
DISTRICT_CSV_MAP = {
    "Mysuru": "Mysore",
    "Chamarajanagar": "Chamrajnagar",
    "Tumkuru": "Tumkur",
}

TALUK_CSV_MAP = {
    "Krishnarajapete": "Krishnarajpet",
    "Shrirangapattana": "Shrirangapattana",
    "Mysuru": "Mysore",
    "Chamarajanagar": "Chamrajnagar",
    "H.D. Kote": "Heggadadevankote",
    "T. Narasipura": "Thiramakudlu narasipur",
    "Tirumakudalu Narasipura": "Thiramakudlu narasipur",
    "Doddaballapura": "Doddaballapur",
    "Srinivaspur": "Srinivaspura",
    "Chikkaballapura": "Chikkaballapur",
    "Gouribidanur": "Gouribidnur",
    "Gudibanda": "Gudibande",
    "Tumkuru": "Tumkur",
    "Arsikere": "Arasikere",
    "Holenarasipur": "Holenarasipura",
}

class GroundwaterCollector(BaseCollector):
    """Collector for historical taluk groundwater level data."""

    def __init__(self) -> None:
        """Initialize the collector."""
        super().__init__(source_name="groundwater")

    def collect(self, target_date: date) -> int:
        """Dummy implementation of abstract collect method to satisfy BaseCollector.
        
        Args:
            target_date: Unused target date.
            
        Returns:
            0
        """
        return 0

    def download_and_ingest(self) -> int:
        """Download and ingest historical groundwater data.
        
        Returns:
            Number of rows written to the database.
        """
        # Ensure local raw_downloads directory exists
        os.makedirs(os.path.dirname(LOCAL_CACHE_PATH), exist_ok=True)
        
        if not os.path.exists(LOCAL_CACHE_PATH):
            logger.info("groundwater.downloading_csv", url=CSV_URL)
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(CSV_URL, headers=headers, timeout=30)
                resp.raise_for_status()
                with open(LOCAL_CACHE_PATH, "wb") as f:
                    f.write(resp.content)
                logger.info("groundwater.download_success", path=LOCAL_CACHE_PATH)
            except Exception as exc:
                logger.error("groundwater.download_failed", error=str(exc))
                self._record_anomaly(f"Failed to download groundwater CSV: {exc}", severity="HIGH")
                return 0

        # Read CSV
        try:
            df = pd.read_csv(LOCAL_CACHE_PATH, header=None)
        except Exception as exc:
            logger.error("groundwater.read_failed", error=str(exc))
            return 0

        # Parse data rows (row 0 contains headers)
        data_df = df.iloc[1:].copy()
        data_df.columns = [
            "sl_no", "district", "taluk",
            "2013", "2014", "2015", "2016", "2017", "2018", "2019", "2020", "2021", "2022"
        ]
        
        data_df["district"] = data_df["district"].astype(str).str.strip()
        data_df["taluk"] = data_df["taluk"].astype(str).str.strip()

        rows_inserted = 0

        # Iterate over all target South Karnataka districts and taluks
        with get_session() as session:
            for district_config_name, taluks in DISTRICT_TALUKS_MAP.items():
                # Find matching district in CSV (either matches config name directly, or maps to it)
                csv_district_name = DISTRICT_CSV_MAP.get(district_config_name, district_config_name)
                district_rows = data_df[data_df["district"].str.lower() == csv_district_name.lower()]
                
                if district_rows.empty:
                    logger.warning("groundwater.district_not_found_in_csv", district=csv_district_name)
                    continue

                for taluk_config_name in taluks:
                    # Find matching taluk in CSV
                    csv_taluk_name = TALUK_CSV_MAP.get(taluk_config_name, taluk_config_name)
                    taluk_row = district_rows[district_rows["taluk"].str.lower() == csv_taluk_name.lower()]
                    
                    if taluk_row.empty:
                        logger.warning(
                            "groundwater.taluk_not_found_in_csv",
                            district=csv_district_name,
                            taluk=csv_taluk_name
                        )
                        continue

                    # Insert yearly values (2013 to 2022)
                    for year in range(2013, 2023):
                        year_str = str(year)
                        val_raw = taluk_row[year_str].values[0]
                        
                        try:
                            val = float(val_raw) if pd.notna(val_raw) and str(val_raw).strip() != "" else None
                        except (ValueError, TypeError):
                            val = None

                        # Check if record already exists
                        existing = (
                            session.query(RawGroundwaterLevel)
                            .filter_by(
                                taluk=taluk_config_name,
                                district=district_config_name,
                                year=year
                            )
                            .first()
                        )
                        
                        if not existing:
                            record = RawGroundwaterLevel(
                                taluk=taluk_config_name,
                                district=district_config_name,
                                year=year,
                                depth_m=val
                            )
                            session.add(record)
                            rows_inserted += 1

            session.commit()
            
        logger.info("groundwater.ingest_complete", rows_inserted=rows_inserted)
        return rows_inserted
