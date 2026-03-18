import math
import sqlite3
import config

_db_path = None  # overridden by app.py in cloud mode


def set_db_path(path):
    global _db_path
    _db_path = path


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path or config.DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id          TEXT PRIMARY KEY,
                date_utc    TEXT NOT NULL,
                media_type  TEXT NOT NULL,
                filename    TEXT NOT NULL,
                poster      TEXT,
                latitude    REAL,
                longitude   REAL,
                year        INTEGER,
                month       INTEGER,
                day         INTEGER,
                user_id     TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_date
                ON memories(date_utc);
            CREATE INDEX IF NOT EXISTS idx_year_month
                ON memories(year, month);
            CREATE INDEX IF NOT EXISTS idx_latlon
                ON memories(latitude, longitude)
                WHERE latitude IS NOT NULL;
        """)
        # Migrate existing databases without user_id column
        try:
            conn.execute("ALTER TABLE memories ADD COLUMN user_id TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_user_id
                ON memories(user_id);
        """)
    conn.close()


def upsert_memory(conn: sqlite3.Connection, record: dict):
    row = {**record, "user_id": record.get("user_id")}
    conn.execute("""
        INSERT OR IGNORE INTO memories
            (id, date_utc, media_type, filename, poster,
             latitude, longitude, year, month, day, user_id)
        VALUES
            (:id, :date_utc, :media_type, :filename, :poster,
             :latitude, :longitude, :year, :month, :day, :user_id)
    """, row)
    conn.commit()


def query_memories(filters: dict, user_id: str) -> list[dict]:
    conditions = ["user_id = ?"]
    params = [user_id]

    if filters.get("date_from"):
        conditions.append("date_utc >= ?")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        conditions.append("date_utc <= ?")
        params.append(filters["date_to"] + "T23:59:59")
    # Cross-year filters (e.g. "March 18 in every year")
    if filters.get("month_day_from") and filters.get("month_day_to"):
        conditions.append("strftime('%m-%d', date_utc) BETWEEN ? AND ?")
        params.extend([filters["month_day_from"], filters["month_day_to"]])
    elif filters.get("month_day_from"):
        conditions.append("strftime('%m-%d', date_utc) = ?")
        params.append(filters["month_day_from"])
    if filters.get("month"):
        conditions.append("strftime('%m', date_utc) = ?")
        params.append(str(filters["month"]).zfill(2))
    if filters.get("year"):
        conditions.append("year = ?")
        params.append(int(filters["year"]))
    if filters.get("media_type"):
        conditions.append("media_type = ?")
        params.append(filters["media_type"].lower())

    # Bounding-box pre-filter for location (uses index)
    if filters.get("lat") is not None and filters.get("lon") is not None:
        radius_km = float(filters.get("radius_km", 5.0))
        lat_delta = radius_km / 111.0
        lon_delta = radius_km / (111.0 * max(0.01, abs(math.cos(math.radians(filters["lat"])))))
        conditions.append(
            "latitude  BETWEEN ? AND ? AND "
            "longitude BETWEEN ? AND ?"
        )
        params += [
            filters["lat"] - lat_delta, filters["lat"] + lat_delta,
            filters["lon"] - lon_delta, filters["lon"] + lon_delta,
        ]

    where    = "WHERE " + " AND ".join(conditions)
    page     = max(1, int(filters.get("page", 1)))
    per_page = min(100, int(filters.get("per_page", 50)))
    offset   = (page - 1) * per_page

    conn = get_connection()
    rows = conn.execute(
        f"SELECT * FROM memories {where} ORDER BY date_utc DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()
    total = conn.execute(
        f"SELECT COUNT(*) FROM memories {where}", params
    ).fetchone()[0]
    conn.close()
    return {"items": [dict(r) for r in rows], "total": total, "page": page, "per_page": per_page}


def get_map_points(user_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, filename, poster, date_utc, latitude, longitude "
        "FROM memories WHERE latitude IS NOT NULL AND user_id = ?",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_date_bounds(user_id: str) -> dict:
    conn = get_connection()
    row = conn.execute(
        "SELECT MIN(date_utc) AS min_date, MAX(date_utc) AS max_date "
        "FROM memories WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_stats(user_id: str | None = None) -> dict:
    conn = get_connection()
    if user_id:
        base = "FROM memories WHERE user_id = ?"
        params: tuple = (user_id,)
    else:
        base = "FROM memories WHERE 1=1"
        params = ()
    total    = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
    images   = conn.execute(f"SELECT COUNT(*) {base} AND media_type='image'", params).fetchone()[0]
    videos   = conn.execute(f"SELECT COUNT(*) {base} AND media_type='video'", params).fetchone()[0]
    with_gps = conn.execute(f"SELECT COUNT(*) {base} AND latitude IS NOT NULL", params).fetchone()[0]
    conn.close()
    return {"total": total, "images": images, "videos": videos, "with_gps": with_gps}


def count_memories_for_user(db_path, user_id: str) -> int:
    """Use a specific db path (for admin overview per user)."""
    try:
        conn = sqlite3.connect(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0
