"""Analisi geometrica del layout per pagina (Nota strategica §2).

Verifica l'assunzione "2 colonne" e classifica ogni pagina per scegliere la rotta di
conversione (VLM vs text-layer). Nessun LLM: pura geometria.
- gutter-test: parole che attraversano la banda centrale (alto => colonna singola);
- larghezza righe: mediana e % righe larghe (>0.75w);
- densità tabellare: lines+rects (pdfplumber);
- anomalie: testo-fantasma, pagine quasi vuote.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

import fitz  # PyMuPDF
import pdfplumber

from poc_istruzioni.ingest.checks import DEFAULT_ARTIFACTS

# Soglie di classificazione (euristiche, tarabili sui numeri reali del documento).
MIN_WORDS_ANOMALOUS = 15
TABLE_LINES_RECTS = 25
MULTICOL_MEDIAN_WIDTH = 0.55
MULTICOL_PCT_WIDE = 0.30
MULTICOL_GUTTER_RATIO = 0.15

CLASSES = ("single_column", "multi_column", "table_heavy", "anomalous")


@dataclass
class LayoutMetrics:
    page: int
    n_words: int
    n_lines: int
    gutter_cross: int
    gutter_ratio: float
    median_line_width: float
    pct_lines_wide: float
    n_lines_rects: int
    n_images: int
    has_ghost: bool
    classification: str


def classify(
    *,
    n_words: int,
    n_lines: int,
    gutter_ratio: float,
    median_line_width: float,
    pct_lines_wide: float,
    n_lines_rects: int,
    has_ghost: bool,
) -> str:
    """Classe di layout dalla luce delle metriche (funzione pura)."""
    if has_ghost or n_words < MIN_WORDS_ANOMALOUS:
        return "anomalous"
    if n_lines_rects >= TABLE_LINES_RECTS:
        return "table_heavy"
    if (
        median_line_width < MULTICOL_MEDIAN_WIDTH
        and pct_lines_wide < MULTICOL_PCT_WIDE
        and gutter_ratio < MULTICOL_GUTTER_RATIO
    ):
        return "multi_column"
    return "single_column"


def _page_geometry(page: fitz.Page) -> tuple[int, int, int, float, float]:
    """Ritorna (n_words, n_lines, gutter_cross, median_line_width, pct_lines_wide)."""
    w = page.rect.width or 1.0
    words = page.get_text("words")  # (x0, y0, x1, y1, word, block, line, word_no)
    band_lo, band_hi = 0.47 * w, 0.53 * w
    gutter_cross = sum(1 for x0, _, x1, *_ in words if x0 <= band_hi and x1 >= band_lo)

    spans: dict[tuple[int, int], list[float]] = defaultdict(lambda: [float("inf"), float("-inf")])
    for x0, _y0, x1, _y1, _word, bno, lno, _wno in words:
        key = (bno, lno)
        spans[key][0] = min(spans[key][0], x0)
        spans[key][1] = max(spans[key][1], x1)

    widths = [(x1 - x0) / w for x0, x1 in spans.values()]
    n_lines = len(widths)
    median_w = statistics.median(widths) if widths else 0.0
    pct_wide = (sum(1 for ww in widths if ww > 0.75) / n_lines) if n_lines else 0.0
    return len(words), n_lines, gutter_cross, median_w, pct_wide


def analyze_document(pdf_path: Path | str) -> list[LayoutMetrics]:
    """Calcola le metriche di layout per ogni pagina del PDF."""
    pdf_path = Path(pdf_path)
    results: list[LayoutMetrics] = []
    doc = fitz.open(pdf_path)
    plumber = pdfplumber.open(str(pdf_path))
    try:
        for i, page in enumerate(doc):
            n_words, n_lines, gutter_cross, median_w, pct_wide = _page_geometry(page)
            text = page.get_text()
            has_ghost = any(a.lower() in text.lower() for a in DEFAULT_ARTIFACTS)
            n_images = len(page.get_images())
            pp = plumber.pages[i]
            n_lines_rects = len(pp.lines) + len(pp.rects)
            gutter_ratio = gutter_cross / n_lines if n_lines else 0.0
            cls = classify(
                n_words=n_words,
                n_lines=n_lines,
                gutter_ratio=gutter_ratio,
                median_line_width=median_w,
                pct_lines_wide=pct_wide,
                n_lines_rects=n_lines_rects,
                has_ghost=has_ghost,
            )
            results.append(
                LayoutMetrics(
                    page=i + 1,
                    n_words=n_words,
                    n_lines=n_lines,
                    gutter_cross=gutter_cross,
                    gutter_ratio=round(gutter_ratio, 3),
                    median_line_width=round(median_w, 3),
                    pct_lines_wide=round(pct_wide, 3),
                    n_lines_rects=n_lines_rects,
                    n_images=n_images,
                    has_ghost=has_ghost,
                    classification=cls,
                )
            )
    finally:
        doc.close()
        plumber.close()
    return results


def summarize(metrics: list[LayoutMetrics]) -> dict[str, int]:
    """Conteggio pagine per classe."""
    counts = {c: 0 for c in CLASSES}
    for m in metrics:
        counts[m.classification] += 1
    return counts


def write_csv(metrics: list[LayoutMetrics], path: Path | str) -> Path:
    """Scrive le metriche per pagina in CSV (asset permanente)."""
    import csv

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(asdict(metrics[0]).keys()) if metrics else []
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for m in metrics:
            writer.writerow(asdict(m))
    return path
