"""Connessione SQLite e inizializzazione schema (no ORM).

`schema.sql` è la single-source del modello dati; `init_db` lo applica in modo idempotente.
`foreign_keys` va abilitato per connessione (non è persistente in SQLite).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Apre una connessione con row factory a dizionario e foreign key attive."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection, schema_path: Path | None = None) -> None:
    """Applica lo schema (CREATE TABLE IF NOT EXISTS): sicuro da rieseguire."""
    sql = (schema_path or _SCHEMA_PATH).read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()
