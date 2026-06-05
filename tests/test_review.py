"""Test del generatore di review HTML (FR-B2, livello C)."""

from poc_istruzioni.ingest.checks import run_checks
from poc_istruzioni.ingest.review import ReviewItem, build_review_html, write_review_html


def _item(tmp_path, page_n, vlm_md, pdf_text):
    img = tmp_path / f"p{page_n:03d}.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")  # byte fittizi: serve solo l'embedding
    report = run_checks(vlm_md, pdf_text)
    return ReviewItem(page_n=page_n, image_path=img, vlm_md=vlm_md, report=report)


def test_html_contiene_immagine_markdown_e_stato(tmp_path) -> None:
    item = _item(
        tmp_path, 54,
        "## QUADRO RP\n### Righi RP1-RP4\ncodice 1 franchigia 129,11",
        "QUADRO RP Righi RP1 RP4 codice 1 franchigia 129,11",
    )
    out = build_review_html("Calibrazione", [item])
    assert "data:image/png;base64," in out  # immagine embeddata
    assert "QUADRO RP" in out               # markdown mostrato
    assert "p054" in out
    assert "OK" in out


def test_html_segnala_pagina_da_rivedere(tmp_path) -> None:
    # markdown con artefatto -> needs_review
    item = _item(
        tmp_path, 99,
        "## QUADRO RP REDDITI SC 2023 codice 1",
        "QUADRO RP codice 1",
    )
    out = build_review_html("Batch", [item])
    assert "DA RIVEDERE" in out
    assert "artefatti" in out


def test_escape_html_nel_markdown(tmp_path) -> None:
    item = _item(tmp_path, 1, "testo con <tag> & simboli", "testo con tag simboli")
    out = build_review_html("X", [item])
    assert "&lt;tag&gt;" in out  # markdown escapato, non interpretato


def test_write_review_html_scrive_file(tmp_path) -> None:
    item = _item(tmp_path, 1, "## QUADRO RP", "QUADRO RP")
    path = write_review_html(tmp_path / "review.html", "T", [item])
    assert path.exists()
    assert path.read_text(encoding="utf-8").startswith("<!doctype html>")
