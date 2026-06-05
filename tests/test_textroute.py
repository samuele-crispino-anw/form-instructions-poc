"""Test della Rotta A: estrazione con indizi font + conversione testo->markdown (mock)."""

from types import SimpleNamespace

import fitz
import pytest

from poc_istruzioni.config import CachePricing, Currency, ModelPrice, Prices
from poc_istruzioni.db.connection import connect, init_db
from poc_istruzioni.ingest.textroute import (
    _span_text,
    convert_text_to_markdown,
    extract_text_with_cues,
)
from poc_istruzioni.llm.client import LlmClient

PRICES = Prices(
    updated="t",
    models={"claude-opus-4-8": ModelPrice(input_per_mtok=5.0, output_per_mtok=25.0)},
    cache=CachePricing(read_multiplier=0.10, write_5m_multiplier=1.25, write_1h_multiplier=2.00),
    currency=Currency(usd_to_eur=0.87),
)


def test_extract_marca_titolo_grande(tmp_path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "QUADRO RP", fontsize=22)  # titolo grande
    page.insert_text((72, 110), "testo del corpo normale", fontsize=10)
    pdf = tmp_path / "d.pdf"
    doc.save(str(pdf))
    doc.close()

    text = extract_text_with_cues(fitz.open(pdf)[0])
    lines = text.splitlines()
    assert any(line.startswith("〖H〗 ") and "QUADRO RP" in line for line in lines)
    assert any(line == "testo del corpo normale" for line in lines)


def test_span_text_mappa_dingbat() -> None:
    assert _span_text({"text": "n", "font": "ZapfDingbats"}) == "-"
    assert _span_text({"text": "normale", "font": "Times"}) == "normale"


def test_extract_strip_boilerplate_e_numero_pagina(tmp_path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Header ripetuto", fontsize=10)
    page.insert_text((72, 110), "contenuto del corpo", fontsize=10)
    page.insert_text((72, 150), "42", fontsize=10)  # numero di pagina orfano
    pdf = tmp_path / "d.pdf"
    doc.save(str(pdf))
    doc.close()

    out = extract_text_with_cues(
        fitz.open(pdf)[0], boilerplate={"Header ripetuto"}, page_number=42
    )
    assert "contenuto del corpo" in out
    assert "Header ripetuto" not in out
    assert "\n42" not in out and out.strip() != "42"


class FakeMessages:
    def __init__(self):
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="## QUADRO RP")],
            usage=SimpleNamespace(input_tokens=800, output_tokens=300,
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


def test_convert_text_to_markdown(conn) -> None:
    fake = FakeAnthropic()
    llm = LlmClient(conn, PRICES, client=fake)
    res = convert_text_to_markdown(
        llm, "〖H〗 QUADRO RP\ntesto", model="claude-opus-4-8", prompt="P", page_n=62
    )
    assert res.text == "## QUADRO RP"
    # il testo estratto è passato come messaggio utente; purpose = spike:routeA
    assert fake.messages.last_kwargs["messages"][0]["content"].startswith("〖H〗 QUADRO RP")
    row = conn.execute("SELECT scopo FROM llm_calls").fetchone()
    assert row["scopo"] == "spike:routeA"
