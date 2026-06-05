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


def test_report_costs_dimensione_invalida(tmp_path, monkeypatch) -> None:
    db = tmp_path / "poc.db"
    _seed_db(db)
    monkeypatch.setenv("POC_DB_PATH", str(db))
    res = runner.invoke(app, ["report", "costs", "--by", "pippo"])
    assert res.exit_code != 0
