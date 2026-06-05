"""Composizione del contesto applicativo: config, DB, percorsi.

Centralizza il wiring così che CLI e fasi non ripetano il caricamento di settings,
l'apertura del DB e l'inizializzazione dello schema.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from poc_istruzioni.config import Prices, Settings, load_prices, load_settings
from poc_istruzioni.db.connection import connect, init_db


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_path(p: Path | str) -> Path:
    """Risolve un percorso di config relativo rispetto alla radice del repo."""
    path = Path(p)
    return path if path.is_absolute() else _repo_root() / path


@dataclass
class Context:
    settings: Settings
    prices: Prices
    conn: sqlite3.Connection


def db_path(settings: Settings) -> Path:
    """Percorso del DB; override via POC_DB_PATH (utile per i test)."""
    env = os.environ.get("POC_DB_PATH")
    return Path(env) if env else resolve_path(settings.paths.db_path)


def build_context() -> Context:
    """Carica config, apre il DB (creando la cartella) e applica lo schema."""
    settings = load_settings()
    prices = load_prices()
    path = db_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    init_db(conn)
    return Context(settings=settings, prices=prices, conn=conn)
