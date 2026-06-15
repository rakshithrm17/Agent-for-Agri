"""
Master Data Collection Script
==============================
Collects ALL available free data for the Crop Intelligence Agent.

Data collected:
  1. Agmarknet mandi prices      - all Karnataka, all crops, 2010-2025
  2. Open-Meteo weather          - Malavalli + all Mandya taluks, 2010-2025
  3. NASA POWER weather          - cross-verification source
  4. ICRISAT crop area/yield     - district level, 2001-2023 (via data.gov.in)
  5. Karnataka crop area stats   - season wise, district wise
  6. SoilGrids                   - soil properties per taluk
  7. News/RSS alerts             - current alerts

Run this script ONCE to seed the database with all historical data.
Progress is saved — safe to stop and restart.

Usage:
    python scripts/collect_all_data.py
    python scripts/collect_all_data.py --source weather
    python scripts/collect_all_data.py --source prices
    python scripts/collect_all_data.py --source area
"""

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import os
import sqlite3

# ─── Config ───────────────────────────────────────────────────────────────────
DB_PATH = PROJECT_ROOT / "crop_agent.db"
DATA_DIR = PROJECT_ROOT / "data" / "raw_downloads"
DATA_DIR.mkdir(parents=True, exist_ok=True)

AGMARKNET_API_KEY = os.getenv("AGMARKNET_API_KEY", "")
AGMARKNET_URL = "https://api.data.gov.in/resource/35985678-0d79-46b4-9ed6-6f13308a1d24"

# All Mandya taluks with coordinates
MANDYA_TALUKS = {
    "Malavalli":          (12.3847, 77.0607),
    "Mandya":             (12.5234, 76.8961),
    "Maddur":             (12.5807, 77.0466),
    "Nagamangala":        (12.8156, 76.7497),
    "Pandavapura":        (12.4872, 76.6839),
    "Shrirangapattana":   (12.4165, 76.6951),
    "Krishnarajapete":    (12.6585, 76.3887),
}

# Karnataka districts for broader area data
KARNATAKA_DISTRICTS = [
    "Mandya", "Mysuru", "Hassan", "Tumakuru", "Bengaluru Rural",
    "Shivamogga", "Davangere", "Belagavi", "Dharwad", "Haveri",
    "Vijayapura", "Kalaburagi", "Raichur", "Ballari", "Koppal",
    "Chitradurga", "Chikkamagaluru", "Kodagu", "Dakshina Kannada",
    "Udupi", "Uttara Kannada", "Gadag", "Bagalkote", "Bidar",
    "Yadgir", "Ramanagara", "Chamarajanagar", "Kolar", "Chikkaballapur"
]

# ─── Database Setup ────────────────────────────────────────────────────────────
def init_database():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Raw mandi prices
    cur.execute("""
        CREATE TABLE IF NOT EXISTS raw_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            state TEXT,
            district TEXT,
            market TEXT,
            commodity TEXT,
            variety TEXT,
            min_price REAL,
            max_price REAL,
            modal_price REAL,
            arrivals_qty REAL,
            source TEXT DEFAULT 'agmarknet',
            collected_at TEXT DEFAULT (datetime('now')),
            UNIQUE(date, market, commodity, variety)
        )
    """)

    # Weather data
    cur.execute("""
        CREATE TABLE IF NOT EXISTS raw_weather (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            taluk TEXT NOT NULL,
            district TEXT DEFAULT 'Mandya',
            latitude REAL,
            longitude REAL,
            source TEXT NOT NULL,
            rainfall_mm REAL,
            temp_max_c REAL,
            temp_min_c REAL,
            humidity_pct REAL,
            wind_kmh REAL,
            solar_radiation REAL,
            et0_mm REAL,
            collected_at TEXT DEFAULT (datetime('now')),
            UNIQUE(date, taluk, source)
        )
    """)

    # Crop area planted (hectares) per crop per district per year-season
    cur.execute("""
        CREATE TABLE IF NOT EXISTS raw_crop_area (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER NOT NULL,
            season TEXT,
            state TEXT,
            district TEXT,
            crop TEXT NOT NULL,
            area_ha REAL,
            production_tonnes REAL,
            yield_kg_per_ha REAL,
            source TEXT,
            collected_at TEXT DEFAULT (datetime('now')),
            UNIQUE(year, season, district, crop, source)
        )
    """)

    # Progress tracker so we can resume
    cur.execute("""
        CREATE TABLE IF NOT EXISTS collection_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT NOT NULL UNIQUE,
            status TEXT DEFAULT 'pending',
            last_date TEXT,
            rows_collected INTEGER DEFAULT 0,
            started_at TEXT,
            completed_at TEXT,
            notes TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Database initialized:", DB_PATH)


def get_progress(task: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT status, last_date, rows_collected FROM collection_progress WHERE task=?", (task,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"status": row[0], "last_date": row[1], "rows_collected": row[2]}
    return {"status": "not_started", "last_date": None, "rows_collected": 0}


def update_progress(task: str, status: str, last_date: str = None, rows: int = 0, notes: str = None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO collection_progress (task, status, last_date, rows_collected, started_at, notes)
        VALUES (?, ?, ?, ?, datetime('now'), ?)
        ON CONFLICT(task) DO UPDATE SET
            status=excluded.status,
            last_date=excluded.last_date,
            rows_collected=collection_progress.rows_collected + excluded.rows_collected,
            completed_at=CASE WHEN excluded.status='done' THEN datetime('now') ELSE NULL END,
            notes=excluded.notes
    """, (task, status, last_date, rows, notes))
    conn.commit()
    conn.close()


