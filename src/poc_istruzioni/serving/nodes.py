"""D1 — albero di navigazione dai pattern STRUTTURALI degli heading (non dai livelli '#').

Il markdown per-pagina ha livelli '#' incoerenti e ripete il titolo-documento; quindi la
gerarchia si ricostruisce riconoscendo i marcatori reali della struttura fiscale
(QUADRO / SEZIONE / Rigo RPn / codice) dal TESTO dell'heading. Deterministico, niente LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Rumore: il titolo-documento ripetuto nel corpo (NON è un nodo).
_DOC_TITLE = re.compile(r"REDDITI\s+PERSONE\s+FISICHE.*ISTRUZIONI", re.I)
# Marcatori strutturali -> (kind, livello canonico). QUADRO/SEZIONE/codice sono ancorati
# all'inizio dell'heading: così "Rigo RP49 ... del Quadro RP" resta un rigo, non un quadro
# (l'header di pagina ripetuto "QUADRO RP ..." inizia invece proprio con QUADRO).
_PATTERNS: list[tuple[re.Pattern[str], str, int]] = [
    (re.compile(r"^\s*(?:\d+\.\s*)?QUADRO\s+[A-Z]{1,2}\b", re.I), "quadro", 1),
    (re.compile(r"^\s*SEZIONE\s+[IVX]+", re.I), "sezione", 2),
    (re.compile(r"\b(?:Rigo|Righi)\b.*\bR[A-Z]\d+", re.I), "rigo", 3),
    (re.compile(r"^\s*codic[ei]\b", re.I), "codice", 4),
]


@dataclass
class Node:
    id: int
    parent_id: int | None
    kind: str
    level: int
    title: str
    page_start: int
    page_end: int
    ord: int


def classify_heading(title: str) -> tuple[str, int] | None:
    """(kind, livello) per un heading strutturale; None se rumore o non-strutturale."""
    t = title.strip()
    if _DOC_TITLE.search(t):
        return None
    for pat, kind, level in _PATTERNS:
        if pat.search(t):
            # quadro/sezione che terminano con ":" sono lead-in di prosa (es. "Sezione III A:
            # righi da RP41 a RP47, nella quale vanno indicate:"), non titoli reali -> ignora.
            if kind in ("quadro", "sezione") and t.endswith(":"):
                return None
            return (kind, level)
    return None  # heading non-strutturale -> contenuto del nodo corrente, non un nodo


_HEADING_RE = re.compile(r"^#{1,6}\s+(.*\S)\s*$")
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.S)


def parse_structural_headings(md_by_page: dict[int, str]) -> list[tuple[int, str, str, int]]:
    """Estrae gli heading strutturali in ordine di pagina: (page, kind, title, level)."""
    out: list[tuple[int, str, str, int]] = []
    for page in sorted(md_by_page):
        body = _FRONTMATTER_RE.sub("", md_by_page[page])
        for line in body.splitlines():
            m = _HEADING_RE.match(line)
            if not m:
                continue
            cls = classify_heading(m.group(1))
            if cls is not None:
                kind, level = cls
                out.append((page, kind, m.group(1).strip(), level))
    return out


def _block_end(pages: list[int]) -> dict[int, int]:
    """Per ogni pagina, l'ultima pagina del suo blocco contiguo (per non oltrepassare i buchi)."""
    pages = sorted(set(pages))
    end: dict[int, int] = {}
    i = 0
    while i < len(pages):
        j = i
        while j + 1 < len(pages) and pages[j + 1] == pages[j] + 1:
            j += 1
        for k in range(i, j + 1):
            end[pages[k]] = pages[j]
        i = j + 1
    return end


def _dedup_key(kind: str, title: str) -> tuple[str, str] | None:
    """Chiave canonica per i marcatori che si ripetono come header di pagina (quadro/sezione).

    Il QUADRO è ripetuto come running-header su ogni pagina: senza deduplica creerebbe un
    nodo radice per pagina, spezzando l'albero. Si tiene solo la PRIMA occorrenza per chiave.
    Righi e codici non si deduplicano (sono contenuto naturalmente unico).
    """
    if kind == "quadro":
        m = re.search(r"QUADRO\s+([A-Z]{1,2})", title, re.I)
        return ("quadro", m.group(1).upper()) if m else ("quadro", title.lower())
    if kind == "sezione":
        m = re.search(r"SEZIONE\s+([IVX]+(?:\s+[A-Z])?)", title, re.I)
        key = m.group(1).upper().replace(" ", "") if m else title.lower()
        return ("sezione", key)
    return None


def build_tree(
    headings: list[tuple[int, str, str, int]], slice_pages: list[int]
) -> list[Node]:
    """Annida gli heading per livello canonico e calcola i range di pagina (clamp al blocco)."""
    block_end = _block_end(slice_pages)
    seen: set[tuple[str, str]] = set()
    deduped: list[tuple[int, str, str, int]] = []
    for h in headings:
        key = _dedup_key(h[1], h[2])
        if key is not None:
            if key in seen:
                continue  # running-header ripetuto -> non è un nuovo nodo
            seen.add(key)
        deduped.append(h)

    nodes: list[Node] = []
    stack: list[Node] = []  # antenati correnti
    for ordn, (page, kind, title, level) in enumerate(deduped, start=1):
        while stack and stack[-1].level >= level:
            stack.pop()
        parent = stack[-1].id if stack else None
        node = Node(
            id=ordn, parent_id=parent, kind=kind, level=level, title=title,
            page_start=page, page_end=page, ord=ordn,
        )
        nodes.append(node)
        stack.append(node)

    # page_end = appena prima del prossimo nodo di livello <= (sibling/antenato), clamp al blocco.
    # I figli (livello maggiore) NON chiudono il nodo: il padre li ingloba fino al fratello dopo.
    for i, n in enumerate(nodes):
        end = block_end.get(n.page_start, n.page_start)
        for m in nodes[i + 1:]:
            if m.level <= n.level:
                # fratello/antenato sulla stessa pagina -> il nodo finisce sulla sua pagina
                end = min(end, m.page_start - 1) if m.page_start > n.page_start else n.page_start
                break
        n.page_end = max(n.page_start, end)
    return nodes


def render_tree(nodes: list[Node]) -> str:
    """Resa testuale ad albero (indentata per livello)."""
    lines = []
    for n in nodes:
        indent = "  " * (n.level - 1)
        lines.append(f"{indent}- [{n.kind}] {n.title}  (p.{n.page_start}-{n.page_end})")
    return "\n".join(lines)
