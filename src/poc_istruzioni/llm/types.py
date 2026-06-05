"""Tipi dell'accesso LLM: token usage di una chiamata (campi usage dell'API Anthropic)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Usage:
    """Token di una singola chiamata.

    Semantica dei campi usage Anthropic:
    - input_tokens: input NON in cache, a prezzo pieno
    - cache_read_input_tokens: input servito da cache (~0.1x)
    - cache_creation_input_tokens: input scritto in cache (1.25x a 5m, 2x a 1h)
    - output_tokens: output generato
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    @classmethod
    def from_anthropic(cls, usage: Any) -> Usage:
        """Estrae i token dall'oggetto `response.usage` dell'SDK (None -> 0)."""

        def field(name: str) -> int:
            return getattr(usage, name, 0) or 0

        return cls(
            input_tokens=field("input_tokens"),
            output_tokens=field("output_tokens"),
            cache_read_input_tokens=field("cache_read_input_tokens"),
            cache_creation_input_tokens=field("cache_creation_input_tokens"),
        )
