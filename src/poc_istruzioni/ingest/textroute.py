"""Rotta A: conversione text-layer -> markdown senza vision (Nota strategica §3).

Estrae il testo in ordine di lettura con indizi di struttura dai metadati font
(dimensione, grassetto) per aiutare l'LLM a inferire titoli; poi una passata LLM
testo->markdown. Candidata primaria per le pagine single_column.
"""

from __future__ import annotations

from collections import Counter

import fitz  # PyMuPDF

from poc_istruzioni.llm.client import LlmClient, LlmResult

_HEADING_MARK = "〖H〗 "
_BOLD_FLAG = 16  # bit dei flag span PyMuPDF: grassetto
_HEADING_SIZE_RATIO = 1.15  # font > 1.15x del corpo => probabile titolo


def extract_text_with_cues(page: fitz.Page) -> str:
    """Testo della pagina in ordine di lettura; righe titolo/grassetto marcate con 〖H〗."""
    data = page.get_text("dict")

    # Dimensione del corpo = quella che copre più caratteri.
    sizes: Counter[int] = Counter()
    for block in data["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                sizes[round(span["size"])] += len(span["text"])
    body = sizes.most_common(1)[0][0] if sizes else 0

    out: list[str] = []
    for block in data["blocks"]:
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(s["text"] for s in spans).strip()
            if not text:
                continue
            max_size = max(round(s["size"]) for s in spans)
            bold = any(s["flags"] & _BOLD_FLAG for s in spans)
            is_heading = max_size > body * _HEADING_SIZE_RATIO or bold
            out.append((_HEADING_MARK if is_heading else "") + text)
    return "\n".join(out)


def convert_text_to_markdown(
    llm: LlmClient,
    text: str,
    *,
    model: str,
    prompt: str,
    page_n: int,
    max_tokens: int = 8000,
) -> LlmResult:
    """Converte il testo estratto in markdown via LLM (no vision). Purpose ledger: spike:routeA."""
    return llm.complete(
        scopo="spike:routeA",
        model=model,
        system=prompt,
        messages=[{"role": "user", "content": text}],
        max_tokens=max_tokens,
        cache_ttl="5m",
    )
