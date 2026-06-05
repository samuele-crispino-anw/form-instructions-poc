"""Orchestrazione dell'ingestion. Per ora B1: registra documento e pagine renderizzate.

Lega rendering (render.py) e provenance (sha256 del PDF) alla persistenza (documents, pages),
così la catena PDF -> immagine pagina è ricostruibile e ripetibile (FR-T1/T3).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from poc_istruzioni.db.repositories import (
    Document,
    Page,
    insert_page,
    update_page_status,
    upsert_document,
)
from poc_istruzioni.ingest.checks import run_checks
from poc_istruzioni.ingest.render import render_pdf
from poc_istruzioni.ingest.review import ReviewItem, write_review_html
from poc_istruzioni.ingest.transcribe import transcribe_page
from poc_istruzioni.llm.client import LlmClient
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


@dataclass
class BatchSummary:
    """Riepilogo di un batch di trascrizione: pagine, da rivedere, costo, review."""

    pages: int
    needs_review: int
    review_path: Path
    usd: float
    eur: float


def transcribe_pages(
    conn: sqlite3.Connection,
    llm: LlmClient,
    *,
    doc_id: str,
    page_numbers: list[int],
    pages_dir: Path | str,
    markdown_dir: Path | str,
    ref_texts: dict[int, str],
    model: str,
    prompt: str,
    review_path: Path | str,
    title: str,
) -> BatchSummary:
    """Trascrive le pagine indicate, esegue i check, persiste e genera la review HTML.

    `ref_texts`: testo PDF di riferimento per pagina (già ripulito da header/footer).
    """
    pages_dir = Path(pages_dir)
    md_dir = Path(markdown_dir) / doc_id / "pages"
    md_dir.mkdir(parents=True, exist_ok=True)

    items: list[ReviewItem] = []
    usd = eur = 0.0
    n_review = 0

    for n in page_numbers:
        image_path = pages_dir / f"p{n:03d}.png"
        res = transcribe_page(llm, image_path, model=model, prompt=prompt, page_n=n)
        (md_dir / f"p{n:03d}.md").write_text(res.text, encoding="utf-8")

        report = run_checks(res.text, ref_texts.get(n, ""))
        update_page_status(
            conn,
            doc_id,
            n,
            vlm_status="needs_review" if report.needs_review else "ok",
            overlap_score=report.overlap,
            needs_review=report.needs_review,
        )
        items.append(ReviewItem(page_n=n, image_path=image_path, vlm_md=res.text, report=report))
        usd += res.cost.usd
        eur += res.cost.eur
        n_review += int(report.needs_review)

    write_review_html(review_path, title, items)
    return BatchSummary(
        pages=len(items),
        needs_review=n_review,
        review_path=Path(review_path),
        usd=usd,
        eur=eur,
    )
