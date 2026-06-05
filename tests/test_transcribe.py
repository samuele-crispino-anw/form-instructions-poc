"""Test della trascrizione VLM con SDK mockato (nessuna chiamata reale)."""

from types import SimpleNamespace

import pytest

from poc_istruzioni.config import CachePricing, Currency, ModelPrice, Prices
from poc_istruzioni.db.connection import connect, init_db
from poc_istruzioni.ingest.transcribe import transcribe_page
from poc_istruzioni.llm.client import LlmClient

PRICES = Prices(
    updated="test",
    models={"claude-opus-4-8": ModelPrice(input_per_mtok=5.0, output_per_mtok=25.0)},
    cache=CachePricing(read_multiplier=0.10, write_5m_multiplier=1.25, write_1h_multiplier=2.00),
    currency=Currency(usd_to_eur=0.87),
)


class FakeMessages:
    def __init__(self):
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="## QUADRO RP\n### Righi RP1-RP4")],
            usage=SimpleNamespace(
                input_tokens=1500, output_tokens=400,
                cache_read_input_tokens=0, cache_creation_input_tokens=0,
            ),
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


def test_transcribe_invia_immagine_e_ritorna_markdown(conn, tmp_path) -> None:
    img = tmp_path / "p001.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
    fake = FakeAnthropic()
    llm = LlmClient(conn, PRICES, client=fake)

    res = transcribe_page(llm, img, model="claude-opus-4-8", prompt="ISTRUZIONI", page_n=1)

    assert res.text.startswith("## QUADRO RP")
    # il prompt è il system (cachato)
    assert fake.messages.last_kwargs["system"][-1]["text"] == "ISTRUZIONI"
    # nel messaggio utente c'è un blocco immagine base64 png
    content = fake.messages.last_kwargs["messages"][0]["content"]
    image_blocks = [b for b in content if b.get("type") == "image"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["source"]["media_type"] == "image/png"
    assert image_blocks[0]["source"]["data"]  # base64 non vuoto


def test_transcribe_registra_costo_nel_ledger(conn, tmp_path) -> None:
    img = tmp_path / "p001.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
    llm = LlmClient(conn, PRICES, client=FakeAnthropic())
    res = transcribe_page(llm, img, model="claude-opus-4-8", prompt="P", page_n=7)
    # 1500 in *5 + 400 out *25 = 7500+10000 = 17500 / 1e6 = 0.0175 USD
    assert res.cost.usd == pytest.approx(0.0175)
    assert res.usage.output_tokens == 400
