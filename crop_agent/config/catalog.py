"""Crop and district catalog loader.

Loads the all-India crop catalog and district reference data from seed CSV files.
These CSV files are committed to Git (whitelisted in .gitignore) because they
are reference/seed data — not collected raw data.

The catalog is loaded once at import time and cached. All other modules should
import from here rather than reading the CSV directly.

Seed file locations:
    data/seeds/crops_catalog.csv      — All India crops (100+ crops)
    data/seeds/districts_karnataka.csv — Karnataka district/taluk reference
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

from crop_agent.config.logging_config import get_logger

logger = get_logger(__name__)

# Path to seed data — resolved relative to the project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SEEDS_DIR: Path = _PROJECT_ROOT / "data" / "seeds"
CROPS_CATALOG_PATH: Path = SEEDS_DIR / "crops_catalog.csv"
DISTRICTS_CATALOG_PATH: Path = SEEDS_DIR / "districts_karnataka.csv"


@dataclass
class CropInfo:
    """Complete metadata for a single crop from the all-India catalog.

    Attributes:
        crop_name: Official crop name (e.g. "Paddy (Rice)").
        crop_category: Top-level category (Cereal, Pulse, Vegetable, Fruit, etc.).
        crop_sub_category: Sub-category within the group.
        seasons_possible: List of seasons this crop can be grown in.
        duration_days_min: Minimum days from sowing to harvest.
        duration_days_max: Maximum days from sowing to harvest.
        yield_unit: Unit for yield measurement (quintal, kg, tonne, nut).
        price_unit: Unit for price measurement.
        gdd_base_temp_c: Base temperature (°C) for Growing Degree Days calculation.
        volatility_class: Price volatility level — LOW | MEDIUM | HIGH.
        is_perishable: True if crop needs cold storage / sells quickly.
        major_states: List of primary producing states across India.
        yield_min_per_acre: Minimum observed yield per acre.
        yield_max_per_acre: Maximum observed yield per acre.
        price_min_inr_per_unit: Minimum observed price in INR per unit.
        price_max_inr_per_unit: Maximum observed price in INR per unit.
    """

    crop_name: str
    crop_category: str
    crop_sub_category: str
    seasons_possible: list[str]
    duration_days_min: int
    duration_days_max: int
    yield_unit: str
    price_unit: str
    gdd_base_temp_c: float
    volatility_class: str
    is_perishable: bool
    major_states: list[str]
    yield_min_per_acre: float
    yield_max_per_acre: float
    price_min_inr_per_unit: float
    price_max_inr_per_unit: float


@dataclass
class DistrictInfo:
    """Reference data for a district/taluk location.

    Attributes:
        district_name: District name.
        taluk: Taluk name within the district.
        state: State name.
        latitude: Latitude in decimal degrees.
        longitude: Longitude in decimal degrees.
        elevation_m: Elevation above sea level in metres.
        soil_type_primary: Primary soil classification.
        major_crops: List of major crops grown in this area.
        agro_climatic_zone: Agro-climatic zone classification.
    """

    district_name: str
    taluk: str
    state: str
    latitude: float
    longitude: float
    elevation_m: float
    soil_type_primary: str
    major_crops: list[str]
    agro_climatic_zone: str


@lru_cache(maxsize=1)
def load_crops_catalog() -> dict[str, CropInfo]:
    """Load the all-India crop catalog from the seed CSV.

    Results are cached after the first call — O(1) for all subsequent accesses.

    Returns:
        Dictionary mapping crop_name → CropInfo for all 100+ crops.

    Raises:
        FileNotFoundError: If the crop catalog CSV is missing.
        ValueError: If the CSV has malformed rows.
    """
    if not CROPS_CATALOG_PATH.exists():
        raise FileNotFoundError(
            f"Crop catalog not found at: {CROPS_CATALOG_PATH}. "
            "Ensure data/seeds/crops_catalog.csv is present and committed to Git."
        )

    catalog: dict[str, CropInfo] = {}

    with CROPS_CATALOG_PATH.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row_num, row in enumerate(reader, start=2):  # start=2 because row 1 is header
            try:
                info = CropInfo(
                    crop_name=row["crop_name"].strip(),
                    crop_category=row["crop_category"].strip(),
                    crop_sub_category=row["crop_sub_category"].strip(),
                    seasons_possible=[s.strip() for s in row["seasons_possible"].split("|")],
                    duration_days_min=int(row["duration_days_min"]),
                    duration_days_max=int(row["duration_days_max"]),
                    yield_unit=row["yield_unit"].strip(),
                    price_unit=row["price_unit"].strip(),
                    gdd_base_temp_c=float(row["gdd_base_temp_c"]),
                    volatility_class=row["volatility_class"].strip(),
                    is_perishable=row["is_perishable"].strip().lower() == "true",
                    major_states=[s.strip() for s in row["major_states"].split(",")],
                    yield_min_per_acre=float(row["yield_min_per_acre"]),
                    yield_max_per_acre=float(row["yield_max_per_acre"]),
                    price_min_inr_per_unit=float(row["price_min_inr_per_unit"]),
                    price_max_inr_per_unit=float(row["price_max_inr_per_unit"]),
                )
                catalog[info.crop_name] = info
            except (KeyError, ValueError) as exc:
                logger.warning(
                    "catalog.crops.malformed_row",
                    row_num=row_num,
                    error=str(exc),
                    row=dict(row),
                )

    logger.info("catalog.crops.loaded", total_crops=len(catalog))
    return catalog


@lru_cache(maxsize=1)
def load_districts_catalog() -> list[DistrictInfo]:
    """Load the Karnataka district/taluk reference data from the seed CSV.

    Returns:
        List of DistrictInfo objects for all Karnataka districts/taluks.

    Raises:
        FileNotFoundError: If the districts catalog CSV is missing.
    """
    if not DISTRICTS_CATALOG_PATH.exists():
        raise FileNotFoundError(
            f"Districts catalog not found at: {DISTRICTS_CATALOG_PATH}. "
            "Ensure data/seeds/districts_karnataka.csv is present."
        )

    districts: list[DistrictInfo] = []

    with DISTRICTS_CATALOG_PATH.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row_num, row in enumerate(reader, start=2):
            try:
                info = DistrictInfo(
                    district_name=row["district_name"].strip(),
                    taluk=row["taluk"].strip(),
                    state=row["state"].strip(),
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    elevation_m=float(row["elevation_m"]),
                    soil_type_primary=row["soil_type_primary"].strip(),
                    major_crops=[c.strip() for c in row["major_crops"].split(",")],
                    agro_climatic_zone=row["agro_climatic_zone"].strip(),
                )
                districts.append(info)
            except (KeyError, ValueError) as exc:
                logger.warning(
                    "catalog.districts.malformed_row",
                    row_num=row_num,
                    error=str(exc),
                )

    logger.info("catalog.districts.loaded", total_entries=len(districts))
    return districts


def get_crop_names() -> list[str]:
    """Get sorted list of all crop names in the catalog.

    Returns:
        Alphabetically sorted list of all crop names.
    """
    return sorted(load_crops_catalog().keys())


def get_crops_by_category(category: str) -> list[CropInfo]:
    """Get all crops in a given category.

    Args:
        category: Category name (e.g. "Vegetable", "Fruit", "Cereal").

    Returns:
        List of CropInfo objects matching the category.
    """
    return [
        crop for crop in load_crops_catalog().values()
        if crop.crop_category.lower() == category.lower()
    ]


def get_crops_by_state(state: str) -> list[CropInfo]:
    """Get all crops grown primarily in a given state.

    Args:
        state: State name (e.g. "Karnataka", "Punjab").

    Returns:
        List of CropInfo for crops where the state is a major producer.
    """
    return [
        crop for crop in load_crops_catalog().values()
        if any(state.lower() in s.lower() for s in crop.major_states)
    ]


def get_crop_validity_ranges() -> dict[str, dict[str, float]]:
    """Build the per-crop validity range dict from the catalog.

    Used by anti_hallucination.py to validate model predictions.
    If a crop is not in the catalog, its predictions cannot be validated.

    Returns:
        Dict mapping crop_name → {yield_min, yield_max, price_min, price_max}.
    """
    return {
        name: {
            "yield_min": info.yield_min_per_acre,
            "yield_max": info.yield_max_per_acre,
            "price_min": info.price_min_inr_per_unit,
            "price_max": info.price_max_inr_per_unit,
        }
        for name, info in load_crops_catalog().items()
    }


def get_high_volatility_crops() -> list[str]:
    """Get list of crops classified as HIGH volatility.

    High-volatility crops must show P10/P50/P90 distribution on the
    dashboard — not just the average prediction.

    Returns:
        List of crop names with volatility_class == "HIGH".
    """
    return [
        name
        for name, info in load_crops_catalog().items()
        if info.volatility_class == "HIGH"
    ]


def get_mandya_crops() -> list[str]:
    """Get crop names that are grown in Mandya district specifically.

    Returns:
        List of crop names relevant for Mandya district.
    """
    mandya_entries = [
        d for d in load_districts_catalog()
        if d.district_name == "Mandya"
    ]
    all_mandya_crops: set[str] = set()
    for entry in mandya_entries:
        all_mandya_crops.update(entry.major_crops)
    return sorted(all_mandya_crops)
