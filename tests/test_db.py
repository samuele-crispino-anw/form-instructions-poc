"""Test schema SQLite, round-trip documents e vincoli di integrità."""

import sqlite3

import pytest

from poc_istruzioni.db.connection import connect, init_db
from poc_istruzioni.db.repositories import Document, get_document, insert_document

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
