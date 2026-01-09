from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# --- Common DB paths ---

def get_nations_db_path() -> Path:
    """Return the absolute path to nations SQLite database."""
    return Path.cwd() / 'data' / 'nations.db'


def get_alliances_db_path() -> Path:
    """Return the absolute path to alliances SQLite database."""
    return Path.cwd() / 'data' / 'alliances.db'


def get_builds_db_path() -> Path:
    """Return the absolute path to the builds SQLite database."""
    return Path.cwd() / 'data' / 'city_builds.db'


# --- Dynamic schema + upsert for nations ---

def map_sqlite_type(value: Any) -> str:
    """Infer a reasonable SQLite column type from a Python value.

    Scalars map to INTEGER/REAL/TEXT; complex types are stored as TEXT (JSON).
    """
    if isinstance(value, bool):
        return "INTEGER"
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "REAL"
    if isinstance(value, (str, type(None))):
        return "TEXT"
    return "TEXT"


def ensure_table_and_columns(conn: sqlite3.Connection, table: str, sample_row: Dict[str, Any]) -> None:
    """Ensure the table exists and has columns for all keys in sample_row.

    - Creates table if missing, using 'id INTEGER PRIMARY KEY' when present.
    - Adds new columns on the fly when data gains fields.
    - Complex (dict/list) fields are stored as TEXT containing compact JSON.
    """
    cur = conn.cursor()
    # Create table if not exists
    columns_def = []
    if "id" in sample_row:
        columns_def.append("id INTEGER PRIMARY KEY")
    columns_def.append("_created_at INTEGER")
    cur.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(columns_def)})")

    # Discover existing columns
    cur.execute(f"PRAGMA table_info({table})")
    existing_cols = {row[1] for row in cur.fetchall()}

    # Add missing columns
    for key, val in sample_row.items():
        if key not in existing_cols:
            col_type = map_sqlite_type(val)
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {key} {col_type}")
            existing_cols.add(key)

    conn.commit()


