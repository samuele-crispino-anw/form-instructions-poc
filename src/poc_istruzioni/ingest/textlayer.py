"""Estrazione del text-layer del PDF, usata SOLO come riferimento per i check (FR-B2).

Il text-layer non è affidabile per l'ordine di lettura (2 colonne), ma è una seconda
estrazione indipendente utile per il cross-check con l'output del VLM. Header/footer
ripetuti vanno rimossi prima del confronto, altrimenti l'overlap-score si gonfia.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF


def extract_pages_text(pdf_path: Path | str) -> list[str]:
    """Testo grezzo di ogni pagina (indice 0 = pagina 1)."""
    with fitz.open(Path(pdf_path)) as doc:
        return [page.get_text() for page in doc]


def find_boilerplate_lines(pages_text: list[str], *, min_fraction: float = 0.6) -> set[str]:
    """Righe (normalizzate) che ricorrono in almeno `min_fraction` delle pagine.

    Sono gli header/footer ripetuti: si considerano boilerplate da rimuovere.
    """
    if not pages_text:
        return set()
    counts: Counter[str] = Counter()
    for text in pages_text:
        # una riga conta una volta per pagina anche se ripetuta nella pagina
        unique_lines = {ln.strip() for ln in text.splitlines() if ln.strip()}
        counts.update(unique_lines)
    threshold = max(2, int(len(pages_text) * min_fraction))
    return {line for line, c in counts.items() if c >= threshold}


def strip_lines(text: str, boilerplate: set[str]) -> str:
    """Rimuove dalle righe del testo quelle presenti nel set boilerplate."""
    return "\n".join(ln for ln in text.splitlines() if ln.strip() not in boilerplate)
