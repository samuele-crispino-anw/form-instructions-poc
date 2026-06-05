"""Test dell'orchestrazione B1 (render_document) su PDF sintetico e DB temporaneo."""

import fitz
import pytest

from poc_istruzioni.db.connection import connect, init_db
from poc_istruzioni.db.repositories import get_document, get_pages
from poc_istruzioni.ingest.pipeline import render_document


def _make_pdf(path, n_pages: int) -> None:
    doc = fitz.open()
    for i in range(n_pages):
        doc.new_page().insert_text((72, 72), f"pagina {i + 1}")
    doc.save(str(path))
    doc.close()


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "poc.db")
    init_db(c)
    yield c
    c.close()


def _render(conn, pdf, pages_dir, n=3):
    _make_pdf(pdf, n)
    return render_document(
        conn,
        doc_id="PF1-2026",
        modello="REDDITI-PF-F1",
        edizione="2026",
        periodo_imposta="2025",
        agg_data="2026-05-13",
        pdf_path=pdf,
        pages_dir=pages_dir,
        dpi=100,
    )


def test_registra_documento_e_pagine(conn, tmp_path) -> None:
    n = _render(conn, tmp_path / "d.pdf", tmp_path / "pages", n=3)
    assert n == 3

    doc = get_document(conn, "PF1-2026")
    assert doc is not None
    assert doc.modello == "REDDITI-PF-F1"
    assert len(doc.sha256) == 64  # sha256 del PDF

    pages = get_pages(conn, "PF1-2026")
    assert [p.n for p in pages] == [1, 2, 3]
    assert all(p.png_sha and p.png_path for p in pages)


def test_idempotente(conn, tmp_path) -> None:
    pdf = tmp_path / "d.pdf"
    _render(conn, pdf, tmp_path / "pages", n=2)
    # secondo render dello stesso PDF: nessun duplicato (PK doc_id,n -> replace)
    render_document(
        conn,
        doc_id="PF1-2026",
        modello="REDDITI-PF-F1",
        edizione="2026",
        periodo_imposta="2025",
        agg_data="2026-05-13",
        pdf_path=pdf,
        pages_dir=tmp_path / "pages",
        dpi=100,
    )
    assert len(get_pages(conn, "PF1-2026")) == 2
