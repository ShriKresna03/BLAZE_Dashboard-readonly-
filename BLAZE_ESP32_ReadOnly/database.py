"""SQLite storage for the BLAZE dashboard (telemetry + batch sessions)."""
from __future__ import annotations

import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "blaze.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

BAND_LOW = 300.0     # display reference band, not a safety limit
BAND_HIGH = 500.0
MAX_SAMPLE_GAP_S = 10.0   # gaps longer than this are not counted as "time in band"
MAX_TELEMETRY_ROWS = 100_000


def _now() -> str:
    # Fixed-width ISO format so string comparison == time comparison.
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@contextmanager
def connect():
    """Open a connection, commit on success, ALWAYS close.

    (sqlite3's own `with conn:` commits but never closes, which leaks
    connections on every Streamlit rerun.)
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_TELEMETRY_SQL = """
    CREATE TABLE IF NOT EXISTS telemetry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        temperature REAL,                       -- NULL = no valid reading (sensor fault)
        sensor_status TEXT NOT NULL,
        state TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'SIMULATOR',
        created_at TEXT NOT NULL
    )
"""


def init_db() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")

        # Migrate older databases where temperature was NOT NULL.
        cols = {r["name"]: r for r in conn.execute("PRAGMA table_info(telemetry)")}
        if cols and cols["temperature"]["notnull"]:
            conn.execute("ALTER TABLE telemetry RENAME TO telemetry_old")
            conn.execute(_TELEMETRY_SQL)
            conn.execute(
                """INSERT INTO telemetry
                   (id, temperature, sensor_status, state, source, created_at)
                   SELECT id, temperature, sensor_status, state, source, created_at
                   FROM telemetry_old"""
            )
            conn.execute("DROP TABLE telemetry_old")

        conn.execute(_TELEMETRY_SQL)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_telemetry_created ON telemetry(created_at)"
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_name TEXT,
                feedstock TEXT,
                mass_in_g REAL,
                mass_out_g REAL,
                started_at TEXT NOT NULL,
                stopped_at TEXT,
                duration_seconds REAL,
                peak_temperature REAL,
                seconds_in_reference_band REAL,
                notes TEXT
            )
        """)
        # Keep the table from growing forever (2 s samples = ~43k rows/day).
        conn.execute(
            """DELETE FROM telemetry WHERE id <= (
                   SELECT MAX(id) FROM telemetry) - ?""",
            (MAX_TELEMETRY_ROWS,),
        )


# ---------------------------------------------------------------- telemetry
def add_reading(temperature, sensor_status, state, source="SIMULATOR") -> None:
    if temperature is not None:
        temperature = float(temperature)
        if math.isnan(temperature):
            temperature = None
    with connect() as conn:
        conn.execute(
            """INSERT INTO telemetry
               (temperature, sensor_status, state, source, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (temperature, sensor_status, state, source, _now()),
        )


def latest_reading():
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM telemetry ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def latest_esp32_reading():
    """Return the newest ESP32-originated reading, ignoring old simulator rows."""
    with connect() as conn:
        row = conn.execute(
            """SELECT * FROM telemetry
               WHERE source LIKE 'ESP32:%'
               ORDER BY id DESC LIMIT 1"""
        ).fetchone()
    return dict(row) if row else None


def recent_readings(limit: int = 180):
    """Oldest-to-newest list of the most recent `limit` readings."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM telemetry ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def clear_telemetry() -> None:
    with connect() as conn:
        conn.execute("DELETE FROM telemetry")


# ----------------------------------------------------------------- sessions
def start_session(batch_name, feedstock, mass_in_g, notes) -> int:
    with connect() as conn:
        if conn.execute(
            "SELECT 1 FROM sessions WHERE stopped_at IS NULL LIMIT 1"
        ).fetchone():
            raise ValueError("A logging session is already active.")
        cur = conn.execute(
            """INSERT INTO sessions
               (batch_name, feedstock, mass_in_g, started_at, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (batch_name, feedstock, mass_in_g, _now(), notes),
        )
        return cur.lastrowid


def active_session():
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE stopped_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def stop_session(session_id: int, mass_out_g) -> None:
    stopped = _now()
    # 0 means "not measured yet" in the UI, so store NULL instead of a fake 0% yield.
    mass_out = float(mass_out_g) if mass_out_g and float(mass_out_g) > 0 else None

    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not row or row["stopped_at"]:
            return

        duration = max(
            0.0,
            (datetime.fromisoformat(stopped)
             - datetime.fromisoformat(row["started_at"])).total_seconds(),
        )

        rows = conn.execute(
            """SELECT temperature, created_at FROM telemetry
               WHERE created_at >= ? AND created_at <= ?
               ORDER BY created_at""",
            (row["started_at"], stopped),
        ).fetchall()

        valid = [
            (datetime.fromisoformat(r["created_at"]), float(r["temperature"]))
            for r in rows if r["temperature"] is not None
        ]
        peak = max((t for _, t in valid), default=None)

        # Use real timestamp gaps instead of assuming a fixed sample interval.
        in_band = 0.0
        for (t0, v0), (t1, _) in zip(valid, valid[1:]):
            dt = (t1 - t0).total_seconds()
            if BAND_LOW <= v0 < BAND_HIGH and 0 < dt <= MAX_SAMPLE_GAP_S:
                in_band += dt

        conn.execute(
            """UPDATE sessions SET
               stopped_at=?, duration_seconds=?, peak_temperature=?,
               seconds_in_reference_band=?, mass_out_g=?
               WHERE id=?""",
            (stopped, duration, peak, in_band, mass_out, session_id),
        )


def all_sessions(limit: int = 100):
    with connect() as conn:
        rows = conn.execute(
            """SELECT *,
                      CASE WHEN mass_out_g IS NOT NULL AND mass_in_g > 0
                           THEN mass_out_g * 100.0 / mass_in_g END AS yield_percent
               FROM sessions ORDER BY id DESC LIMIT ?""",
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]
