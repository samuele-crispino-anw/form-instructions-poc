"""Test del rendering pagine (FR-B1). Usa un PDF sintetico, non il corpus reale."""

import fitz

from poc_istruzioni.ingest.render import render_pdf
from poc_istruzioni.provenance import sha256_file


def _make_pdf(path, n_pages: int) -> None:
    doc = fitz.open()
    for i in range(n_pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"pagina {i + 1}")
    doc.save(str(path))
    doc.close()


def test_una_png_per_pagina(tmp_path) -> None:
    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, 3)
    pages = render_pdf(pdf, tmp_path / "pages", dpi=100)
    assert [p.n for p in pages] == [1, 2, 3]
    assert (tmp_path / "pages" / "p001.png").exists()
    assert (tmp_path / "pages" / "p003.png").exists()


def test_nomi_zero_padded(tmp_path) -> None:
    pdf = tmp_path / "d.pdf"
    _make_pdf(pdf, 1)
    pages = render_pdf(pdf, tmp_path / "o", dpi=72)
    assert pages[0].png_path.name == "p001.png"


def test_hash_riproducibile(tmp_path) -> None:
    # FR-T3: stesso input + stesso DPI -> stessi hash.
    pdf = tmp_path / "d.pdf"
    _make_pdf(pdf, 2)
    a = render_pdf(pdf, tmp_path / "a", dpi=100)
    b = render_pdf(pdf, tmp_path / "b", dpi=100)
    assert [p.sha256 for p in a] == [p.sha256 for p in b]


def test_hash_coincide_con_file(tmp_path) -> None:
    pdf = tmp_path / "d.pdf"
    _make_pdf(pdf, 1)
    pages = render_pdf(pdf, tmp_path / "o", dpi=100)
    assert pages[0].sha256 == sha256_file(pages[0].png_path)
