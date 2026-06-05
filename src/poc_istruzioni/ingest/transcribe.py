"""FR-B2: trascrizione di una pagina-immagine in Markdown via modello vision (Opus).

La chiamata passa per LlmClient (unico accesso, ledger). Il prompt di trascrizione è il
prefisso di sistema, identico tra pagine -> cachabile (FR-B5). L'immagine varia per pagina.
"""

from __future__ import annotations

import base64
from pathlib import Path

from poc_istruzioni.llm.client import LlmClient, LlmResult


def _image_block(image_path: Path | str) -> dict:
    data = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": data},
    }


def transcribe_page(
    llm: LlmClient,
    image_path: Path | str,
    *,
    model: str,
    prompt: str,
    page_n: int,
    max_tokens: int = 8000,
    query_id: str | None = None,
) -> LlmResult:
    """Trascrive una pagina; ritorna l'LlmResult (testo markdown + costo + usage)."""
    messages = [
        {
            "role": "user",
            "content": [
                _image_block(image_path),
                {"type": "text", "text": f"Trascrivi fedelmente questa pagina (pagina {page_n})."},
            ],
        }
    ]
    return llm.complete(
        scopo=f"conversion:p{page_n:03d}",
        model=model,
        system=prompt,
        messages=messages,
        max_tokens=max_tokens,
        cache_ttl="5m",
        query_id=query_id,
    )
