"""Test della catena di escalation per pagina (convert_page), in mock."""

from types import SimpleNamespace

import pytest

from poc_istruzioni.config import (
    CachePricing,
    Currency,
    ModelPrice,
    Prices,
    load_settings,
)
from poc_istruzioni.db.connection import connect, init_db
from poc_istruzioni.ingest.convert import convert_page
from poc_istruzioni.llm.client import LlmClient

SETTINGS = load_settings()  # usa la config reale (tier e catena)

PRICES = Prices(
    updated="t",
    models={
        "claude-haiku-4-5": ModelPrice(input_per_mtok=1.0, output_per_mtok=5.0),
        "claude-opus-4-8": ModelPrice(input_per_mtok=5.0, output_per_mtok=25.0),
    },
    cache=CachePricing(read_multiplier=0.10, write_5m_multiplier=1.25, write_1h_multiplier=2.00),
    currency=Currency(usd_to_eur=0.87),
)

REF = "codice 1 franchigia 129,11 spese sanitarie detrazione"
GOOD = "## QUADRO RP\ncodice 1 franchigia 129,11 spese sanitarie detrazione"
BAD = "## QUADRO RP\ncodice 1 spese sanitarie detrazione"  # manca 129,11 -> gate boccia


def _usage():
    return SimpleNamespace(
        input_tokens=500, output_tokens=200,
        cache_read_input_tokens=0, cache_creation_input_tokens=0,
    )


class ByModel:
    """create() ritorna GOOD per Opus, BAD per Haiku (simula escalation che ripara)."""

    def create(self, **kw):
        text = GOOD if "opus" in kw["model"] else BAD
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], usage=_usage())


class Always:
    def __init__(self, text):
        self.text = text

    def create(self, **kw):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.text)], usage=_usage()
        )


def _fake(messages):
    return SimpleNamespace(messages=messages)


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "c.db")
    init_db(c)
    yield c
    c.close()


def _call(conn, client, route, tmp_path, force_strong=False):
    img = tmp_path / "p001.png"
    img.write_bytes(b"\x89PNGFAKE")
    return convert_page(
        LlmClient(conn, PRICES, client=client),
        route=route, page_n=1, cues_text="dummy", image_path=img, ref_text=REF,
        settings=SETTINGS, prompt_text="PA", prompt_vision="PB",
        boilerplate=frozenset(), force_strong=force_strong,
    )


def test_haiku_passa_subito(conn, tmp_path) -> None:
    out = _call(conn, _fake(Always(GOOD)), "A", tmp_path)
    assert out.status == "ok"
    assert out.escalations == 0
    assert "haiku" in out.model_used


def test_escalation_haiku_a_opus(conn, tmp_path) -> None:
    out = _call(conn, _fake(ByModel()), "A", tmp_path)
    assert out.status == "ok"
    assert out.escalations == 1  # Haiku fallita, Opus ripara
    assert "opus" in out.model_used


def test_force_strong_parte_da_opus(conn, tmp_path) -> None:
    out = _call(conn, _fake(ByModel()), "A", tmp_path, force_strong=True)
    assert out.status == "ok"
    assert out.escalations == 0  # parte già forte (circuit breaker)
    assert "opus" in out.model_used


def test_tutto_fallisce_needs_human(conn, tmp_path) -> None:
    out = _call(conn, _fake(Always(BAD)), "A", tmp_path)
    assert out.status == "needs_human"
    assert out.escalations == 2  # haiku -> opus -> vlm, tutti falliti
    assert out.reasons  # motivi dell'ultimo tentativo


def test_route_b_usa_vlm(conn, tmp_path) -> None:
    out = _call(conn, _fake(Always(GOOD)), "B", tmp_path)
    assert out.status == "ok"
    assert out.route == "B"
    assert out.escalations == 0
