import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get('DI04_DB_PATH', str(BASE_DIR / 'grievances.db'))


def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.execute('PRAGMA foreign_keys = ON')
        con.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('citizen','admin','worker')),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            citizen_id INTEGER NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            voice_text TEXT DEFAULT '',
            category TEXT NOT NULL,
            priority TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Submitted',
            location_text TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            photo_filename TEXT,
            audio_filename TEXT,
            evidence_filename TEXT,
            assigned_team TEXT NOT NULL DEFAULT 'Unassigned',
            worker_id INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            sla_due TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER NOT NULL REFERENCES complaints(id) ON DELETE CASCADE,
            actor_id INTEGER REFERENCES users(id),
            action TEXT NOT NULL,
            details TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_complaints_citizen ON complaints(citizen_id);
        CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);
        CREATE INDEX IF NOT EXISTS idx_complaints_sla ON complaints(sla_due);
        CREATE INDEX IF NOT EXISTS idx_history_complaint ON history(complaint_id);
        ''')
