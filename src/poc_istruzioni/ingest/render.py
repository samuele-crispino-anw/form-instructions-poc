"""FR-B1: rendering delle pagine PDF in immagini PNG.

Il layer testuale del PDF non è affidabile per l'ordine di lettura (layout a 2 colonne,
testo-fantasma): la trascrizione (B2) lavora sulle immagini, non sul testo estratto.
Rendering deterministico: stesso PDF + stesso DPI -> stessi byte PNG -> stesso hash (FR-T3).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

from poc_istruzioni.provenance import sha256_bytes


@dataclass(frozen=True)
class RenderedPage:
    """Esito del rendering di una pagina (numero 1-based, percorso PNG, hash)."""

    n: int
    png_path: Path
    sha256: str


def render_pdf(pdf_path: Path | str, out_dir: Path | str, *, dpi: int = 175) -> list[RenderedPage]:
    """Renderizza ogni pagina del PDF in `out_dir/p{NNN}.png` e ne calcola lo sha256.

    Le pagine sono numerate da 1 con padding a 3 cifre (p001.png, p002.png, ...).
    """
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rendered: list[RenderedPage] = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            data = page.get_pixmap(dpi=dpi).tobytes("png")
            png_path = out_dir / f"p{i:03d}.png"
            png_path.write_bytes(data)
            rendered.append(RenderedPage(n=i, png_path=png_path, sha256=sha256_bytes(data)))
    return rendered
