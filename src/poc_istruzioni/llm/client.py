"""LlmClient: unico punto di accesso ai modelli Anthropic (FR-T2).

Ogni chiamata passa di qui e viene registrata nel ledger con token e costo.
Il prefisso di sistema riceve cache_control per il prompt caching (FR-B5); resta
responsabilità del chiamante mantenere il prefisso byte-identico tra chiamate.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from poc_istruzioni.config import Prices, Settings
from poc_istruzioni.ledger.store import record_call
from poc_istruzioni.llm.pricing import Cost, compute_cost
from poc_istruzioni.llm.types import Usage

_DEFAULT_MAX_TOKENS = 4096


@dataclass(frozen=True)
class LlmResult:
    """Esito di una chiamata: testo, token, costo, id riga ledger, risposta grezza."""

    text: str
    usage: Usage
    cost: Cost
    model: str
    call_id: int
    raw: Any


def _cache_control(cache_ttl: str) -> dict:
    # 5m è il default del provider (ttl omesso); 1h va esplicitato.
    if cache_ttl == "5m":
        return {"type": "ephemeral"}
    if cache_ttl == "1h":
        return {"type": "ephemeral", "ttl": "1h"}
    raise ValueError(f"cache_ttl non valido: {cache_ttl!r} (atteso '5m' o '1h')")


def _extract_text(resp: Any) -> str:
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


class LlmClient:
    def __init__(
        self,
        conn: sqlite3.Connection,
        prices: Prices,
        *,
        client: Any | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._conn = conn
        self._prices = prices
        self._settings = settings
        if client is None:
            import anthropic  # import pigro: non richiede API key finché non si chiama

            client = anthropic.Anthropic()
        self._client = client

    def _build_system(self, system: str | list[dict], cache_ttl: str) -> list[dict]:
        """Avvolge il system in blocchi testo con cache_control sull'ultimo blocco."""
        cc = _cache_control(cache_ttl)
        if isinstance(system, str):
            return [{"type": "text", "text": system, "cache_control": cc}]
        blocks = [dict(b) for b in system]
        if blocks:
            blocks[-1] = {**blocks[-1], "cache_control": cc}
        return blocks

    def complete(
        self,
        *,
        scopo: str,
        model: str,
        messages: list[dict],
        system: str | list[dict] | None = None,
        max_tokens: int | None = None,
        cache_ttl: str = "5m",
        cache_system: bool = True,
        query_id: str | None = None,
        **extra: Any,
    ) -> LlmResult:
        """Esegue una chiamata, la registra nel ledger e ne ritorna l'esito."""
        if max_tokens is None:
            max_tokens = self._settings.llm.max_tokens if self._settings else _DEFAULT_MAX_TOKENS

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            **extra,
        }
        if system is not None:
            kwargs["system"] = (
                self._build_system(system, cache_ttl) if cache_system else system
            )

        resp = self._client.messages.create(**kwargs)

        usage = Usage.from_anthropic(resp.usage)
        cost = compute_cost(usage, model, self._prices, cache_ttl=cache_ttl)
        call_id = record_call(
            self._conn, scopo=scopo, modello=model, usage=usage, cost=cost, query_id=query_id
        )
        return LlmResult(
            text=_extract_text(resp),
            usage=usage,
            cost=cost,
            model=model,
            call_id=call_id,
            raw=resp,
        )
