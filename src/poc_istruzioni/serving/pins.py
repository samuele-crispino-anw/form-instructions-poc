"""D2.5 — pinning delle regole governanti (deterministico).

Una regola governante vive nel PREAMBOLO di un nodo-ramo (quadro/sezione): il testo tra il suo
heading e il primo heading strutturale successivo. Vale per tutto il sottoalbero del ramo. A
serve-time, dato un nodo foglia, si "pinano" i preamboli degli ANTENATI nello scope.
"""

from __future__ import annotations

from dataclasses import dataclass

from poc_istruzioni.ingest.checks import dehyphenate
from poc_istruzioni.serving.nodes import _FRONTMATTER_RE, _HEADING_RE, Node, classify_heading


@dataclass(frozen=True)
class Pin:
    """Regola governante ancorata al ramo che la contiene (owner)."""

    owner_node_id: int
    owner_kind: str
    owner_title: str
    text: str


def extract_preamble(node: Node, md_by_page: dict[int, str], *, max_chars: int = 4000) -> str:
    """Testo tra l'heading del ramo e il primo heading STRUTTURALE successivo (de-ifenato)."""
    collected: list[str] = []
    started = False
    for p in range(node.page_start, node.page_end + 1):
        body = md_by_page.get(p)
        if body is None:
            continue
        for line in _FRONTMATTER_RE.sub("", body).splitlines():
            m = _HEADING_RE.match(line)
            if m:
                title = m.group(1).strip()
                if not started:
                    started = title == node.title.strip()  # parte DOPO l'heading del ramo
                    continue
                if classify_heading(title) is not None:  # prossimo marcatore strutturale -> stop
                    text = dehyphenate("\n".join(collected)).strip()
                    return text[:max_chars]
                collected.append(title)  # heading non-strutturale: è contenuto del preambolo
            elif started:
                collected.append(line)
    return dehyphenate("\n".join(collected)).strip()[:max_chars]


def build_pins(nodes: list[Node], md_by_page: dict[int, str]) -> list[Pin]:
    """Un pin per ogni nodo-ramo con preambolo non vuoto (potenziali regole governanti)."""
    has_children = {n.parent_id for n in nodes if n.parent_id is not None}
    pins: list[Pin] = []
    for n in nodes:
        if n.id not in has_children:  # solo i rami hanno un preambolo che governa i figli
            continue
        text = extract_preamble(n, md_by_page)
        if text:
            pins.append(Pin(owner_node_id=n.id, owner_kind=n.kind, owner_title=n.title, text=text))
    return pins


def collect_pins(target_node_id: int, nodes: list[Node], pins: list[Pin]) -> list[Pin]:
    """Pin degli ANTENATI del nodo target, ordinati dalla radice in giù (scope decrescente)."""
    parent_of = {n.id: n.parent_id for n in nodes}
    by_owner = {p.owner_node_id: p for p in pins}
    chain: list[int] = []
    cur = parent_of.get(target_node_id)
    while cur is not None:
        chain.append(cur)
        cur = parent_of.get(cur)
    chain.reverse()  # radice -> padre diretto
    return [by_owner[nid] for nid in chain if nid in by_owner]
