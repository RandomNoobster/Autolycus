from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# --- Common DB paths ---

# Fields stored as JSON strings in SQLite (originally dict/list from the API).
# Only these are parsed with json.loads during reads for performance.
_JSON_FIELDS: frozenset[str] = frozenset({
    'wars', 'alliance', 'treasures', 'cities', 'bounties', 'military_research',
})


def _decode_row(row: sqlite3.Row) -> Dict[str, Any]:
    """Decode a sqlite row into a dict, parsing JSON-like string fields."""
    decoded = dict(row)
    for key, val in decoded.items():
        if isinstance(val, str):
            try:
                decoded[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
    return decoded


def get_nations_db_path() -> Path:
    """Return the absolute path to nations SQLite database."""
    return Path.cwd() / 'data' / 'nations.db'


def get_alliances_db_path() -> Path:
    """Return the absolute path to alliances SQLite database."""
    return Path.cwd() / 'data' / 'alliances.db'


def get_builds_db_path() -> Path:
    """Return the absolute path to the builds SQLite database."""
    return Path.cwd() / 'data' / 'city_builds.db'


def map_sqlite_type(value: Any) -> str:
    """Infer a reasonable SQLite column type from a Python value."""
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
    """Ensure the table exists and has columns for all keys in sample_row."""
    cur = conn.cursor()
    columns_def = []
    if "id" in sample_row:
        columns_def.append("id INTEGER PRIMARY KEY")
    columns_def.append("_created_at INTEGER")
    cur.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(columns_def)})")

    cur.execute(f"PRAGMA table_info({table})")
    existing_cols = {row[1] for row in cur.fetchall()}

    for key, val in sample_row.items():
        if key not in existing_cols:
            col_type = map_sqlite_type(val)
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {key} {col_type}")
            existing_cols.add(key)

    conn.commit()


def row_to_db_values(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a data row to DB-ready values."""
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
    """Delete rows whose id is not in keep_ids. No-op if keep_ids is empty."""
    if not keep_ids:
        return
    placeholders = ",".join(["?"] * len(keep_ids))
    sql = f"DELETE FROM {table} WHERE id NOT IN ({placeholders})"
    cur = conn.cursor()
    cur.execute(sql, keep_ids)
    conn.commit()


def get_all_nations(db_path: Path) -> Dict[str, Any]:
    """Fetch all nations from the nations database."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM nations")
        nations = [_decode_row(row) for row in cur.fetchall()]

        ensure_metadata_table(conn)
        last_fetched = get_metadata(conn, 'last_fetched')

        return {
            'nations': nations,
            'last_fetched': last_fetched,
        }


def get_all_nations_filtered(
    db_path: Path,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    nation_ids: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Fetch nations with optional SQL-level filters and selective JSON parsing."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        where_clauses: List[str] = []
        params: List[Any] = []

        if min_score is not None:
            where_clauses.append("score >= ?")
            params.append(min_score)
        if max_score is not None:
            where_clauses.append("score <= ?")
            params.append(max_score)
        if nation_ids:
            placeholders = ",".join("?" * len(nation_ids))
            where_clauses.append(f"id IN ({placeholders})")
            params.extend([int(nid) for nid in nation_ids if nid.isdigit()])

        sql = "SELECT * FROM nations"
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)

        cur.execute(sql, params)
        nations = [dict(row) for row in cur.fetchall()]

        for nation in nations:
            for key in _JSON_FIELDS:
                val = nation.get(key)
                if isinstance(val, str):
                    try:
                        nation[key] = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        pass
            for key, val in nation.items():
                if key in _JSON_FIELDS:
                    continue
                if isinstance(val, str) and val and val[0] in ('{', '['):
                    try:
                        nation[key] = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        pass

        ensure_metadata_table(conn)
        last_fetched = get_metadata(conn, 'last_fetched')

        return {
            'nations': nations,
            'last_fetched': last_fetched,
        }


def get_nation_by_id(db_path: Path, nation_id: int | str) -> Dict[str, Any]:
    """Fetch a single nation by ID from the nations database."""
    try:
        nation_id_int = int(str(nation_id))
    except (TypeError, ValueError):
        nation_id_int = None

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        nation = None
        if nation_id_int is not None:
            cur.execute("SELECT * FROM nations WHERE id = ?", (nation_id_int,))
            row = cur.fetchone()
            if row:
                nation = _decode_row(row)

        ensure_metadata_table(conn)
        last_fetched = get_metadata(conn, 'last_fetched')

        return {
            'nation': nation,
            'last_fetched': last_fetched,
        }


