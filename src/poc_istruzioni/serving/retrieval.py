"""D-orchestrazione — retrieval a due velocità: fast-path D3 -> gate -> navigazione-LLM -> pin.

Logica pura (gate, assembly) testabile senza IO; la navigazione-LLM è l'unico passo a costo token,
e scatta solo quando il gate non è "netto". Il contesto servito = regole governanti (pin) + voce.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from poc_istruzioni.llm.client import LlmClient, LlmResult
    from poc_istruzioni.serving.pins import Pin


@dataclass
class RetrievalResult:
    """Esito del retrieval: voce scelta, metodo, pin nello scope, contesto servito, trace."""

    query: str
    gate: str            # netto | ambiguo | vuoto
    reason: str
    method: str          # fast_path | navigation_llm | refused
    target_node_id: int | None
    candidates: list[tuple[int, float]]
    target_title: str = ""
    target_pages: str = ""
    pins: list = field(default_factory=list)      # list[Pin] ereditati nello scope
    served_text: str = ""
    cost_usd: float = 0.0

    @property
    def pin_owners(self) -> list[int]:
        return [p.owner_node_id for p in self.pins]


def classify_fastpath(
    ranked: list[tuple[int, float]], *, min_abs: float, margin: float
) -> tuple[str, str]:
    """Gate: 'netto' (servi dal fast-path), 'ambiguo' (escala a LLM), 'vuoto' (nessun match)."""
    if not ranked:
        return "vuoto", "nessun match lessicale"
    top1 = ranked[0][1]
    top2 = ranked[1][1] if len(ranked) > 1 else 0.0
    if top1 < min_abs:
        return "ambiguo", f"top1 {top1:.1f} < soglia_assoluta {min_abs}"
    if top2 > 0 and top1 < margin * top2:
        return "ambiguo", f"margine {top1 / top2:.2f}x < {margin}x (top2 vicino)"
    margine = "inf" if top2 == 0 else f"{top1 / top2:.2f}x"
    return "netto", f"top1 {top1:.1f}, margine {margine}"


def served_page_range(
    page_start: int, page_end: int, node_starts: list[int]
) -> tuple[int, int]:
    """Range di pagine da SERVIRE per una foglia: estende fino all'inizio del nodo successivo.

    Il contenuto di un rigo può proseguire sulla pagina dove inizia il rigo seguente (heading e
    coda condividono la pagina): servire fino a quella pagina inclusa evita di troncare la risposta.
    Il range del nodo (per display/navigazione) resta invariato; cambia solo cosa si serve.
    """
    later = [p for p in node_starts if p > page_start]
    return (page_start, min(later) if later else page_end)


def build_served_context(target_title: str, target_text: str, pins: list[Pin]) -> str:
    """Assembla il contesto da servire: prima le regole governanti (pin), poi la voce."""
    parts: list[str] = []
    if pins:
        parts.append("=== REGOLE GOVERNANTI (ereditate dallo scope superiore) ===")
        for p in pins:
            parts.append(f"[{p.owner_kind}] {p.owner_title}\n{p.text}")
    parts.append(f"=== VOCE ===\n{target_title}\n{target_text}")
    return "\n\n".join(parts)


def navigate_hierarchical(
    client: LlmClient,
    query: str,
    nodes: list,
    summaries: dict[int, str],
    *,
    model: str,
    system_prompt: str,
    max_depth: int = 6,
) -> tuple[int | None, float, list[int]]:
    """Naviga l'albero dall'alto: a ogni livello l'LLM sceglie in quale figlio scendere.

    Decoupled dal fast-path lessicale: l'LLM vede i summary dei figli del nodo corrente e risponde
    col numero del figlio, FERMA (la voce corrente è quella giusta) o NESSUNA (rifiuta).
    Ritorna (node_id scelto | None, costo_usd, percorso). Con un solo figlio scende senza LLM.
    """
    by_id = {n.id: n for n in nodes}
    children: dict[int | None, list] = {}
    for n in nodes:
        children.setdefault(n.parent_id, []).append(n)

    current = None
    cost = 0.0
    path: list[int] = []
    for _ in range(max_depth):
        kids = children.get(current.id if current else None, [])
        if not kids:
            break  # foglia raggiunta
        if len(kids) == 1:  # unica discesa possibile: scendi senza spendere un LLM
            current = kids[0]
            path.append(current.id)
            continue
        listing = "\n".join(
            f"[{k.id}] ({k.kind}) {k.title}\n    {summaries.get(k.id) or ''}" for k in kids
        )
        user = (
            f"Domanda: {query}\n\nVoce corrente: {current.title if current else '(radice)'}\n\n"
            f"Sotto-voci:\n{listing}\n\nScendi nella sotto-voce più pertinente (rispondi col suo "
            "numero), oppure FERMA se la voce corrente è già quella giusta, oppure NESSUNA se "
            "nessuna è pertinente."
        )
        res = client.complete(
            scopo="router:descent", model=model, system=system_prompt,
            messages=[{"role": "user", "content": user}], max_tokens=12,
        )
        cost += res.cost.usd
        text = res.text.upper()
        if "NESSUNA" in text:
            return None, cost, path
        if "FERMA" in text:
            return (current.id if current else None), cost, path
        m = re.search(r"\d+", res.text)
        nid = int(m.group()) if m else None
        if nid is None or nid not in {k.id for k in kids}:
            return (current.id if current else None), cost, path
        current = by_id[nid]
        path.append(nid)
    return (current.id if current else None), cost, path


def navigate_llm(
    query: str,
    candidates: list[tuple[int, str, str, str]],
    client: LlmClient,
    *,
    model: str,
    system_prompt: str,
) -> tuple[int | None, LlmResult]:
    """Disambigua tra i candidati (id, kind, title, summary) coi summary: ritorna l'id scelto."""
    lines = [f"[{nid}] ({kind}) {title}\n    {summary}" for nid, kind, title, summary in candidates]
    user = (
        f"Domanda dell'utente: {query}\n\nVoci candidate:\n" + "\n".join(lines)
        + "\n\nRispondi SOLO con il numero tra parentesi della voce più pertinente, "
        "oppure 'nessuna' se nessuna risponde alla domanda."
    )
    res = client.complete(
        scopo="router:nav", model=model, system=system_prompt,
        messages=[{"role": "user", "content": user}], max_tokens=16,
    )
    m = re.search(r"\d+", res.text)
    chosen = int(m.group()) if m else None
    valid = {c[0] for c in candidates}
    return (chosen if chosen in valid else None), res
