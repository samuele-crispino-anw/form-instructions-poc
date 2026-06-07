"""Test schema SQLite, round-trip documents e vincoli di integrità."""

import sqlite3

import pytest

from poc_istruzioni.db.connection import connect, init_db
from poc_istruzioni.db.repositories import (
    ConversionRow,
    Document,
    Page,
    ReviewRow,
    false_positive_rules,
    get_document,
    get_pages,
    get_review,
    governance,
    insert_audit,
    insert_document,
    insert_page,
    insert_review,
    upsert_conversion,
)


def _doc(doc_id: str = "PF1-2026") -> Document:
    return Document(
        id=doc_id,
        modello="REDDITI-PF-F1",
        edizione="2026",
        periodo_imposta="2025",
        sha256="abc",
        path="data/raw/pf1.pdf",
    )

EXPECTED_TABLES = {
    "documents",
    "pages",
    "sections",
    "queries",
    "answer_traces",
    "llm_calls",
    "eval_cases",
    "eval_results",
}


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "test.db")
    init_db(c)
    yield c
    c.close()


def test_init_db_crea_tutte_le_tabelle(conn) -> None:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {r["name"] for r in rows}
    assert EXPECTED_TABLES <= names


def test_init_db_idempotente(conn) -> None:
    init_db(conn)  # seconda applicazione non deve sollevare
    init_db(conn)


def test_documents_round_trip(conn) -> None:
    doc = Document(
        id="PF1-2026",
        modello="REDDITI-PF-F1",
        edizione="2026",
        periodo_imposta="2025",
        sha256="abc123",
        path="data/raw/pf1.pdf",
        agg_data="2026-05-13",
    )
    insert_document(conn, doc)
    assert get_document(conn, "PF1-2026") == doc


def test_get_document_inesistente_ritorna_none(conn) -> None:
    assert get_document(conn, "NON-ESISTE") is None


def test_foreign_key_attiva(conn) -> None:
    # page con doc_id inesistente deve violare la foreign key.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO pages (doc_id, n) VALUES (?, ?)", ("MANCANTE", 1))
        conn.commit()


def test_pages_round_trip(conn) -> None:
    insert_document(conn, _doc())
    insert_page(conn, Page(doc_id="PF1-2026", n=1, png_path="p001.png", png_sha="aa"))
    insert_page(
        conn,
        Page(
            doc_id="PF1-2026",
            n=2,
            png_path="p002.png",
            png_sha="bb",
            vlm_status="needs_review",
            overlap_score=0.3,
            needs_review=True,
        ),
    )
    pages = get_pages(conn, "PF1-2026")
    assert [p.n for p in pages] == [1, 2]
    assert pages[1].needs_review is True
    assert pages[1].overlap_score == 0.3


def test_insert_page_idempotente(conn) -> None:
    insert_document(conn, _doc())
    insert_page(conn, Page(doc_id="PF1-2026", n=1, png_sha="aa"))
    insert_page(conn, Page(doc_id="PF1-2026", n=1, png_sha="bb"))  # stessa PK -> replace
    pages = get_pages(conn, "PF1-2026")
    assert len(pages) == 1
    assert pages[0].png_sha == "bb"


def _conv(n, route="A", model="claude-haiku-4-5", esc=0, status="ok"):
    return ConversionRow(
        doc_id="PF1-2026", n=n, route=route, model_used=model, escalations=esc,
        status=status, reasons=None, md_path=f"p{n:03d}.md", usd=0.01,
        ts="2026-06-05T00:00:00+00:00",
    )


def test_governance(conn) -> None:
    upsert_conversion(conn, _conv(2))  # A, no escalation
    upsert_conversion(conn, _conv(3, esc=1, model="claude-opus-4-8"))  # A escalata
    upsert_conversion(conn, _conv(1, route="B", model="claude-opus-4-8"))  # B
    upsert_conversion(conn, _conv(4, esc=2, status="needs_human"))  # escalata, umano
    insert_audit(conn, "PF1-2026", 2, gate_flagged=False, diff_found=True, gate_miss=True, ts="t")

    g = governance(conn, "PF1-2026")
    assert g["pages"] == 4
    assert g["route_a"] == 3 and g["route_b"] == 1
    assert g["escalated"] == 2  # p3 e p4
    assert g["needs_human"] == 1
    assert g["gate_misses"] == 1
    assert g["escalation_rate"] == 0.5


def test_reviews_round_trip_e_falsi_positivi(conn) -> None:
    insert_review(conn, ReviewRow(
        doc_id="PF1-2026", n=181, azione="falso_positivo", revisore="Samuele",
        nota="%% è nella fonte", regole_flaggate="lint: valore con simbolo doppio (es. 1,73%%)",
        sha_rifiutato="aa", sha_risolto="aa", ts="2026-06-07T00:00:00+00:00",
    ))
    insert_review(conn, ReviewRow(
        doc_id="PF1-2026", n=134, azione="corretta", revisore="Samuele",
        nota="reintegrati 2 numeri", regole_flaggate="numeri mancanti",
        sha_rifiutato="bb", sha_risolto="cc", ts="2026-06-07T00:01:00+00:00",
    ))
    r = get_review(conn, "PF1-2026", 181)
    assert r is not None and r.azione == "falso_positivo" and r.revisore == "Samuele"
    # solo i falsi positivi contano per la taratura delle regole
    fp = false_positive_rules(conn, "PF1-2026")
    assert fp == {"lint:simbolo_doppio": 1}
