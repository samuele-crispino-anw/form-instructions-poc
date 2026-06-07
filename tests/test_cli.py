"""Test della CLI (report costs, version) su DB temporaneo, senza rete.

Lo smoke con chiamata reale è una verifica manuale (human-in-the-loop), non qui.
"""

from typer.testing import CliRunner

from poc_istruzioni.cli import app
from poc_istruzioni.db.connection import connect, init_db
from poc_istruzioni.ledger.store import record_call
from poc_istruzioni.llm.pricing import Cost
from poc_istruzioni.llm.types import Usage

runner = CliRunner()


def _seed_db(path) -> None:
    c = connect(path)
    init_db(c)
    record_call(
        c, scopo="router", modello="claude-haiku-4-5",
        usage=Usage(input_tokens=100, output_tokens=10),
        cost=Cost(usd=1.0, eur=0.5),
    )
    record_call(
        c, scopo="answer", modello="claude-haiku-4-5",
        usage=Usage(input_tokens=200, output_tokens=20),
        cost=Cost(usd=2.0, eur=1.0),
    )
    c.close()


def test_version() -> None:
    res = runner.invoke(app, ["version"])
    assert res.exit_code == 0
    assert res.stdout.strip() != ""


def test_report_costs_totale(tmp_path, monkeypatch) -> None:
    db = tmp_path / "poc.db"
    _seed_db(db)
    monkeypatch.setenv("POC_DB_PATH", str(db))
    res = runner.invoke(app, ["report", "costs"])
    assert res.exit_code == 0
    assert "TOTALE" in res.stdout
    assert "3.000000" in res.stdout  # somma USD (6 decimali)


def test_report_costs_per_scopo(tmp_path, monkeypatch) -> None:
    db = tmp_path / "poc.db"
    _seed_db(db)
    monkeypatch.setenv("POC_DB_PATH", str(db))
    res = runner.invoke(app, ["report", "costs", "--by", "purpose"])
    assert res.exit_code == 0
    assert "router" in res.stdout
    assert "answer" in res.stdout


def test_review_list_e_resolve(tmp_path, monkeypatch) -> None:
    from poc_istruzioni.db.repositories import (
        ConversionRow,
        false_positive_rules,
        get_review,
        upsert_conversion,
    )

    db = tmp_path / "poc.db"
    c = connect(db)
    init_db(c)
    upsert_conversion(c, ConversionRow(
        doc_id="PF1-2026", n=181, route="A", model_used="claude-opus-4-8", escalations=1,
        status="needs_human", reasons="lint: valore con simbolo doppio (es. 1,73%%)",
        md_path="p181.md", usd=0.2, ts="2026-06-07T00:00:00+00:00",
    ))
    c.close()
    monkeypatch.setenv("POC_DB_PATH", str(db))

    # list mostra la pagina pendente
    res = runner.invoke(app, ["review", "list"])
    assert res.exit_code == 0 and "p181" in res.stdout

    # resolve come falso positivo
    res = runner.invoke(
        app,
        ["review", "resolve", "--page", "181", "--action", "falso-positivo",
         "--by", "Samuele", "--note", "%% nella fonte"],
    )
    assert res.exit_code == 0

    c = connect(db)
    rev = get_review(c, "PF1-2026", 181)
    assert rev is not None and rev.azione == "falso_positivo" and rev.revisore == "Samuele"
    assert false_positive_rules(c, "PF1-2026") == {"lint:simbolo_doppio": 1}
    c.close()

    # ora non è più in coda
    res = runner.invoke(app, ["review", "list"])
    assert "Nessuna pagina" in res.stdout


def test_report_costs_dimensione_invalida(tmp_path, monkeypatch) -> None:
    db = tmp_path / "poc.db"
    _seed_db(db)
    monkeypatch.setenv("POC_DB_PATH", str(db))
    res = runner.invoke(app, ["report", "costs", "--by", "pippo"])
    assert res.exit_code != 0