def get_all_alliances(db_path: Path) -> Dict[str, Any]:
    """Fetch all alliances from the alliances database."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alliances'")
        has_table = cur.fetchone() is not None

        alliances: List[Dict[str, Any]] = []
        if has_table:
            cur.execute("SELECT * FROM alliances")
            alliances = [_decode_row(row) for row in cur.fetchall()]

        ensure_metadata_table(conn)
        last_fetched = get_metadata(conn, 'last_fetched')
        return {
            'alliances': alliances,
            'last_fetched': last_fetched,
        }


def find_nation(arg: str | int) -> Optional[Dict[str, Any]]:
    """Find a nation in SQLite by id, nation_name, leader_name, or discord."""
    if isinstance(arg, str):
        arg = arg.strip()

    numeric_arg = re.sub(r"[^0-9]", "", str(arg))
    db_path = get_nations_db_path()
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        if numeric_arg:
            cur.execute("SELECT * FROM nations WHERE id = ? LIMIT 1", (int(numeric_arg),))
            row = cur.fetchone()
            if row:
                return _decode_row(row)

        for field in ("nation_name", "leader_name", "discord"):
            cur.execute(
                f"SELECT * FROM nations WHERE {field} = ? COLLATE NOCASE LIMIT 1",
                (str(arg),),
            )
            row = cur.fetchone()
            if row:
                return _decode_row(row)

    return None


def list_all_alliances() -> List[Dict[str, Any]]:
    """Return all alliances from SQLite cache."""
    return get_all_alliances(get_alliances_db_path()).get("alliances", [])


def get_alliances_by_ids(alliance_ids: List[str]) -> List[Dict[str, Any]]:
    """Return alliance rows whose ids are in alliance_ids."""
    unique_ids = [str(x) for x in set(alliance_ids) if str(x)]
    if not unique_ids:
        return []
    int_ids = [int(x) for x in unique_ids if str(x).isdigit()]
    if not int_ids:
        return []

    db_path = get_alliances_db_path()
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        placeholders = ",".join(["?"] * len(int_ids))
        cur.execute(f"SELECT * FROM alliances WHERE id IN ({placeholders})", int_ids)
        return [_decode_row(row) for row in cur.fetchall()]


def search_alliances_autocomplete(search_value: str) -> List[str]:
    """Alliance names formatted for slash autocomplete; substring on id/name/acronym."""
    needle = (search_value or "").lower()
    out: List[str] = []
    for aa in list_all_alliances():
        aa_id = str(aa.get("id", ""))
        aa_name = str(aa.get("name", ""))
        aa_acronym = str(aa.get("acronym", ""))
        if needle in aa_id.lower() or needle in aa_name.lower() or needle in aa_acronym.lower():
            out.append(f"{aa_name} ({aa_id})")
    return out


IMPROVEMENT_FIELDS: List[str] = [
    'infrastructure', 'oilpower', 'windpower', 'coalpower', 'nuclearpower',
    'coalmine', 'oilwell', 'uramine', 'leadmine', 'ironmine', 'bauxitemine',
    'farm', 'gasrefinery', 'aluminumrefinery', 'steelmill', 'munitionsfactory',
    'policestation', 'hospital', 'recyclingcenter', 'subway', 'supermarket',
    'bank', 'mall', 'stadium', 'barracks', 'factory', 'airforcebase', 'drydock',
]


def fetch_build_rows(
    db_path: Path,
    infra_level: int,
    mmr_mins: Dict[str, int],
    caps: Dict[str, int],
    restricted_mines: List[str],
) -> List[Dict[str, int]]:
    """Fetch build rows matching criteria from the builds DB."""
    fields = IMPROVEMENT_FIELDS
    where_clauses = ["infrastructure = ?"]
    params: List[Any] = [infra_level]

    for key in ("barracks", "factory", "airforcebase", "drydock"):
        if key in mmr_mins and mmr_mins[key] > 0:
            where_clauses.append(f"{key} >= ?")
            params.append(mmr_mins[key])

    for mine in restricted_mines:
        where_clauses.append(f"{mine} = 0")

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
