import requests
import sqlite3
import csv
import io
import zipfile
import os
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, as_completed
from core.logging_config import setup_logging

# --- CONFIGURATION ---
BASE_URL = "https://politicsandwar.com/data/cities/"

# --- PATH CONFIGURATION (FIXED) ---
# This automatically gets the folder where THIS script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Define paths relative to the script location
DB_PATH = os.path.join(SCRIPT_DIR, "city_builds.db")
LOG_PATH = os.path.join(SCRIPT_DIR, "scraper_errors.log")

# Logging configuration
setup_logging(process_name="cities_scraper", level=os.getenv("LOG_LEVEL", "INFO"))

# Use 16 workers, or default to CPU count if detection fails
MAX_WORKERS = os.cpu_count() or 16 

# Mapping
BUILDING_MAPPING = {
    'oil_power_plants': 'oilpower',
    'wind_power_plants': 'windpower',
    'coal_power_plants': 'coalpower',
    'nuclear_power_plants': 'nuclearpower',
    'coal_mines': 'coalmine',
    'oil_wells': 'oilwell',
    'uranium_mines': 'uramine',
    'barracks': 'barracks',
    'farms': 'farm',
    'police_stations': 'policestation',
    'hospitals': 'hospital',
    'recycling_centers': 'recyclingcenter',
    'subway': 'subway',
    'supermarkets': 'supermarket',
    'banks': 'bank',
    'shopping_malls': 'mall',
    'stadiums': 'stadium',
    'lead_mines': 'leadmine',
    'iron_mines': 'ironmine',
    'bauxite_mines': 'bauxitemine',
    'oil_refineries': 'gasrefinery',
    'aluminum_refineries': 'aluminumrefinery',
    'steel_mills': 'steelmill',
    'munitions_factories': 'munitionsfactory',
    'factories': 'factory',
    'hangars': 'airforcebase',
    'drydocks': 'drydock'
}

# Pre-compute ordered keys for consistent tuple generation
ORDERED_KEYS = list(BUILDING_MAPPING.values())

def get_zip_links():
    """Fetches all zip links from the main page."""
    try:
        r = requests.get(BASE_URL)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        links = []
        for a in soup.find_all('a', href=True):
            if a['href'].endswith('.csv.zip'):
                links.append(urljoin(BASE_URL, a['href']))
        return list(set(links))
    except Exception as e:
        print(f"Error getting links: {e}")
        logging.error(f"Error getting links: {e}")
        return []

def setup_database():
    """Sets up DB with WAL mode for fast sequential writes."""
    conn = sqlite3.connect(DB_PATH)
    
    # Performance Tunings for SQLite
    conn.execute("PRAGMA journal_mode=WAL;") 
    conn.execute("PRAGMA synchronous = NORMAL;") 
    conn.execute("PRAGMA cache_size = -64000;") # Use 64MB of RAM for cache
    
    c = conn.cursor()
    
    cols_def = ", ".join([f"{col} INTEGER DEFAULT 0" for col in ORDERED_KEYS])
    all_building_cols = ", ".join(ORDERED_KEYS)

    # Note: infrastructure is calculated, not read. Land is removed.
    schema = f"""
    CREATE TABLE IF NOT EXISTS builds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        infrastructure INTEGER, 
        {cols_def},
        CONSTRAINT unq_build UNIQUE ({all_building_cols})
    );
    """
    c.execute(schema)
    
    # Indices (Removed "land")
    indices = [
        "infrastructure", "barracks", 
        "factory", "airforcebase", "drydock"
    ]
    for idx in indices:
        c.execute(f"CREATE INDEX IF NOT EXISTS idx_{idx} ON builds ({idx});")
    
    conn.commit()
    return conn

def normalize_and_calculate(row):
    """
    Pure CPU function: takes a raw CSV dict, returns a tuple of values suitable for DB.
    Tuple Order: (Infrastructure, [Ordered Buildings])
    """
    # Land calculation removed entirely

    # 1. Buildings
    building_values = []
    total_buildings = 0
    
    for csv_key, db_key in BUILDING_MAPPING.items():
        try:
            val = int(float(row.get(csv_key, 0)))
            # Clamp negative values to 0 just in case
            if val < 0: val = 0
            building_values.append(val)
            total_buildings += val
        except:
            building_values.append(0)

    # 2. Calculate Infrastructure
    infrastructure = total_buildings * 50
    
    # Return tuple: (infra, *buildings) -- Land removed
    return (infrastructure, *building_values)

def process_url(url):
    """
    Worker Function: Downloads, Unzips, Normalizes.
    Returns a list of tuples to the main process.
    """
    results = []
    try:
        r = requests.get(url, timeout=30)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            filename = z.namelist()[0]
            with z.open(filename) as f:
                wrapper = io.TextIOWrapper(f, encoding='cp437', newline='')
                reader = csv.DictReader(wrapper)
                
                # We normalize immediately to save memory (tuples are smaller than dicts)
                for row in reader:
                    results.append(normalize_and_calculate(row))
    except Exception as e:
        # Return error info, but don't crash
        return (False, f"Error processing {url}: {e}")
        
    return (True, results)

def main():
    print(f"Database will be stored at: {DB_PATH}")
    
    # 1. Setup DB
    conn = setup_database()
    c = conn.cursor()
    
    # 2. Get Links
    print("Fetching links...")
    links = get_zip_links()
    if not links:
        print("No links found.")
        return

    # 3. Prepare SQL Query
    # Columns: infrastructure, + all buildings (Land removed)
    placeholders = ', '.join(['?'] * (1 + len(ORDERED_KEYS)))
    column_names = f"infrastructure, {', '.join(ORDERED_KEYS)}"
    insert_sql = f"INSERT OR IGNORE INTO builds ({column_names}) VALUES ({placeholders})"

    # 4. Start Parallel Processing
    print(f"Starting processing with {MAX_WORKERS} threads...")
    
    total_inserted = 0
    
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_url = {executor.submit(process_url, url): url for url in links}
        
        # Process as they complete
        for future in tqdm(as_completed(future_to_url), total=len(links)):
            success, payload = future.result()
            
            if success:
                # payload is the list of tuples
                if payload:
                    c.executemany(insert_sql, payload)
                    conn.commit() # Commit after every file to keep memory usage stable
                    total_inserted += len(payload) # Note: this counts attempted inserts, not unique
            else:
                print(payload) # Print error message to console
                logging.error(payload) # Log to file

    # 5. Cleanup
    print("Optimizing database (VACUUM)...")
    conn.execute("VACUUM;")
    
    c.execute("SELECT Count(*) FROM builds")
    final_count = c.fetchone()[0]
    
    print(f"Done! Processed records. Total Unique Calculated Builds in DB: {final_count}")
    conn.close()

if __name__ == "__main__":
    # Windows requires this guard for multiprocessing
    main()