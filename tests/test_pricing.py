"""Test del calcolo costo: tariffe sintetiche per controllare i numeri al centesimo."""

from types import SimpleNamespace

import pytest

from poc_istruzioni.config import CachePricing, Currency, ModelPrice, Prices
from poc_istruzioni.llm.pricing import compute_cost
from poc_istruzioni.llm.types import Usage

# Prices sintetico: input 5/Mtok, output 25/Mtok, read 0.1x,
# write 1.25x(5m)/2x(1h), 1 USD = 0.5 EUR.
PRICES = Prices(
    updated="test",
    models={"m": ModelPrice(input_per_mtok=5.0, output_per_mtok=25.0)},
    cache=CachePricing(read_multiplier=0.10, write_5m_multiplier=1.25, write_1h_multiplier=2.00),
    currency=Currency(usd_to_eur=0.5),
)


def test_input_a_prezzo_pieno() -> None:
    cost = compute_cost(Usage(input_tokens=1_000_000), "m", PRICES)
    assert cost.usd == 5.0
    assert cost.eur == 2.5  # 5.0 * 0.5


def test_output_a_prezzo_pieno() -> None:
    assert compute_cost(Usage(output_tokens=1_000_000), "m", PRICES).usd == 25.0


def test_cache_read_scontato() -> None:
    # 1M token letti da cache a 5/Mtok * 0.1 = 0.5 USD
    assert compute_cost(Usage(cache_read_input_tokens=1_000_000), "m", PRICES).usd == 0.5


def test_cache_write_5m_e_1h() -> None:
    u = Usage(cache_creation_input_tokens=1_000_000)
    assert compute_cost(u, "m", PRICES, cache_ttl="5m").usd == 6.25  # 5 * 1.25
    assert compute_cost(u, "m", PRICES, cache_ttl="1h").usd == 10.0  # 5 * 2.0


def test_combinazione() -> None:
    u = Usage(
        input_tokens=200_000,
        output_tokens=10_000,
        cache_read_input_tokens=800_000,
    )
    # (200k*5 + 800k*5*0.1 + 10k*25) / 1e6 = (1_000_000 + 400_000 + 250_000)/1e6 = 1.65
    assert compute_cost(u, "m", PRICES).usd == pytest.approx(1.65)


def test_override_tasso_eur() -> None:
    cost = compute_cost(Usage(input_tokens=1_000_000), "m", PRICES, usd_to_eur=1.0)
    assert cost.eur == 5.0


def test_ttl_non_valido_solleva() -> None:
    with pytest.raises(ValueError):
        compute_cost(Usage(input_tokens=1), "m", PRICES, cache_ttl="2h")


def test_usage_from_anthropic_gestisce_none() -> None:
    raw = SimpleNamespace(
        input_tokens=100,
        output_tokens=20,
        cache_read_input_tokens=None,  # campo assente/None -> 0
        cache_creation_input_tokens=5,
    )
    u = Usage.from_anthropic(raw)
    assert (u.input_tokens, u.output_tokens) == (100, 20)
    assert u.cache_read_input_tokens == 0
    assert u.cache_creation_input_tokens == 5
