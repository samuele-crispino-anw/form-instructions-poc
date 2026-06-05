"""Repository tipizzati sulle tabelle SQLite. Query esplicite, nessun ORM.

In Fase 0 è presente il repository `documents`, sufficiente a esercitare lo schema
e i vincoli di integrità. Gli altri (sections, queries, ...) si aggiungono per fase.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Document:
    """Riga della tabella `documents` (PDF sorgente)."""

    id: str
    modello: str
    edizione: str
    periodo_imposta: str
    sha256: str
    path: str
    agg_data: str | None = None


def insert_document(conn: sqlite3.Connection, doc: Document) -> None:
    conn.execute(
        "INSERT INTO documents "
        "(id, modello, edizione, periodo_imposta, agg_data, sha256, path) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            doc.id,
            doc.modello,
            doc.edizione,
            doc.periodo_imposta,
            doc.agg_data,
            doc.sha256,
            doc.path,
        ),
    )
    conn.commit()


def get_document(conn: sqlite3.Connection, doc_id: str) -> Document | None:
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if row is None:
        return None
    return Document(
        id=row["id"],
        modello=row["modello"],
        edizione=row["edizione"],
        periodo_imposta=row["periodo_imposta"],
        sha256=row["sha256"],
        path=row["path"],
        agg_data=row["agg_data"],
    )