# ─── 1. AGMARKNET PRICE COLLECTION ────────────────────────────────────────────
def collect_prices(start_year: int = 2010, end_year: int = 2025):
    """Collect ALL Karnataka mandi prices from Agmarknet API."""

    if not AGMARKNET_API_KEY:
        print("⚠️  AGMARKNET_API_KEY not set — skipping price collection")
        return

    task = "agmarknet_prices_karnataka"
    progress = get_progress(task)

    if progress["status"] == "done":
        print(f"✅ Prices already collected ({progress['rows_collected']} rows) — skipping")
        return

    print(f"\n{'='*60}")
    print("📊 COLLECTING MANDI PRICES — Karnataka (2010-2025)")
    print(f"{'='*60}")

    conn = sqlite3.connect(DB_PATH)
    total_rows = progress.get("rows_collected", 0)
    update_progress(task, "running")

    # Collect month by month
    current = date(start_year, 1, 1)
    end = date(end_year, 12, 31)

    # Resume from last collected date if exists
    if progress["last_date"]:
        try:
            current = datetime.strptime(progress["last_date"], "%Y-%m-%d").date() + timedelta(days=1)
            print(f"Resuming from {current}")
        except ValueError:
            pass

    while current <= end:
        date_str = current.strftime("%d/%m/%Y")
        month_label = current.strftime("%b %Y")

        try:
            offset = 0
            page_rows = 0

            while True:
                params = {
                    "api-key": AGMARKNET_API_KEY,
                    "format": "json",
                    "filters[State.keyword]": "Karnataka",
                    "filters[Arrival_Date]": date_str,
                    "limit": 100,
                    "offset": offset,
                }

                resp = requests.get(AGMARKNET_URL, params=params, timeout=20)
                if resp.status_code != 200:
                    break

                data = resp.json()
                records = data.get("records", [])

                if not records:
                    break

                # Insert into DB
                cur = conn.cursor()
                for rec in records:
                    try:
                        modal_price = str(rec.get("Modal_Price", "0")).replace(",", "")
                        min_price = str(rec.get("Min_Price", "0")).replace(",", "")
                        max_price = str(rec.get("Max_Price", "0")).replace(",", "")
                        arrivals = str(rec.get("Arrivals_in_Qtl", "0")).replace(",", "")

                        cur.execute("""
                            INSERT OR IGNORE INTO raw_prices
                            (date, state, district, market, commodity, variety, min_price, max_price, modal_price, arrivals_qty)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            current.isoformat(),
                            rec.get("State", "Karnataka"),
                            rec.get("District", ""),
                            rec.get("Market", ""),
                            rec.get("Commodity", ""),
                            rec.get("Variety", ""),
                            float(min_price) if min_price else None,
                            float(max_price) if max_price else None,
                            float(modal_price) if modal_price else None,
                            float(arrivals) if arrivals else None,
                        ))
                        page_rows += 1
                    except (ValueError, TypeError):
                        pass

                conn.commit()
                total_rows += page_rows

                if len(records) < 100:
                    break
                offset += 100
                time.sleep(0.2)

            update_progress(task, "running", current.isoformat(), page_rows)

            if page_rows > 0:
                print(f"  {month_label}: {page_rows} price records | Total: {total_rows:,}")

        except Exception as e:
            print(f"  ⚠️  Error on {date_str}: {e}")

        current += timedelta(days=1)
        time.sleep(0.1)  # Be respectful to the API

    conn.close()
    update_progress(task, "done", end.isoformat(), 0, f"Total: {total_rows}")
    print(f"\n✅ Price collection complete: {total_rows:,} records")


# ─── 2. WEATHER COLLECTION ────────────────────────────────────────────────────
def collect_weather(start_year: int = 2005, end_year: int = 2025):
    """Collect historical weather for all Mandya taluks from Open-Meteo."""

    print(f"\n{'='*60}")
    print("🌦️  COLLECTING WEATHER DATA — All Mandya Taluks (2005-2025)")
    print(f"{'='*60}")

    ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
    VARIABLES = [
        "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
        "relative_humidity_2m_max", "wind_speed_10m_max",
        "shortwave_radiation_sum", "et0_fao_evapotranspiration"
    ]

    conn = sqlite3.connect(DB_PATH)
    total_rows = 0

    for taluk, (lat, lon) in MANDYA_TALUKS.items():
        task = f"weather_{taluk.lower().replace(' ', '_')}"
        progress = get_progress(task)

        if progress["status"] == "done":
            print(f"  ✅ {taluk}: already collected ({progress['rows_collected']} rows)")
            continue

        print(f"\n  📍 Collecting weather for {taluk} ({lat}, {lon})...")
        update_progress(task, "running")
        taluk_rows = 0

        # Collect year by year (Open-Meteo has limits per request)
        for year in range(start_year, end_year + 1):
            start_d = f"{year}-01-01"
            end_d = f"{year}-12-31" if year < end_year else date.today().strftime("%Y-%m-%d")

            try:
                params = {
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": start_d,
                    "end_date": end_d,
                    "daily": ",".join(VARIABLES),
                    "timezone": "Asia/Kolkata",
                }

                resp = requests.get(ARCHIVE_URL, params=params, timeout=30)
                if resp.status_code != 200:
                    print(f"    ⚠️  {year}: HTTP {resp.status_code}")
                    continue

                daily = resp.json().get("daily", {})
                dates = daily.get("time", [])

                if not dates:
                    continue

                cur = conn.cursor()
                year_rows = 0
                for i, d in enumerate(dates):
                    def safe(key):
                        vals = daily.get(key, [])
                        v = vals[i] if i < len(vals) else None
                        return float(v) if v is not None else None

                    try:
                        cur.execute("""
                            INSERT OR IGNORE INTO raw_weather
                            (date, taluk, latitude, longitude, source,
                             rainfall_mm, temp_max_c, temp_min_c,
                             humidity_pct, wind_kmh, solar_radiation, et0_mm)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            d, taluk, lat, lon, "open_meteo",
                            safe("precipitation_sum"),
                            safe("temperature_2m_max"),
                            safe("temperature_2m_min"),
                            safe("relative_humidity_2m_max"),
                            safe("wind_speed_10m_max"),
                            safe("shortwave_radiation_sum"),
                            safe("et0_fao_evapotranspiration"),
                        ))
                        year_rows += 1
                    except Exception:
                        pass

                conn.commit()
                taluk_rows += year_rows
                total_rows += year_rows
                update_progress(task, "running", f"{year}-12-31", year_rows)
                print(f"    {year}: {year_rows} days ✓")
                time.sleep(0.5)  # Respect Open-Meteo rate limits

            except Exception as e:
                print(f"    ⚠️  {year} error: {e}")

        update_progress(task, "done", f"{end_year}-12-31", 0, f"{taluk_rows} rows")
        print(f"  ✅ {taluk}: {taluk_rows:,} daily records")

    conn.close()
    print(f"\n✅ Weather collection complete: {total_rows:,} total records")


