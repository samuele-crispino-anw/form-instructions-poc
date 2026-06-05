"""Test dell'analisi layout (§2): classify puro + geometria su PDF sintetici."""

import fitz

from poc_istruzioni.ingest.layout import (
    analyze_document,
    classify,
    summarize,
    write_csv,
)

# --- classify (funzione pura) ---------------------------------------------

def _kw(**over):
    base = dict(
        n_words=300, n_lines=40, gutter_ratio=0.5, median_line_width=0.9,
        pct_lines_wide=0.8, n_lines_rects=0, has_ghost=False,
    )
    base.update(over)
    return base


def test_classify_anomalous_per_ghost() -> None:
    assert classify(**_kw(has_ghost=True)) == "anomalous"


def test_classify_anomalous_quasi_vuota() -> None:
    assert classify(**_kw(n_words=5)) == "anomalous"


def test_classify_table_heavy() -> None:
    assert classify(**_kw(n_lines_rects=30)) == "table_heavy"


def test_classify_multi_column() -> None:
    assert classify(**_kw(median_line_width=0.4, pct_lines_wide=0.1, gutter_ratio=0.05)) == (
        "multi_column"
    )


def test_classify_single_column() -> None:
    assert classify(**_kw()) == "single_column"


# --- geometria su PDF sintetici -------------------------------------------

def _single_col_pdf(path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    rect = fitz.Rect(50, 50, page.rect.width - 50, page.rect.height - 50)
    page.insert_textbox(rect, "parola " * 200, fontsize=11)
    doc.save(str(path))
    doc.close()


def _two_col_pdf(path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    w, h = page.rect.width, page.rect.height
    # Gutter centrale netto: colonne entro [0.08w, 0.42w] e [0.58w, 0.92w].
    left = fitz.Rect(0.08 * w, 50, 0.42 * w, h - 50)
    right = fitz.Rect(0.58 * w, 50, 0.92 * w, h - 50)
    page.insert_textbox(left, "parola " * 120, fontsize=11)
    page.insert_textbox(right, "parola " * 120, fontsize=11)
    doc.save(str(path))
    doc.close()


def test_pagina_colonna_singola(tmp_path) -> None:
    pdf = tmp_path / "single.pdf"
    _single_col_pdf(pdf)
    m = analyze_document(pdf)[0]
    assert m.classification == "single_column"
    assert m.median_line_width > 0.6


def test_pagina_due_colonne(tmp_path) -> None:
    pdf = tmp_path / "two.pdf"
    _two_col_pdf(pdf)
    m = analyze_document(pdf)[0]
    assert m.classification == "multi_column"
    assert m.median_line_width < 0.55


# --- summarize / CSV -------------------------------------------------------

def test_summarize_e_csv(tmp_path) -> None:
    pdf = tmp_path / "single.pdf"
    _single_col_pdf(pdf)
    metrics = analyze_document(pdf)
    counts = summarize(metrics)
    assert counts["single_column"] == 1
    out = write_csv(metrics, tmp_path / "layout.csv")
    content = out.read_text(encoding="utf-8")
    assert content.startswith("page,n_words,")
    assert "single_column" in content
