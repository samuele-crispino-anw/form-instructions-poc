"""Calcolo del costo di una chiamata LLM dai token (FR-T2).

Il costo è derivato dai token reali e dalle tariffe di prices.toml, mai stimato.
Costo nativo in USD (valuta di fatturazione Anthropic) + conversione in EUR configurabile.
"""

from __future__ import annotations

from dataclasses import dataclass

from poc_istruzioni.config import Prices
from poc_istruzioni.llm.types import Usage

_PER_MTOK = 1_000_000


@dataclass(frozen=True)
class Cost:
    usd: float
    eur: float


def _write_multiplier(prices: Prices, cache_ttl: str) -> float:
    if cache_ttl == "5m":
        return prices.cache.write_5m_multiplier
    if cache_ttl == "1h":
        return prices.cache.write_1h_multiplier
    raise ValueError(f"cache_ttl non valido: {cache_ttl!r} (atteso '5m' o '1h')")


def compute_cost(
    usage: Usage,
    model_id: str,
    prices: Prices,
    *,
    cache_ttl: str = "5m",
    usd_to_eur: float | None = None,
) -> Cost:
    """Costo della chiamata. `usd_to_eur` sovrascrive il tasso di config se passato."""
    mp = prices.for_model(model_id)
    read_mult = prices.cache.read_multiplier
    write_mult = _write_multiplier(prices, cache_ttl)

    usd = (
        usage.input_tokens * mp.input_per_mtok
        + usage.cache_read_input_tokens * mp.input_per_mtok * read_mult
        + usage.cache_creation_input_tokens * mp.input_per_mtok * write_mult
        + usage.output_tokens * mp.output_per_mtok
    ) / _PER_MTOK

    rate = usd_to_eur if usd_to_eur is not None else prices.currency.usd_to_eur
    return Cost(usd=usd, eur=usd * rate)
