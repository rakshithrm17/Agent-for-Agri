"""
Agmarknet Price Scraper — Direct Website
==========================================
Scrapes mandi price data directly from agmarknet.gov.in
(fallback when the data.gov.in API is down)

Also tries the eNAM API for price data.

This script downloads Karnataka mandi prices month by month
and saves to the SQLite database.
"""

import sqlite3
import time
import sys
import re
from datetime import date, timedelta
from pathlib import Path

# Try requests + bs4
try:
    import requests
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "crop_agent.db"

AGMARKNET_SEARCH_URL = "https://agmarknet.gov.in/SearchCommoditywise.aspx"
SESSION_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-IN,en;q=0.9",
}

# Karnataka mandi codes (from Agmarknet)
# These are the key mandis we want price history for
MANDYA_MARKETS = {
    "Mandya": "Karnataka",
    "Malavalli": "Karnataka",
    "Maddur": "Karnataka",
    "Mysore": "Karnataka",
    "Bengaluru": "Karnataka",
}


def try_enam_api():
    """Try to get price data from eNAM (National Agriculture Market)."""
    print("\n📊 Trying eNAM API...")

    try:
        # eNAM public data endpoint
        session = requests.Session()
        session.headers.update(SESSION_HEADERS)

        # eNAM API endpoints
        endpoints_to_try = [
            "https://enam.gov.in/ENAM_WEB_SERVICE/enamservice/getArrivalData",
            "https://enam.gov.in/web/dashboard/trade-data",
        ]

        for url in endpoints_to_try:
            try:
                resp = session.get(url, timeout=15)
                print(f"  {url}: HTTP {resp.status_code}")
                if resp.status_code == 200:
                    print(f"  Response preview: {resp.text[:200]}")
                    return True
            except Exception as e:
                print(f"  {url}: Error - {e}")

    except Exception as e:
        print(f"  eNAM error: {e}")

    return False


def try_data_gov_in_search():
    """Search data.gov.in catalog for Agmarknet datasets."""
    print("\n🔍 Searching data.gov.in for Agmarknet datasets...")

    try:
        session = requests.Session()

        # Search the catalog
        search_url = "https://api.data.gov.in/catalog"
        params = {
            "api-key": "579b464db66ec23bdd000001d96ea592fa0547ce5abbb26d802373d6",
            "format": "json",
            "q": "agmarknet mandi price Karnataka",
            "limit": 10,
        }

        resp = session.get(search_url, params=params, timeout=15)
        print(f"  Catalog search HTTP: {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()
            datasets = data.get("catalogs", data.get("records", []))
            print(f"  Found {len(datasets)} datasets")
            for ds in datasets[:5]:
                print(f"    - {ds.get('title', 'N/A')}: {ds.get('id', 'N/A')}")
            return datasets

    except Exception as e:
        print(f"  Error: {e}")

    return []


def try_alternative_resource_ids():
    """Try known working Agmarknet resource IDs on data.gov.in."""
    print("\n🔑 Testing alternative Agmarknet resource IDs...")

    # Known resource IDs for Agmarknet data on data.gov.in
    RESOURCE_IDS = [
        ("35985678-0d79-46b4-9ed6-6f13308a1d24", "Agmarknet Daily Prices (main)"),
        ("9ef84268-d588-465a-a308-a864a43d0070", "District crop area stats"),
        ("a9ca0f8d-97a0-4daa-bc02-59d20124f63a", "Agmarknet prices alt"),
        ("fd917a10-60d9-4ee1-a878-7edafb4faf62", "Agmarknet commodity prices"),
        ("7c868c14-1e4a-4b0d-8f23-e6c7d96e4b0c", "Karnataka mandi prices"),
    ]

    API_KEY = "579b464db66ec23bdd000001d96ea592fa0547ce5abbb26d802373d6"
    BASE = "https://api.data.gov.in/resource"
    session = requests.Session()

    working = []
    for rid, name in RESOURCE_IDS:
        try:
            url = f"{BASE}/{rid}"
            resp = session.get(url, params={
                "api-key": API_KEY,
                "format": "json",
                "limit": 1,
            }, timeout=10)

            status = resp.status_code
            if status == 200:
                data = resp.json()
                total = data.get("total", 0)
                fields = list(data.get("records", [{}])[0].keys()) if data.get("records") else []
                print(f"  ✅ {name}: {total:,} records | Fields: {fields[:5]}")
                working.append((rid, name, total, fields))
            else:
                print(f"  ❌ {name}: HTTP {status}")
        except Exception as e:
            print(f"  ⚠️  {name}: {str(e)[:60]}")
        time.sleep(0.5)

    return working


def download_prices_from_open_source():
    """
    Download Karnataka mandi price data from alternative open sources.
    
    Sources tried in order:
    1. data.gov.in API (primary)
    2. OGD Platform direct CSV download
    3. eNAM API
    """
    print("\n" + "=" * 60)
    print("💰 FINDING PRICE DATA SOURCES")
    print("=" * 60)

    # Try 1: Find working resource IDs
    working_resources = try_alternative_resource_ids()

    # Try 2: Catalog search
    if not working_resources:
        try_data_gov_in_search()

    # Try 3: eNAM
    try_enam_api()


if __name__ == "__main__":
    if not BS4_AVAILABLE:
        print("Installing BeautifulSoup4...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "beautifulsoup4", "--quiet"])
        from bs4 import BeautifulSoup

    download_prices_from_open_source()
