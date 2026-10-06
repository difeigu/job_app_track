import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    title TEXT,
    company TEXT,
    company_logo TEXT,
    location TEXT,
    work_mode TEXT,
    employment_type TEXT,
    status TEXT NOT NULL DEFAULT 'Wishlist',
    source TEXT,
    salary_min REAL,
    salary_max REAL,
    salary_currency TEXT,
    salary_period TEXT,
    description TEXT,
    date_posted TEXT,
    deadline TEXT,
    contact_name TEXT,
    contact_email TEXT,
    contact_phone TEXT,
    referral INTEGER DEFAULT 0,
    resume_version TEXT,
    cover_letter_used INTEGER DEFAULT 0,
    rating INTEGER,
    tags TEXT,
    applied_date TEXT,
    next_action TEXT,
    next_action_date TEXT,
    notes TEXT,
    scrape_status TEXT,
    scrape_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_date TEXT,
    description TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE
);
"""


def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
