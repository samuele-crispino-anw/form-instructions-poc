"""Test del ledger: scrittura chiamate e aggregazioni di costo (FR-T2)."""

import pytest

from poc_istruzioni.db.connection import connect, init_db
from poc_istruzioni.ledger.store import record_call, report_by, total
from poc_istruzioni.llm.pricing import Cost
from poc_istruzioni.llm.types import Usage


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "ledger.db")
    init_db(c)
    yield c
    c.close()


def _seed(conn) -> None:
    # Tre chiamate su due scopi, due modelli, due giorni.
    record_call(
        conn, scopo="router", modello="claude-haiku-4-5",
        usage=Usage(input_tokens=100, output_tokens=10),
        cost=Cost(usd=1.0, eur=0.5), query_id="q1", ts="2026-06-05T10:00:00+00:00",
    )
    record_call(
        conn, scopo="answer", modello="claude-haiku-4-5",
        usage=Usage(input_tokens=200, output_tokens=20),
        cost=Cost(usd=2.0, eur=1.0), query_id="q1", ts="2026-06-05T10:01:00+00:00",
    )
    record_call(
        conn, scopo="conversion", modello="claude-opus-4-8",
        usage=Usage(input_tokens=1000, cache_creation_input_tokens=500),
        cost=Cost(usd=10.0, eur=5.0), query_id=None, ts="2026-06-06T09:00:00+00:00",
    )


def test_total_vuoto(conn) -> None:
    t = total(conn)
    assert t.calls == 0
    assert t.usd == 0
    assert t.eur == 0


def test_total_somma(conn) -> None:
    _seed(conn)
    t = total(conn)
    assert t.calls == 3
    assert t.usd == pytest.approx(13.0)
    assert t.eur == pytest.approx(6.5)
    assert t.tok_in == 1300


def test_report_by_purpose(conn) -> None:
    _seed(conn)
    by = {r.key: r for r in report_by(conn, "purpose")}
    assert set(by) == {"router", "answer", "conversion"}
    assert by["conversion"].usd == pytest.approx(10.0)
    assert by["router"].calls == 1


def test_report_by_model(conn) -> None:
    _seed(conn)
    by = {r.key: r for r in report_by(conn, "model")}
    assert by["claude-haiku-4-5"].calls == 2
    assert by["claude-haiku-4-5"].usd == pytest.approx(3.0)
    assert by["claude-opus-4-8"].calls == 1


def test_report_by_day(conn) -> None:
    _seed(conn)
    by = {r.key: r for r in report_by(conn, "day")}
    assert set(by) == {"2026-06-05", "2026-06-06"}
    assert by["2026-06-05"].calls == 2


def test_report_by_query(conn) -> None:
    _seed(conn)
    by = {r.key: r for r in report_by(conn, "query")}
    assert by["q1"].calls == 2  # due chiamate legate alla stessa query


def test_report_by_dimensione_invalida(conn) -> None:
    with pytest.raises(ValueError):
        report_by(conn, "scopo")  # nome interno, non dimensione pubblica
