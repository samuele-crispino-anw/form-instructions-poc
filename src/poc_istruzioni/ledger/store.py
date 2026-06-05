"""Ledger delle chiamate LLM (FR-T2): scrittura per chiamata e aggregazioni di costo.

Risponde a "quanto è costata questa query / questa fase / oggi / questo modello".
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from poc_istruzioni.llm.pricing import Cost
from poc_istruzioni.llm.types import Usage
from poc_istruzioni.provenance import utc_now_iso

# Dimensione di aggregazione -> espressione SQL (allowlist: niente input utente in query).
_DIMENSIONS = {
    "purpose": "scopo",
    "model": "modello",
    "query": "query_id",
    "day": "substr(ts, 1, 10)",
}


@dataclass(frozen=True)
class CostRow:
    """Riga aggregata di costo (anche la riga `total`)."""

    key: str | None
    calls: int
    tok_in: int
    tok_out: int
    tok_cache_r: int
    tok_cache_w: int
    usd: float
    eur: float


def record_call(
    conn: sqlite3.Connection,
    *,
    scopo: str,
    modello: str,
    usage: Usage,
    cost: Cost,
    query_id: str | None = None,
    ts: str | None = None,
) -> int:
    """Inserisce una riga nel ledger e ritorna l'id. Ogni chiamata LLM passa di qui."""
    cur = conn.execute(
        "INSERT INTO llm_calls "
        "(ts, scopo, modello, tok_in, tok_out, tok_cache_r, tok_cache_w, usd, eur, query_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ts or utc_now_iso(),
            scopo,
            modello,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_input_tokens,
            usage.cache_creation_input_tokens,
            cost.usd,
            cost.eur,
            query_id,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


_AGG = (
    "COUNT(*) AS calls, "
    "COALESCE(SUM(tok_in), 0) AS tok_in, "
    "COALESCE(SUM(tok_out), 0) AS tok_out, "
    "COALESCE(SUM(tok_cache_r), 0) AS tok_cache_r, "
    "COALESCE(SUM(tok_cache_w), 0) AS tok_cache_w, "
    "COALESCE(SUM(usd), 0) AS usd, "
    "COALESCE(SUM(eur), 0) AS eur"
)


def _to_row(row: sqlite3.Row, key: str | None) -> CostRow:
    return CostRow(
        key=key,
        calls=row["calls"],
        tok_in=row["tok_in"],
        tok_out=row["tok_out"],
        tok_cache_r=row["tok_cache_r"],
        tok_cache_w=row["tok_cache_w"],
        usd=row["usd"],
        eur=row["eur"],
    )


def total(conn: sqlite3.Connection) -> CostRow:
    """Totale complessivo del ledger."""
    row = conn.execute(f"SELECT {_AGG} FROM llm_calls").fetchone()
    return _to_row(row, key=None)


def report_by(conn: sqlite3.Connection, dimension: str) -> list[CostRow]:
    """Aggregazione per 'purpose' | 'model' | 'query' | 'day'."""
    try:
        expr = _DIMENSIONS[dimension]
    except KeyError:
        raise ValueError(
            f"dimensione non valida: {dimension!r} (attese: {sorted(_DIMENSIONS)})"
        ) from None
    rows = conn.execute(
        f"SELECT {expr} AS key, {_AGG} FROM llm_calls GROUP BY {expr} ORDER BY {expr}"
    ).fetchall()
    return [_to_row(r, key=r["key"]) for r in rows]
