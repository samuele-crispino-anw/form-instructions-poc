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


def upsert_document(conn: sqlite3.Connection, doc: Document) -> None:
    """Inserisce o sostituisce un documento (idempotente sul re-ingest)."""
    conn.execute(
        "INSERT OR REPLACE INTO documents "
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


@dataclass(frozen=True)
class Page:
    """Riga della tabella `pages` (pagina renderizzata, FR-B1/B2)."""

    doc_id: str
    n: int
    png_path: str | None = None
    png_sha: str | None = None
    vlm_status: str | None = None
    overlap_score: float | None = None
    needs_review: bool = False


def insert_page(conn: sqlite3.Connection, page: Page) -> None:
    """Inserisce o sostituisce una pagina (idempotente sul re-rendering)."""
    conn.execute(
        "INSERT OR REPLACE INTO pages "
        "(doc_id, n, png_path, png_sha, vlm_status, overlap_score, needs_review) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            page.doc_id,
            page.n,
            page.png_path,
            page.png_sha,
            page.vlm_status,
            page.overlap_score,
            int(page.needs_review),
        ),
    )
    conn.commit()


def update_page_status(
    conn: sqlite3.Connection,
    doc_id: str,
    n: int,
    *,
    vlm_status: str,
    overlap_score: float,
    needs_review: bool,
) -> None:
    """Aggiorna l'esito della trascrizione VLM su una pagina già renderizzata (FR-B2)."""
    conn.execute(
        "UPDATE pages SET vlm_status = ?, overlap_score = ?, needs_review = ? "
        "WHERE doc_id = ? AND n = ?",
        (vlm_status, overlap_score, int(needs_review), doc_id, n),
    )
    conn.commit()


def get_pages(conn: sqlite3.Connection, doc_id: str) -> list[Page]:
    rows = conn.execute(
        "SELECT * FROM pages WHERE doc_id = ? ORDER BY n", (doc_id,)
    ).fetchall()
    return [
        Page(
            doc_id=r["doc_id"],
            n=r["n"],
            png_path=r["png_path"],
            png_sha=r["png_sha"],
            vlm_status=r["vlm_status"],
            overlap_score=r["overlap_score"],
            needs_review=bool(r["needs_review"]),
        )
        for r in rows
    ]
