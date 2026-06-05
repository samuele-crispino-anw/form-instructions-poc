"""Test dello spike A vs B: metriche pure + orchestrazione in mock."""

from types import SimpleNamespace

import fitz
import pytest

from poc_istruzioni.config import CachePricing, Currency, ModelPrice, Prices
from poc_istruzioni.db.connection import connect, init_db
from poc_istruzioni.ingest.spike import (
    SpikeRow,
    build_spike_html,
    count_headings,
    run_spike,
    summarize_by_class,
)
from poc_istruzioni.llm.client import LlmClient

PRICES = Prices(
    updated="t",
    models={"claude-opus-4-8": ModelPrice(input_per_mtok=5.0, output_per_mtok=25.0)},
    cache=CachePricing(read_multiplier=0.10, write_5m_multiplier=1.25, write_1h_multiplier=2.00),
    currency=Currency(usd_to_eur=0.87),
)


def test_count_headings() -> None:
    assert count_headings("## QUADRO RP\ntesto\n### Rigo RP1\n- 1 = x") == 2


def test_summarize_by_class() -> None:
    rows = [
        SpikeRow(1, "single_column", 0.9, 1.0, 2, 0.08, 1.0, 0.95, 1.0, 2, 0.10, 2.0),
        SpikeRow(2, "single_column", 0.8, 0.9, 1, 0.06, 1.0, 0.85, 0.9, 1, 0.10, 2.0),
        SpikeRow(3, "table_heavy", 0.5, 0.7, 0, 0.07, 1.0, 0.9, 1.0, 3, 0.12, 2.0),
    ]
    s = summarize_by_class(rows)
    assert s["single_column"]["pages"] == 2
    assert s["single_column"]["overlap_a"] == pytest.approx(0.85)
    assert s["table_heavy"]["overlap_b"] == pytest.approx(0.9)


class FakeMessages:
    def create(self, **kwargs):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="## QUADRO RP\n### Rigo RP1\ncodice 1")],
            usage=SimpleNamespace(input_tokens=800, output_tokens=200,
                                  cache_read_input_tokens=0, cache_creation_input_tokens=0),
        )


class FakeAnthropic:
    def __init__(self):
        self.messages = FakeMessages()


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "c.db")
    init_db(c)
    yield c
    c.close()


def test_run_spike_orchestrazione(conn, tmp_path) -> None:
    # PDF sintetico 1 pagina
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "QUADRO RP codice 1", fontsize=12)
    pdf = tmp_path / "d.pdf"
    doc.save(str(pdf))
    doc.close()

    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "p001.png").write_bytes(b"\x89PNGFAKE")

    rows = run_spike(
        LlmClient(conn, PRICES, client=FakeAnthropic()),
        pdf,
        sample=[1],
        klass_by_page={1: "single_column"},
        ref_texts={1: "QUADRO RP codice 1"},
        pages_dir=pages_dir,
        out_dir=tmp_path / "spike",
        model="claude-opus-4-8",
        prompt_text="PA",
        prompt_vision="PB",
    )
    assert len(rows) == 1
    r = rows[0]
    assert r.klass == "single_column"
    assert r.headings_a == 2 and r.headings_b == 2
    assert r.cost_a > 0 and r.cost_b > 0
    # markdown salvati per entrambe le rotte
    assert (tmp_path / "spike" / "routeA" / "p001.md").exists()
    assert (tmp_path / "spike" / "routeB" / "p001.md").exists()
    # due chiamate nel ledger (routeA + conversion:p001)
    scopi = {row["scopo"] for row in conn.execute("SELECT scopo FROM llm_calls")}
    assert scopi == {"spike:routeA", "conversion:p001"}

    htmlout = build_spike_html(rows, tmp_path / "spike", pages_dir)
    assert "Rotta A" in htmlout and "Rotta B" in htmlout
    assert "data:image/png;base64," in htmlout
