import os
import sys
import sqlite3
import time
import requests
from datetime import date, datetime, timedelta
from pathlib import Path

# Add project root to python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

DB_PATH = PROJECT_ROOT / "crop_agent.db"
AGMARKNET_API_KEY = os.getenv("AGMARKNET_API_KEY", "")
AGMARKNET_URL = "https://api.data.gov.in/resource/35985678-0d79-46b4-9ed6-6f13308a1d24"

# Import taluks mapping
from crop_agent.config.settings import DISTRICT_TALUKS_MAP, TALUK_TO_DISTRICT

# Coordinates dictionary from dashboard for all 50 taluks
TALUK_COORDS = {
    "Mandya":(12.5234,76.8961),"Maddur":(12.5807,77.0466),"Malavalli":(12.3847,77.0607),
    "Nagamangala":(12.8156,76.7497),"Pandavapura":(12.4872,76.6839),
    "Shrirangapattana":(12.4165,76.6951),"Krishnarajapete":(12.6585,76.3887),
    "Mysuru":(12.2958,76.6394),"Hunsur":(12.3046,76.2928),"Nanjangud":(12.1139,76.6828),
    "T. Narasipura":(12.2135,76.9162),"Periyapatna":(12.3318,76.0507),"H.D. Kote":(12.0447,76.0025),
    "Chamarajanagar":(11.9238,76.9434),"Gundlupet":(11.8085,76.6914),
    "Kollegal":(12.1578,77.1085),"Yelandur":(11.9862,77.0373),
    "Ramanagara":(12.7157,77.2804),"Channapatna":(12.6509,77.2068),
    "Kanakapura":(12.5460,77.4183),"Magadi":(12.9572,77.2268),
    "Devanahalli":(13.2456,77.7120),"Doddaballapura":(13.2951,77.5378),
    "Hosakote":(13.0701,77.7980),"Nelamangala":(13.1006,77.3919),
    "Kolar":(13.1360,78.1294),"Malur":(13.0023,77.9387),"Mulbagal":(13.1630,78.3960),
    "Srinivaspur":(13.3350,78.2107),"Bangarpet":(12.9860,78.1796),
    "Chikkaballapura":(13.4354,77.7268),"Bagepalli":(13.7862,77.7877),
    "Chintamani":(13.3986,78.0534),"Gouribidanur":(13.6131,77.5203),
    "Gudibanda":(13.9088,77.8397),"Sidlaghatta":(13.3893,77.8649),
    "Tumkuru":(13.3379,77.1173),"Tiptur":(13.2601,76.4757),"Turuvekere":(13.1642,76.6629),
    "Madhugiri":(13.6647,77.2097),"Gubbi":(13.3097,76.9418),"Sira":(13.7426,76.9051),
    "Pavagada":(14.0994,77.2797),"Kunigal":(13.0234,77.0248),
    "Hassan":(13.0036,76.1003),"Arsikere":(13.3143,76.2508),
    "Channarayapatna":(12.9035,76.3873),"Holenarasipur":(12.7854,76.2394),"Belur":(13.1651,75.8665),
}

