"""Orchestrazione dell'ingestion. Per ora B1: registra documento e pagine renderizzate.

Lega rendering (render.py) e provenance (sha256 del PDF) alla persistenza (documents, pages),
così la catena PDF -> immagine pagina è ricostruibile e ripetibile (FR-T1/T3).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from poc_istruzioni.db.repositories import Document, Page, insert_page, upsert_document
from poc_istruzioni.ingest.render import render_pdf
from poc_istruzioni.provenance import sha256_file


def render_document(
    conn: sqlite3.Connection,
    *,
    doc_id: str,
    modello: str,
    edizione: str,
    periodo_imposta: str,
    agg_data: str | None,
    pdf_path: Path | str,
    pages_dir: Path | str,
    dpi: int,
) -> int:
    """Registra il documento, renderizza le pagine e le persiste. Ritorna il n. di pagine."""
    pdf_path = Path(pdf_path)
    upsert_document(
        conn,
        Document(
            id=doc_id,
            modello=modello,
            edizione=edizione,
            periodo_imposta=periodo_imposta,
            sha256=sha256_file(pdf_path),
            path=str(pdf_path),
            agg_data=agg_data,
        ),
    )
    rendered = render_pdf(pdf_path, pages_dir, dpi=dpi)
    for rp in rendered:
        insert_page(
            conn,
            Page(doc_id=doc_id, n=rp.n, png_path=str(rp.png_path), png_sha=rp.sha256),
        )
    return len(rendered)
