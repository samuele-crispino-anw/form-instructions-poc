"""Test estrazione/validazione identità documentale (B.5), in mock."""

import json
from types import SimpleNamespace

import pytest

from poc_istruzioni.config import CachePricing, Currency, ModelPrice, Prices
from poc_istruzioni.db.connection import connect, init_db
from poc_istruzioni.ingest.identity import IdentityRecord, extract_identity, validate_identity
from poc_istruzioni.llm.client import LlmClient

PRICES = Prices(
    updated="t",
    models={"claude-opus-4-8": ModelPrice(input_per_mtok=5.0, output_per_mtok=25.0)},
    cache=CachePricing(read_multiplier=0.10, write_5m_multiplier=1.25, write_1h_multiplier=2.00),
    currency=Currency(usd_to_eur=0.87),
)

IDENTITY_JSON = json.dumps(
    {
        "modello": "REDDITI PERSONE FISICHE — Fascicolo 1",
        "edizione": "2026",
        "periodo_imposta": "2025",
        "agg_data": "2026-05-13",
    }
)


class FakeMessages:
    def __init__(self):
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=IDENTITY_JSON)],
            usage=SimpleNamespace(
                input_tokens=1500, output_tokens=40,
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


def test_extract_identity_parsa_json(conn, tmp_path) -> None:
    img = tmp_path / "p001.png"
    img.write_bytes(b"\x89PNGFAKE")
    fake = FakeAnthropic()
    rec, res = extract_identity(
        LlmClient(conn, PRICES, client=fake), img, model="claude-opus-4-8", prompt="P"
    )
    assert rec.edizione == "2026"
    assert rec.periodo_imposta == "2025"
    assert "PERSONE FISICHE" in rec.modello
    # structured output: lo schema json_schema è passato all'API
    assert fake.messages.last_kwargs["output_config"]["format"]["type"] == "json_schema"
    assert res.cost.usd > 0


def test_validate_identity_ok() -> None:
    rec = IdentityRecord("REDDITI PERSONE FISICHE", "2026", "2025", "2026-05-13")
    issues = validate_identity(
        rec, expected_edizione="2026", expected_periodo="2025", expected_modello_hint="REDDITI"
    )
    assert issues == []


def test_validate_identity_mismatch() -> None:
    rec = IdentityRecord("REDDITI PERSONE FISICHE", "2025", "2024", "")
    issues = validate_identity(rec, expected_edizione="2026", expected_periodo="2025")
    assert len(issues) == 2  # edizione e periodo sbagliati
    assert any("edizione" in i for i in issues)
    assert any("periodo_imposta" in i for i in issues)
