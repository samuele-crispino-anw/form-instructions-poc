"""D2 — riassunti scope-aware dei nodi: etichette di NAVIGAZIONE, non fatti.

Passo deterministico (questo modulo, senza LLM): per ogni nodo costruisce l'INPUT su cui poi
genererà il riassunto. Scope-aware = ogni livello alla sua scala:
- nodo-ramo (ha figli):  titolo + titoli dei FIGLI DIRETTI (il router naviga per figli);
- nodo-foglia (no figli): testo markdown delle sue pagine (de-ifenato, troncabile).

Tenere l'input minimale e alla giusta scala evita che il riassunto di un quadro ricopi ogni
rigo e mantiene basso il costo della compilazione one-shot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from poc_istruzioni.ingest.checks import dehyphenate
from poc_istruzioni.serving.nodes import _FRONTMATTER_RE, Node

if TYPE_CHECKING:
    from poc_istruzioni.llm.client import LlmClient, LlmResult


@dataclass
class ScopeInput:
    """Input scope-aware per generare il riassunto di un nodo."""

    node_id: int
    kind: str
    title: str
    is_leaf: bool
    child_titles: list[str]
    own_text: str  # testo proprio (solo per le foglie); "" per i rami


def _page_text(md_by_page: dict[int, str], start: int, end: int) -> str:
    """Concatena il markdown delle pagine [start, end], togliendo frontmatter e sillabazione."""
    parts = []
    for p in range(start, end + 1):
        raw = md_by_page.get(p)
        if raw:
            parts.append(_FRONTMATTER_RE.sub("", raw).strip())
    return dehyphenate("\n\n".join(parts))


def build_scope_inputs(
    nodes: list[Node], md_by_page: dict[int, str], *, max_own_chars: int = 6000
) -> list[ScopeInput]:
    """Per ogni nodo: figli diretti (rami) oppure testo delle pagine (foglie)."""
    children: dict[int, list[Node]] = {}
    for n in nodes:
        if n.parent_id is not None:
            children.setdefault(n.parent_id, []).append(n)

    out: list[ScopeInput] = []
    for n in nodes:
        kids = children.get(n.id, [])
        is_leaf = not kids
        own = ""
        if is_leaf:
            own = _page_text(md_by_page, n.page_start, n.page_end)
            if max_own_chars and len(own) > max_own_chars:
                own = own[:max_own_chars]
        out.append(
            ScopeInput(
                node_id=n.id,
                kind=n.kind,
                title=n.title,
                is_leaf=is_leaf,
                child_titles=[c.title for c in kids],
                own_text=own,
            )
        )
    return out


def build_user_message(scope: ScopeInput) -> str:
    """Messaggio utente per l'LLM: titolo + (figli per i rami | testo per le foglie)."""
    lines = [f"Tipo voce: {scope.kind}", f"Titolo: {scope.title}"]
    if scope.is_leaf:
        lines += ["", "Testo della voce:", scope.own_text or "(nessun testo estratto)"]
    else:
        lines += ["", "Sotto-voci contenute (figli diretti):"]
        lines += [f"- {t}" for t in scope.child_titles]
    return "\n".join(lines)


def generate_summary(
    client: LlmClient, scope: ScopeInput, *, model: str, system_prompt: str
) -> tuple[str, LlmResult]:
    """Genera l'etichetta di navigazione di un nodo (testo semplice)."""
    res = client.complete(
        scopo=f"summary:node{scope.node_id}",
        model=model,
        system=system_prompt,
        messages=[{"role": "user", "content": build_user_message(scope)}],
        max_tokens=300,
    )
    return res.text.strip(), res
