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


@dataclass(frozen=True)
class ConversionRow:
    """Esito di conversione di una pagina (tabella `conversions`)."""

    doc_id: str
    n: int
    route: str
    model_used: str
    escalations: int
    status: str  # ok | needs_human
    reasons: str | None
    md_path: str | None
    usd: float
    ts: str


def upsert_conversion(conn: sqlite3.Connection, row: ConversionRow) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO conversions "
        "(doc_id, n, route, model_used, escalations, status, reasons, md_path, usd, ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            row.doc_id, row.n, row.route, row.model_used, row.escalations,
            row.status, row.reasons, row.md_path, row.usd, row.ts,
        ),
    )
    conn.commit()


def insert_audit(
    conn: sqlite3.Connection,
    doc_id: str,
    n: int,
    *,
    gate_flagged: bool,
    diff_found: bool,
    gate_miss: bool,
    ts: str,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO audits (doc_id, n, gate_flagged, diff_found, gate_miss, ts) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (doc_id, n, int(gate_flagged), int(diff_found), int(gate_miss), ts),
    )
    conn.commit()


def governance(conn: sqlite3.Connection, doc_id: str) -> dict:
    """Metriche di governance del run (FR-T2/D): rotte, escalation, esiti, audit."""
    rows = conn.execute(
        "SELECT route, escalations, status FROM conversions WHERE doc_id = ?", (doc_id,)
    ).fetchall()
    total = len(rows)
    by_route = {"A": 0, "B": 0}
    escalated = needs_human = 0
    for r in rows:
        by_route[r["route"]] = by_route.get(r["route"], 0) + 1
        if r["escalations"] > 0:
            escalated += 1
        if r["status"] == "needs_human":
            needs_human += 1
    misses = conn.execute(
        "SELECT COUNT(*) AS c FROM audits WHERE doc_id = ? AND gate_miss = 1", (doc_id,)
    ).fetchone()["c"]
    return {
        "pages": total,
        "route_a": by_route.get("A", 0),
        "route_b": by_route.get("B", 0),
        "escalated": escalated,
        "escalation_rate": (escalated / total) if total else 0.0,
        "needs_human": needs_human,
        "gate_misses": misses,
    }


@dataclass(frozen=True)
class ReviewRow:
    """Decisione del revisore umano su una pagina (tabella `reviews`)."""

    doc_id: str
    n: int
    azione: str  # corretta | falso_positivo
    revisore: str
    nota: str | None = None
    regole_flaggate: str | None = None
    sha_rifiutato: str | None = None
    sha_risolto: str | None = None
    ts: str = ""


def insert_review(conn: sqlite3.Connection, row: ReviewRow) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO reviews "
        "(doc_id, n, azione, revisore, nota, regole_flaggate, sha_rifiutato, sha_risolto, ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            row.doc_id, row.n, row.azione, row.revisore, row.nota,
            row.regole_flaggate, row.sha_rifiutato, row.sha_risolto, row.ts,
        ),
    )
    conn.commit()


def update_conversion_status(conn: sqlite3.Connection, doc_id: str, n: int, status: str) -> None:
    """Aggiorna lo stato di una conversione (es. dopo risoluzione umana)."""
    conn.execute(
        "UPDATE conversions SET status = ? WHERE doc_id = ? AND n = ?", (status, doc_id, n)
    )
    conn.commit()


def pending_reviews(conn: sqlite3.Connection, doc_id: str) -> list[sqlite3.Row]:
    """Pagine needs_human ancora senza decisione umana (coda di revisione)."""
    return conn.execute(
        "SELECT c.n, c.reasons, c.model_used, c.escalations FROM conversions c "
        "LEFT JOIN reviews r ON r.doc_id = c.doc_id AND r.n = c.n "
        "WHERE c.doc_id = ? AND c.status = 'needs_human' AND r.n IS NULL ORDER BY c.n",
        (doc_id,),
    ).fetchall()


def get_review(conn: sqlite3.Connection, doc_id: str, n: int) -> ReviewRow | None:
    r = conn.execute(
        "SELECT * FROM reviews WHERE doc_id = ? AND n = ?", (doc_id, n)
    ).fetchone()
    if r is None:
        return None
    return ReviewRow(
        doc_id=r["doc_id"], n=r["n"], azione=r["azione"], revisore=r["revisore"],
        nota=r["nota"], regole_flaggate=r["regole_flaggate"],
        sha_rifiutato=r["sha_rifiutato"], sha_risolto=r["sha_risolto"], ts=r["ts"],
    )


# Marcatori per attribuire un falso positivo alla regola che l'ha generato (calibrazione).
_RULE_MARKERS = {
    "simbolo doppio": "lint:simbolo_doppio",
    "dingbat": "lint:dingbat",
    "header/footer": "lint:header_footer",
    "numero di pagina": "lint:numero_pagina",
    "numeri mancanti": "gate:numeri_mancanti",
    "overlap basso": "gate:overlap",
    "parole critiche": "gate:parole_critiche",
    "abbinamenti codice": "gate:pair_codici",
    "ripetizione": "gate:ripetizione",
    "artefatti": "gate:artefatti",
}


def false_positive_rules(conn: sqlite3.Connection, doc_id: str) -> dict[str, int]:
    """Conteggio dei falsi positivi per regola (feedback per tarare gate/lint)."""
    rows = conn.execute(
        "SELECT regole_flaggate FROM reviews WHERE doc_id = ? AND azione = 'falso_positivo'",
        (doc_id,),
    ).fetchall()
    counts: dict[str, int] = {}
    for r in rows:
        text = (r["regole_flaggate"] or "").lower()
        for marker, rule in _RULE_MARKERS.items():
            if marker in text:
                counts[rule] = counts.get(rule, 0) + 1
    return counts


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
