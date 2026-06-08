"""D3 — keyword index: fast-path deterministico del retrieval (nessun LLM).

Costruisce un indice termine->nodi pesato (tf-per-fonte x idf) da titoli e summary, e risolve una
query utente in nodi candidati ordinati. Gli alias (config) espandono la query per colmare il gap
di vocabolario utente/documento (es. "dentista" -> "spese sanitarie").
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

# Stopword: comuni IT + marcatori strutturali (troppo generici per discriminare un nodo).
_STOPWORDS = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "a", "da", "in", "con", "su",
    "per", "tra", "fra", "del", "dello", "della", "dei", "degli", "delle", "al", "allo", "alla",
    "ai", "agli", "alle", "dal", "dalla", "nel", "nella", "nei", "negli", "sul", "sulla", "e",
    "ed", "o", "od", "che", "non", "si", "se", "come", "anche", "quali", "quale", "cui", "ad",
    "rigo", "righi", "codice", "codici", "quadro", "sezione", "sezioni", "colonna", "colonne",
}
_WORD_RE = re.compile(r"[a-z0-9]+")


def normalize(text: str) -> str:
    """Minuscole, accenti rimossi (società->societa), tutto il resto a spazio."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text


def tokens(text: str, *, bigrams: bool = True) -> list[str]:
    """Unigrammi (no stopword) + bigrammi di parole adiacenti non-stopword."""
    words = _WORD_RE.findall(normalize(text))
    uni = [w for w in words if w not in _STOPWORDS and len(w) > 2]
    out = list(uni)
    if bigrams:
        for a, b in zip(uni, uni[1:], strict=False):
            out.append(f"{a} {b}")
    return out


@dataclass(frozen=True)
class IndexEntry:
    """Una voce dell'indice: il termine punta a un nodo con un peso."""

    term: str
    node_id: int
    weight: float


def build_index(
    items: list[tuple[int, str, str]], *, title_weight: float = 3.0, summary_weight: float = 1.0
) -> list[IndexEntry]:
    """items = (node_id, title, summary). Peso = (tf titolo*w + tf summary*w) x idf."""
    # tf grezza per (term, node) separando le due fonti
    tf: dict[tuple[str, int], float] = defaultdict(float)
    df: dict[str, set[int]] = defaultdict(set)
    for node_id, title, summary in items:
        for t in tokens(title or ""):
            tf[(t, node_id)] += title_weight
            df[t].add(node_id)
        for t in tokens(summary or ""):
            tf[(t, node_id)] += summary_weight
            df[t].add(node_id)

    n_docs = len({nid for _, nid in tf})
    entries: list[IndexEntry] = []
    for (term, node_id), raw in tf.items():
        # idf "smussato": termine in pochi nodi -> idf alto -> instrada con precisione.
        idf = math.log((1 + n_docs) / (1 + len(df[term]))) + 1.0
        entries.append(IndexEntry(term=term, node_id=node_id, weight=round(raw * idf, 4)))
    return entries


def expand_query(query: str, aliases: dict[str, list[str]]) -> list[str]:
    """Token della query + token delle espansioni-alias che vi compaiono (gap di vocabolario)."""
    qn = normalize(query)
    terms = tokens(query)
    for alias, expansions in aliases.items():
        if normalize(alias) in qn:
            for exp in expansions:
                terms.extend(tokens(exp))
    return terms


def score_nodes(
    query: str, entries: list[IndexEntry], aliases: dict[str, list[str]] | None = None
) -> list[tuple[int, float]]:
    """Somma i pesi dei termini della query (espansa) per nodo; ritorna i nodi ordinati."""
    aliases = aliases or {}
    wanted = set(expand_query(query, aliases))
    score: dict[int, float] = defaultdict(float)
    for e in entries:
        if e.term in wanted:
            score[e.node_id] += e.weight
    return sorted(score.items(), key=lambda kv: kv[1], reverse=True)
