"""Test estrazione text-layer e rimozione boilerplate (header/footer ripetuti)."""

import fitz

from poc_istruzioni.ingest.textlayer import (
    extract_pages_text,
    find_boilerplate_lines,
    strip_lines,
)

HEADER = "Istruzioni per la compilazione 2026"


def _make_pdf(path, bodies: list[str]) -> None:
    doc = fitz.open()
    for body in bodies:
        page = doc.new_page()
        page.insert_text((72, 72), HEADER)
        page.insert_text((72, 120), body)
    doc.save(str(path))
    doc.close()


def test_estrae_una_stringa_per_pagina(tmp_path) -> None:
    pdf = tmp_path / "d.pdf"
    _make_pdf(pdf, ["corpo uno", "corpo due", "corpo tre"])
    pages = extract_pages_text(pdf)
    assert len(pages) == 3
    assert "corpo due" in pages[1]


def test_individua_header_ripetuto(tmp_path) -> None:
    pdf = tmp_path / "d.pdf"
    _make_pdf(pdf, ["corpo uno", "corpo due", "corpo tre"])
    boiler = find_boilerplate_lines(extract_pages_text(pdf), min_fraction=0.6)
    assert HEADER in boiler  # presente su tutte le pagine
    assert "corpo uno" not in boiler  # contenuto unico


def test_strip_lines_rimuove_boilerplate() -> None:
    text = f"{HEADER}\nRighi RP1-RP4\nfranchigia 129,11"
    out = strip_lines(text, {HEADER})
    assert HEADER not in out
    assert "Righi RP1-RP4" in out
    assert "129,11" in out


def test_boilerplate_vuoto_su_input_vuoto() -> None:
    assert find_boilerplate_lines([]) == set()
