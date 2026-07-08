"""
Small SQLite-backed storage layer for journal entries, daily recaps,
and the user profile.

Note on persistence: on Streamlit Community Cloud the filesystem is
ephemeral — it resets whenever the app redeploys or sleeps for a long
time. For a single user's personal journaling this is normally fine
day-to-day, but if you want entries to truly never disappear, point
DB_PATH (below) at a mounted volume or swap this module for a hosted
DB (e.g. Turso, Supabase, a Google Sheet, etc).
"""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "talk_it_out.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS entries (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at REAL NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS recaps (
                date TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                name TEXT,
                phone TEXT
            )"""
        )


# ---------- profile ----------
def get_profile():
    with _conn() as conn:
        row = conn.execute("SELECT name, phone FROM profile WHERE id = 1").fetchone()
        return dict(row) if row else None


def save_profile(name: str, phone: str = ""):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO profile (id, name, phone) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, phone=excluded.phone",
            (name, phone),
        )


def clear_profile():
    with _conn() as conn:
        conn.execute("DELETE FROM profile WHERE id = 1")


# ---------- entries ----------
def add_entry(date: str, time_str: str, kind: str, text: str) -> str:
    entry_id = uuid.uuid4().hex
    with _conn() as conn:
        conn.execute(
            "INSERT INTO entries (id, date, time, kind, text, created_at) VALUES (?,?,?,?,?,?)",
            (entry_id, date, time_str, kind, text, time.time()),
        )
    return entry_id


def update_entry(entry_id: str, date: str, time_str: str, kind: str, text: str):
    with _conn() as conn:
        conn.execute(
            "UPDATE entries SET date=?, time=?, kind=?, text=? WHERE id=?",
            (date, time_str, kind, text, entry_id),
        )


def delete_entry(entry_id: str):
    with _conn() as conn:
        conn.execute("DELETE FROM entries WHERE id=?", (entry_id,))


def get_entries(date: str = None, since: str = None):
    with _conn() as conn:
        if date:
            rows = conn.execute(
                "SELECT * FROM entries WHERE date=? ORDER BY time ASC", (date,)
            ).fetchall()
        elif since:
            rows = conn.execute(
                "SELECT * FROM entries WHERE date>=? ORDER BY date ASC, time ASC", (since,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM entries ORDER BY date ASC, time ASC"
            ).fetchall()
        return [dict(r) for r in rows]


def all_dates_with_entries():
    with _conn() as conn:
        rows = conn.execute("SELECT DISTINCT date FROM entries").fetchall()
        return {r["date"] for r in rows}


# ---------- recaps ----------
def get_recap(date: str):
    with _conn() as conn:
        row = conn.execute("SELECT data FROM recaps WHERE date=?", (date,)).fetchone()
        return json.loads(row["data"]) if row else None


def save_recap(date: str, recap: dict):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO recaps (date, data) VALUES (?, ?) "
            "ON CONFLICT(date) DO UPDATE SET data=excluded.data",
            (date, json.dumps(recap)),
        )


def all_recaps():
    with _conn() as conn:
        rows = conn.execute("SELECT date, data FROM recaps").fetchall()
        return {r["date"]: json.loads(r["data"]) for r in rows}
