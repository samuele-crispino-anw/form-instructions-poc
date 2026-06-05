"""Test di LlmClient con SDK Anthropic mockato (nessuna rete).

Verifica: estrazione testo, registrazione nel ledger, costo da usage,
applicazione di cache_control al prefisso di sistema.
"""

from types import SimpleNamespace

import pytest

from poc_istruzioni.config import CachePricing, Currency, ModelPrice, Prices
from poc_istruzioni.db.connection import connect, init_db
from poc_istruzioni.ledger.store import total
from poc_istruzioni.llm.client import LlmClient

PRICES = Prices(
    updated="test",
    models={"claude-haiku-4-5": ModelPrice(input_per_mtok=1.0, output_per_mtok=5.0)},
    cache=CachePricing(read_multiplier=0.10, write_5m_multiplier=1.25, write_1h_multiplier=2.00),
    currency=Currency(usd_to_eur=0.5),
)


class FakeMessages:
    """Registra l'ultimo kwargs e ritorna una risposta finta deterministica."""

    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="text", text="Righi RP1-RP4, "),
                SimpleNamespace(type="text", text="codice 1."),
            ],
            usage=SimpleNamespace(
                input_tokens=1_000_000,
                output_tokens=0,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
        )


class FakeAnthropic:
    def __init__(self) -> None:
        self.messages = FakeMessages()


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "c.db")
    init_db(c)
    yield c
    c.close()


def test_complete_estrae_testo_e_registra(conn) -> None:
    fake = FakeAnthropic()
    client = LlmClient(conn, PRICES, client=fake)

    res = client.complete(
        scopo="router",
        model="claude-haiku-4-5",
        messages=[{"role": "user", "content": "dove indico le spese sanitarie?"}],
        system="Sei un assistente fiscale.",
    )

    assert res.text == "Righi RP1-RP4, codice 1."
    # 1M token input a 1/Mtok = 1.0 USD; eur = 0.5
    assert res.cost.usd == pytest.approx(1.0)
    assert res.cost.eur == pytest.approx(0.5)
    # registrata nel ledger
    t = total(conn)
    assert t.calls == 1
    assert t.usd == pytest.approx(1.0)
    assert res.call_id > 0


def test_cache_control_su_system_5m(conn) -> None:
    fake = FakeAnthropic()
    client = LlmClient(conn, PRICES, client=fake)
    client.complete(
        scopo="answer",
        model="claude-haiku-4-5",
        messages=[{"role": "user", "content": "x"}],
        system="prefisso fisso",
    )
    system_param = fake.messages.last_kwargs["system"]
    assert system_param[-1]["cache_control"] == {"type": "ephemeral"}
    assert system_param[-1]["text"] == "prefisso fisso"


def test_cache_control_1h(conn) -> None:
    fake = FakeAnthropic()
    client = LlmClient(conn, PRICES, client=fake)
    client.complete(
        scopo="answer",
        model="claude-haiku-4-5",
        messages=[{"role": "user", "content": "x"}],
        system="prefisso",
        cache_ttl="1h",
    )
    cc = fake.messages.last_kwargs["system"][-1]["cache_control"]
    assert cc == {"type": "ephemeral", "ttl": "1h"}


def test_senza_system_non_passa_il_parametro(conn) -> None:
    fake = FakeAnthropic()
    client = LlmClient(conn, PRICES, client=fake)
    client.complete(
        scopo="answer",
        model="claude-haiku-4-5",
        messages=[{"role": "user", "content": "x"}],
    )
    assert "system" not in fake.messages.last_kwargs


def test_cache_ttl_invalido_solleva(conn) -> None:
    client = LlmClient(conn, PRICES, client=FakeAnthropic())
    with pytest.raises(ValueError):
        client.complete(
            scopo="answer",
            model="claude-haiku-4-5",
            messages=[{"role": "user", "content": "x"}],
            system="p",
            cache_ttl="2h",
        )
