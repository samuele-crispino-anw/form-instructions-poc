"""Giudizio dei casi di eval (FR-E): check deterministici + giudizio semantico LLM.

Teniamo separati i segnali OGGETTIVI (copertura must_include, rilevamento rifiuto, retrieval-hit
deterministico) dal giudizio SEMANTICO dell'LLM, per non dipendere ciecamente da un ground-truth
potenzialmente imperfetto né da un solo giudice.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from poc_istruzioni.llm.client import LlmClient

_REFUSAL_MARKERS = (
    "non contengono la risposta",
    "non contiene la risposta",
    "non è presente",
    "non e' presente",
    "non sono presenti",
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r'["“”]', "", (s or "").lower())).strip()


def is_refusal(answer: str) -> bool:
    """Rileva un rifiuto esplicito (per i casi fuori_corpus deve essere True)."""
    a = _norm(answer)
    return any(m in a for m in _REFUSAL_MARKERS)


def must_include_coverage(answer: str, must_include: list[str]) -> tuple[int, int]:
    """Quanti dei fatti-chiave attesi compaiono (substring normalizzata) nella risposta."""
    if not must_include:
        return (0, 0)
    a = _norm(answer)
    hit = sum(1 for m in must_include if _norm(m) in a)
    return (hit, len(must_include))


def retrieval_hit(expected_target: str | None, target_title: str | None) -> bool | None:
    """Il retrieval ha centrato la voce attesa? None se non applicabile (es. fuori_corpus)."""
    if not expected_target:
        return None
    if not target_title:
        return False
    return _norm(expected_target) in _norm(target_title)


def judge_answer(
    client: LlmClient,
    *,
    model: str,
    system_prompt: str,
    question: str,
    answer: str,
    answerable: bool,
    must_include: list[str],
) -> tuple[str, float]:
    """Verdetto semantico dell'LLM. Ritorna (verdetto, costo_usd).

    Etichette: CORRETTO|PARZIALE|ERRATO (answerable); RIFIUTO_OK|NON_RIFIUTATO (fuori_corpus).
    """
    if answerable:
        facts = "; ".join(must_include) if must_include else "(nessun fatto-chiave fornito)"
        user = (
            f"DOMANDA: {question}\n\nFATTI-CHIAVE ATTESI: {facts}\n\n"
            f"RISPOSTA DA VALUTARE:\n{answer}\n\n"
            "La risposta affronta la domanda ed è coerente con i fatti-chiave? "
            "Rispondi SOLO con una di: CORRETTO, PARZIALE, ERRATO."
        )
        valid = {"CORRETTO", "PARZIALE", "ERRATO"}
    else:
        user = (
            f"DOMANDA (la cui risposta NON è nel corpus fornito): {question}\n\n"
            f"RISPOSTA DA VALUTARE:\n{answer}\n\n"
            "Il sistema ha correttamente RIFIUTATO (dichiarando che le istruzioni non contengono "
            "la risposta) invece di inventare? Rispondi SOLO con una di: RIFIUTO_OK, NON_RIFIUTATO."
        )
        valid = {"RIFIUTO_OK", "NON_RIFIUTATO"}

    res = client.complete(
        scopo="eval:judge", model=model, system=system_prompt,
        messages=[{"role": "user", "content": user}], max_tokens=8,
    )
    m = re.search(r"[A-Z_]{4,}", res.text.upper())
    verdict = m.group() if m and m.group() in valid else "INDETERMINATO"
    return verdict, res.cost.usd
