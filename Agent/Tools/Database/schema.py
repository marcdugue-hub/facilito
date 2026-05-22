import sqlite3
import os
from pathlib import Path

import yaml

_BASE_DIR = Path(__file__).resolve().parents[3]

def _db_path() -> str:
    cfg_path = _BASE_DIR / "Agent" / "Config" / "app_config.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    db_file = _BASE_DIR / cfg["database"]["path"]
    db_file.parent.mkdir(parents=True, exist_ok=True)
    return str(db_file)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
    if "start_time" not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN start_time TEXT")
        conn.commit()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS facilitators (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS clients (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS teams (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL,
            client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS participants (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name  TEXT NOT NULL,
            email      TEXT,
            role       TEXT
        );

        CREATE TABLE IF NOT EXISTS team_participants (
            team_id        INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            participant_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
            PRIMARY KEY (team_id, participant_id)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            facilitator_id INTEGER NOT NULL REFERENCES facilitators(id),
            title          TEXT NOT NULL,
            date           TEXT,
            start_time     TEXT,
            objective      TEXT,
            status         TEXT NOT NULL DEFAULT 'draft',
            created_at     TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS session_clients (
            session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            client_id  INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
            PRIMARY KEY (session_id, client_id)
        );

        CREATE TABLE IF NOT EXISTS session_teams (
            session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            team_id    INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            PRIMARY KEY (session_id, team_id)
        );

        CREATE TABLE IF NOT EXISTS session_participants (
            session_id     INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            participant_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
            PRIMARY KEY (session_id, participant_id)
        );

        CREATE TABLE IF NOT EXISTS session_practices (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id       INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            practice_id      TEXT NOT NULL,
            source           TEXT NOT NULL DEFAULT 'rag',
            titre            TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL DEFAULT 30,
            position         INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS agent_events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT NOT NULL DEFAULT (datetime('now')),
            session_id   INTEGER,
            event_type   TEXT NOT NULL,
            summary      TEXT,
            payload      TEXT,
            tokens_in    INTEGER DEFAULT 0,
            tokens_out   INTEGER DEFAULT 0,
            duration_ms  INTEGER DEFAULT 0,
            resolved     INTEGER,
            fallback     INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS agent_ratings (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp  TEXT NOT NULL DEFAULT (datetime('now')),
            session_id INTEGER,
            rating     INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cost_config (
            key   TEXT PRIMARY KEY,
            value REAL NOT NULL
        );

        INSERT OR IGNORE INTO cost_config (key, value) VALUES ('cost_in',  1.5);
        INSERT OR IGNORE INTO cost_config (key, value) VALUES ('cost_out', 2.5);

        CREATE TABLE IF NOT EXISTS app_settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        INSERT OR IGNORE INTO app_settings (key, value) VALUES ('voice_mode', 'off');
        """)
        _migrate(conn)