def row_to_db_values(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a data row to DB-ready values.

    - Booleans become 0/1
    - dict/list become JSON strings
    - None/str/int/float left as-is
    """
    out: Dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, bool):
            out[k] = int(v)
        elif isinstance(v, (dict, list)):
            out[k] = json.dumps(v, separators=(",", ":"))
        else:
            out[k] = v
    out.setdefault("_created_at", round(datetime.utcnow().timestamp()))
    return out


def upsert(conn: sqlite3.Connection, table: str, row: Dict[str, Any]) -> None:
    """Insert or update a row by 'id' when present; otherwise inserts."""
    cur = conn.cursor()
    values = row_to_db_values(row)
    cols = list(values.keys())
    placeholders = ", ".join([":" + c for c in cols])
    col_list = ", ".join(cols)

    if "id" in values:
        update_assignments = ", ".join([f"{c}=excluded.{c}" for c in cols if c != "id"])
        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {update_assignments}"
        )
        cur.execute(sql, values)
    else:
        cur.execute(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})", values)
    conn.commit()


def ensure_metadata_table(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()


def set_metadata(conn: sqlite3.Connection, key: str, value: Any) -> None:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO metadata(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value) if not isinstance(value, str) else value),
    )
    conn.commit()


def get_metadata(conn: sqlite3.Connection, key: str) -> Any:
    """Retrieve a metadata value by key.
    
    Args:
        conn: SQLite connection
        key: The metadata key to retrieve
        
    Returns:
        The parsed value, or None if not found
    """
    cur = conn.cursor()
    cur.execute("SELECT value FROM metadata WHERE key = ?", (key,))
    row = cur.fetchone()
    if row:
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return row[0]
    return None


def prune_missing_ids(conn: sqlite3.Connection, table: str, keep_ids: List[int]) -> None:
    """Delete rows whose id is not in keep_ids. No-op if keep_ids is empty.

    Guards against accidental full wipes when a fetch fails by skipping deletion
    when no ids were collected.
    """
    if not keep_ids:
        return
    placeholders = ",".join(["?"] * len(keep_ids))
    sql = f"DELETE FROM {table} WHERE id NOT IN ({placeholders})"
    cur = conn.cursor()
    cur.execute(sql, keep_ids)
    conn.commit()


def get_all_nations(db_path: Path) -> Dict[str, Any]:
    """Fetch all nations from the nations database.
    
    Retrieves all nation records from the nations.db SQLite database and
    parses JSON-encoded fields back to their original types. Also retrieves
    the last_fetched timestamp from the metadata table.
    
    Args:
        db_path: Path to nations.db SQLite database
        
    Returns:
        Dictionary with 'nations' list and 'last_fetched' timestamp
        
    Raises:
        sqlite3.Error: If database query fails
    """
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Get all nations
        cur.execute("SELECT * FROM nations")
        nations = [dict(row) for row in cur.fetchall()]
        
        # Parse JSON fields back to their original types
        for nation in nations:
            for key, val in nation.items():
                if isinstance(val, str):
                    try:
                        nation[key] = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        pass
        
        # Get last_fetched timestamp
        ensure_metadata_table(conn)
        last_fetched = get_metadata(conn, 'last_fetched')
        
        return {
            'nations': nations,
            'last_fetched': last_fetched
        }


def get_all_alliances(db_path: Path) -> Dict[str, Any]:
    """Fetch all alliances from the alliances database.

    Returns an object with `alliances` and `last_fetched`. Gracefully handles
    missing tables so callers can treat empty datasets as no data yet.
    """
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Detect table presence without throwing on fresh DBs
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alliances'")
        has_table = cur.fetchone() is not None

        alliances: List[Dict[str, Any]] = []
        if has_table:
            cur.execute("SELECT * FROM alliances")
            alliances = [dict(row) for row in cur.fetchall()]
            for alliance in alliances:
                for key, val in alliance.items():
                    if isinstance(val, str):
                        try:
                            alliance[key] = json.loads(val)
                        except (json.JSONDecodeError, TypeError):
                            pass

        ensure_metadata_table(conn)
        last_fetched = get_metadata(conn, 'last_fetched')

        return {
            'alliances': alliances,
            'last_fetched': last_fetched,
        }


# --- Builds DB helpers (extracted from legacy utils.py) ---

IMPROVEMENT_FIELDS: List[str] = [
    'infrastructure', 'oilpower', 'windpower', 'coalpower', 'nuclearpower',
    'coalmine', 'oilwell', 'uramine', 'leadmine', 'ironmine', 'bauxitemine',
    'farm', 'gasrefinery', 'aluminumrefinery', 'steelmill', 'munitionsfactory',
    'policestation', 'hospital', 'recyclingcenter', 'subway', 'supermarket',
    'bank', 'mall', 'stadium', 'barracks', 'factory', 'airforcebase', 'drydock'
]


def fetch_build_rows(
    db_path: Path,
    infra_level: int,
    mmr_mins: Dict[str, int],
    caps: Dict[str, int],
    restricted_mines: List[str],
) -> List[Dict[str, int]]:
    """Fetch build rows matching criteria from the builds DB.

    Args:
        db_path: Path to SQLite DB
        infra_level: Exact infrastructure value to match
        mmr_mins: Dict with keys barracks/factory/airforcebase/drydock minimums
        caps: Dict with keys hospital/recyclingcenter/bank/mall caps
        restricted_mines: List of improvement names (json names) that must be zero

    Returns:
        List of dictionaries keyed by IMPROVEMENT_FIELDS
    """
    improvements = [f for f in IMPROVEMENT_FIELDS if f != 'infrastructure']
    fields = IMPROVEMENT_FIELDS

    where_clauses = ["infrastructure = ?"]
    params: List[Any] = [infra_level]

    # MMR filters
    for key in ("barracks", "factory", "airforcebase", "drydock"):
        if key in mmr_mins and mmr_mins[key] > 0:
            where_clauses.append(f"{key} >= ?")
            params.append(mmr_mins[key])

    # Restricted mines must be zero
    for mine in restricted_mines:
        where_clauses.append(f"{mine} = 0")

    # Caps
    for key in ("hospital", "recyclingcenter", "bank", "mall"):
        if key in caps:
            where_clauses.append(f"{key} <= ?")
            params.append(caps[key])

    sql = "SELECT " + ", ".join(fields) + " FROM builds WHERE " + " AND ".join(where_clauses)

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()

    results: List[Dict[str, int]] = []
    for row in rows:
        results.append({key: int(row[key]) for key in fields})
    return results


# --- Web data storage helpers ---

async def write_web(category: str, user_id: int, data: Dict[str, Any], timestamp: int) -> None:
    """Write data to the web storage directory as JSON.
    
    Args:
        category: The category (e.g., 'damage', 'raids', 'builds')
        user_id: The user ID
        data: Dictionary to store as JSON
        timestamp: Unix timestamp for the file
    """
    import aiofiles
    
    web_path = Path.cwd() / 'data' / 'web' / category / str(user_id)
    web_path.mkdir(parents=True, exist_ok=True)
    
    file_path = web_path / f"{timestamp}.json"
    async with aiofiles.open(file_path, 'w') as f:
        await f.write(json.dumps(data))


async def read_web(category: str, user_id: int, timestamp: int) -> Optional[Dict[str, Any]]:
    """Read data from the web storage directory.
    
    Args:
        category: The category (e.g., 'damage', 'raids', 'builds')
        user_id: The user ID
        timestamp: Unix timestamp for the file
        
    Returns:
        Dictionary containing the stored data, or None if file not found
    """
    import aiofiles
    
    file_path = Path.cwd() / 'data' / 'web' / category / str(user_id) / f"{timestamp}.json"
    
    if not file_path.exists():
        return None
    
    async with aiofiles.open(file_path, 'r') as f:
        content = await f.read()
        return json.loads(content)