# ─── 3. CROP AREA DATA COLLECTION ─────────────────────────────────────────────
def collect_crop_area():
    """
    Collect crop area (hectares planted) data from data.gov.in.
    This is the KEY dataset — shows how many hectares of each crop
    are planted each year across Karnataka districts.

    Primary API: ICRISAT district-level data via data.gov.in
    """

    print(f"\n{'='*60}")
    print("🌱 COLLECTING CROP AREA DATA — Karnataka Districts (2001-2023)")
    print(f"{'='*60}")

    if not AGMARKNET_API_KEY:
        print("⚠️  API key needed — skipping crop area collection")
        print("   Get key at: https://data.gov.in/user/register")
        return

    # data.gov.in ICRISAT district level area production datasets
    # These resource IDs are for Karnataka district-level crop data
    AREA_DATASETS = [
        {
            "name": "ICRISAT Karnataka District Crop Area",
            "resource_id": "9ef84268-d588-465a-a308-a864a43d0070",
            "description": "District-wise area under different crops - Karnataka"
        },
        {
            "name": "Horticulture Area Karnataka",
            "resource_id": "35be999b-0208-4354-b557-f6ca9a536a2c",
            "description": "Area under horticulture crops - Karnataka districts"
        },
    ]

    conn = sqlite3.connect(DB_PATH)
    total_rows = 0

    for dataset in AREA_DATASETS:
        task = f"area_{dataset['resource_id'][:8]}"
        progress = get_progress(task)

        if progress["status"] == "done":
            print(f"  ✅ {dataset['name']}: already collected")
            continue

        print(f"\n  📊 Fetching: {dataset['name']}")
        update_progress(task, "running")
        dataset_rows = 0

        try:
            url = f"https://api.data.gov.in/resource/{dataset['resource_id']}"
            offset = 0

            while True:
                params = {
                    "api-key": AGMARKNET_API_KEY,
                    "format": "json",
                    "limit": 1000,
                    "offset": offset,
                }

                resp = requests.get(url, params=params, timeout=30)
                print(f"    Status: {resp.status_code} | Offset: {offset}")

                if resp.status_code != 200:
                    print(f"    ⚠️  Error: {resp.text[:200]}")
                    break

                data = resp.json()
                records = data.get("records", [])
                total_available = int(data.get("total", 0))

                if not records:
                    break

                cur = conn.cursor()
                for rec in records:
                    try:
                        # Try various field name formats from different datasets
                        year = (rec.get("year") or rec.get("Year") or
                                rec.get("year_code") or "").replace("-", "").strip()
                        year = int(year[:4]) if year and year[:4].isdigit() else None

                        district = (rec.get("dist_name") or rec.get("District") or
                                    rec.get("district") or "").strip()

                        crop = (rec.get("crop") or rec.get("Crop") or
                                rec.get("crop_name") or "").strip()

                        area = rec.get("area") or rec.get("Area") or rec.get("area_1000_ha")
                        production = rec.get("production") or rec.get("Production")
                        yield_val = rec.get("yield") or rec.get("Yield")

                        season = (rec.get("season") or rec.get("Season") or "Annual").strip()

                        if year and crop:
                            area_ha = float(str(area).replace(",", "")) * 1000 if area else None
                            prod_t = float(str(production).replace(",", "")) * 1000 if production else None
                            yld = float(str(yield_val).replace(",", "")) if yield_val else None

                            cur.execute("""
                                INSERT OR IGNORE INTO raw_crop_area
                                (year, season, state, district, crop, area_ha, production_tonnes, yield_kg_per_ha, source)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                year, season, "Karnataka", district, crop,
                                area_ha, prod_t, yld, dataset["name"]
                            ))
                            dataset_rows += 1
                    except (ValueError, TypeError):
                        pass

                conn.commit()
                total_rows += dataset_rows
                print(f"    Fetched {offset + len(records)} / {total_available} records")

                if len(records) < 1000 or offset + len(records) >= total_available:
                    break
                offset += 1000
                time.sleep(0.3)

        except Exception as e:
            print(f"    ⚠️  Error: {e}")
            update_progress(task, "error", notes=str(e))
            continue

        update_progress(task, "done", notes=f"{dataset_rows} rows")
        print(f"  ✅ {dataset['name']}: {dataset_rows:,} records")

    conn.close()
    print(f"\n✅ Crop area collection: {total_rows:,} total records")


# ─── 4. SOIL DATA ──────────────────────────────────────────────────────────────
def collect_soil():
    """Collect soil properties from SoilGrids for all Mandya taluks."""

    print(f"\n{'='*60}")
    print("🌍 COLLECTING SOIL DATA — All Mandya Taluks")
    print(f"{'='*60}")

    SOILGRIDS_URL = "https://rest.soilgrids.org/soilgrids/v2.0/properties/query"
    PROPERTIES = ["phh2o", "soc", "clay", "sand", "silt", "bdod", "nitrogen"]
    DEPTHS = ["0-5cm", "5-15cm", "15-30cm"]

    results = []

    for taluk, (lat, lon) in MANDYA_TALUKS.items():
        print(f"  Fetching soil for {taluk}...", end=" ")
        try:
            params = {
                "lon": lon,
                "lat": lat,
                "property": PROPERTIES,
                "depth": DEPTHS,
                "value": "mean",
            }
            resp = requests.get(SOILGRIDS_URL, params=params, timeout=30)

            if resp.status_code == 200:
                data = resp.json()
                layers = data.get("properties", {}).get("layers", [])

                soil_row = {"taluk": taluk, "lat": lat, "lon": lon}
                for layer in layers:
                    prop = layer.get("name", "")
                    depths_data = layer.get("depths", [])
                    for depth_entry in depths_data:
                        if depth_entry.get("label") == "0-5cm":
                            val = depth_entry.get("values", {}).get("mean")
                            if val:
                                soil_row[f"{prop}_0_5cm"] = val
                results.append(soil_row)
                print("✅")
            else:
                print(f"⚠️  HTTP {resp.status_code}")

            time.sleep(1)

        except Exception as e:
            print(f"⚠️  Error: {e}")

    # Save to JSON file (soil is static, doesn't need DB table)
    soil_output = DATA_DIR / "soil_properties_mandya.json"
    with open(soil_output, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ Soil data saved: {soil_output}")
    for r in results:
        ph_raw = r.get("phh2o_0_5cm", "N/A")
        ph = round(ph_raw / 10, 1) if isinstance(ph_raw, (int, float)) else "N/A"
        print(f"   {r['taluk']}: pH={ph}")


# ─── 5. SUMMARY ────────────────────────────────────────────────────────────────
def show_summary():
    """Show what data has been collected so far."""

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print(f"\n{'='*60}")
    print("📊 DATA COLLECTION SUMMARY")
    print(f"{'='*60}")

    tables = [
        ("raw_prices",    "Mandi Prices"),
        ("raw_weather",   "Weather Records"),
        ("raw_crop_area", "Crop Area Records"),
    ]

    for table, label in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  {label:25s}: {count:>10,} rows")
        except Exception:
            print(f"  {label:25s}: table not found")

    # Prices breakdown
    try:
        cur.execute("SELECT COUNT(DISTINCT commodity) FROM raw_prices")
        crops = cur.fetchone()[0]
        cur.execute("SELECT MIN(date), MAX(date) FROM raw_prices")
        date_range = cur.fetchone()
        print(f"\n  Price data: {crops} unique crops | {date_range[0]} to {date_range[1]}")
    except Exception:
        pass

    # Top crops by price records
    try:
        cur.execute("""
            SELECT commodity, COUNT(*) as cnt
            FROM raw_prices
            GROUP BY commodity
            ORDER BY cnt DESC
            LIMIT 15
        """)
        rows = cur.fetchall()
        if rows:
            print("\n  Top crops by price records:")
            for crop, cnt in rows:
                print(f"    {crop:30s}: {cnt:,} records")
    except Exception:
        pass

    # Weather coverage
    try:
        cur.execute("SELECT taluk, COUNT(*), MIN(date), MAX(date) FROM raw_weather GROUP BY taluk")
        rows = cur.fetchall()
        if rows:
            print("\n  Weather coverage per taluk:")
            for taluk, cnt, min_d, max_d in rows:
                print(f"    {taluk:20s}: {cnt:,} days ({min_d} to {max_d})")
    except Exception:
        pass

    # Progress tracker
    cur.execute("SELECT task, status, rows_collected, completed_at FROM collection_progress")
    rows = cur.fetchall()
    if rows:
        print("\n  Collection progress:")
        for task, status, rows_col, completed in rows:
            icon = "✅" if status == "done" else ("🔄" if status == "running" else "⏳")
            print(f"    {icon} {task:40s}: {status} ({rows_col:,} rows)")

    conn.close()


# ─── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Collect all crop intelligence data")
    parser.add_argument("--source", choices=["all", "prices", "weather", "area", "soil", "summary"],
                        default="all", help="Which data source to collect")
    parser.add_argument("--start-year", type=int, default=2010, help="Start year for historical data")
    parser.add_argument("--end-year", type=int, default=2025, help="End year")
    args = parser.parse_args()

    init_database()

    if args.source in ("all", "summary"):
        show_summary()

    if args.source == "summary":
        return

    if args.source in ("all", "prices"):
        collect_prices(args.start_year, args.end_year)

    if args.source in ("all", "weather"):
        collect_weather(args.start_year, args.end_year)

    if args.source in ("all", "area"):
        collect_crop_area()

    if args.source in ("all", "soil"):
        collect_soil()

    if args.source == "all":
        show_summary()


if __name__ == "__main__":
    main()