def update_weather():
    print("\n🌦️  INCREMENTAL WEATHER UPDATE  🌦️")
    print("=================================")
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Ensure raw_weather table exists
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
    conn.commit()

    ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
    VARIABLES = [
        "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
        "relative_humidity_2m_max", "wind_speed_10m_max",
        "shortwave_radiation_sum", "et0_fao_evapotranspiration"
    ]

    yesterday = date.today() - timedelta(days=2) # Archive has a 2-day delay typically
    total_added = 0

    for taluk, (lat, lon) in TALUK_COORDS.items():
        cur.execute("SELECT max(date) FROM raw_weather WHERE taluk = ? AND source = 'open_meteo'", (taluk,))
        res = cur.fetchone()
        
        start_date = None
        if res and res[0]:
            try:
                start_date = datetime.strptime(res[0], "%Y-%m-%d").date() + timedelta(days=1)
            except ValueError:
                pass
        
        if not start_date:
            start_date = date.today() - timedelta(days=30) # Default to last 30 days
            
        if start_date > yesterday:
            print(f"  🟢 {taluk} weather is up to date (last date: {res[0]})")
            continue

        print(f"  🔄 Fetching weather for {taluk} ({start_date} to {yesterday})...")
        
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date.isoformat(),
            "end_date": yesterday.isoformat(),
            "daily": ",".join(VARIABLES),
            "timezone": "Asia/Kolkata",
        }

        try:
            resp = requests.get(ARCHIVE_URL, params=params, timeout=30)
            if resp.status_code != 200:
                print(f"    ⚠️ Failed to fetch weather: HTTP {resp.status_code}")
                continue
                
            daily = resp.json().get("daily", {})
            times = daily.get("time", [])
            if not times:
                print(f"    ⚠️ No weather data returned in range")
                continue
                
            district = TALUK_TO_DISTRICT.get(taluk, "Mandya")
            added_for_taluk = 0
            
            for i, d in enumerate(times):
                def get_val(key):
                    vals = daily.get(key, [])
                    val = vals[i] if i < len(vals) else None
                    return float(val) if val is not None else None
                
                cur.execute("""
                    INSERT OR IGNORE INTO raw_weather
                    (date, taluk, district, latitude, longitude, source,
                     rainfall_mm, temp_max_c, temp_min_c, humidity_pct, wind_kmh, solar_radiation, et0_mm)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    d, taluk, district, lat, lon, "open_meteo",
                    get_val("precipitation_sum"),
                    get_val("temperature_2m_max"),
                    get_val("temperature_2m_min"),
                    get_val("relative_humidity_2m_max"),
                    get_val("wind_speed_10m_max"),
                    get_val("shortwave_radiation_sum"),
                    get_val("et0_fao_evapotranspiration")
                ))
                if cur.rowcount > 0:
                    added_for_taluk += 1
            
            conn.commit()
            total_added += added_for_taluk
            print(f"    ✅ Added {added_for_taluk} days of weather data.")
            time.sleep(1.0) # Be friendly to open-meteo API
            
        except Exception as e:
            print(f"    ❌ Error: {e}")
            
    conn.close()
    print(f"Total weather records added: {total_added}")

def update_prices():
    if not AGMARKNET_API_KEY:
        print("\n⚠️  AGMARKNET_API_KEY not set — skipping incremental price collection")
        return
        
    print("\n💰  INCREMENTAL MANDI PRICE UPDATE  💰")
    print("=====================================")
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Ensure raw_prices table exists
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
    conn.commit()
    
    cur.execute("SELECT max(date) FROM raw_prices")
    res = cur.fetchone()
    
    start_date = None
    if res and res[0]:
        try:
            start_date = datetime.strptime(res[0].split("T")[0], "%Y-%m-%d").date() + timedelta(days=1)
        except ValueError:
            pass
            
    if not start_date:
        start_date = date.today() - timedelta(days=15) # Default to last 15 days
        
    end_date = date.today()
    if start_date > end_date:
        print("  🟢 Mandi prices are up to date.")
        conn.close()
        return
        
    print(f"  🔄 Fetching mandi prices from {start_date} to {end_date}...")
    
    current = start_date
    total_added = 0
    
    while current <= end_date:
        date_str = current.strftime("%d/%m/%Y")
        try:
            offset = 0
            page_added = 0
            while True:
                params = {
                    "api-key": AGMARKNET_API_KEY,
                    "format": "json",
                    "filters[State.keyword]": "Karnataka",
                    "filters[Arrival_Date]": date_str,
                    "limit": 100,
                    "offset": offset,
                }
                
                resp = requests.get(AGMARKNET_URL, params=params, timeout=25)
                if resp.status_code != 200:
                    break
                    
                data = resp.json()
                records = data.get("records", [])
                if not records:
                    break
                    
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
                        if cur.rowcount > 0:
                            page_added += 1
                    except (ValueError, TypeError):
                        pass
                
                conn.commit()
                if len(records) < 100:
                    break
                offset += 100
                time.sleep(0.5)
                
            total_added += page_added
            if page_added > 0:
                print(f"    ✅ {current.isoformat()}: Added {page_added} price records.")
                
        except Exception as e:
            print(f"    ❌ Error on {current.isoformat()}: {e}")
            
        current += timedelta(days=1)
        time.sleep(0.5)
        
    conn.close()
    print(f"Total mandi price records added: {total_added}")

if __name__ == "__main__":
    update_weather()
    update_prices()
    print("\n✨ Daily update complete! ✨")
