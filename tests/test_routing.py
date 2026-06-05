"""Test della regola di routing per-pagina (§B)."""

from poc_istruzioni.config import Routing
from poc_istruzioni.ingest.layout import LayoutMetrics
from poc_istruzioni.ingest.routing import route


def _m(n_words: int, n_lines_rects: int) -> LayoutMetrics:
    return LayoutMetrics(
        page=1, n_words=n_words, n_lines=10, gutter_cross=5, gutter_ratio=0.5,
        median_line_width=0.8, pct_lines_wide=0.7, n_lines_rects=n_lines_rects,
        n_images=0, has_ghost=False, classification="single_column",
    )


def test_pagina_normale_va_in_A() -> None:
    d = route(_m(300, 10), Routing(min_words_text_route=5))
    assert d.route == "A"


def test_pagina_quasi_vuota_va_in_B() -> None:
    d = route(_m(2, 0), Routing(min_words_text_route=5))
    assert d.route == "B"
    assert "text-layer scarso" in d.reason


def test_table_heavy_non_forzata_se_soglia_disattivata() -> None:
    # default: table_rects_force_vlm=None -> una pagina con 270 rect resta su A (B1)
    d = route(_m(800, 270), Routing(min_words_text_route=5))
    assert d.route == "A"


def test_table_heavy_forzata_se_soglia_attiva() -> None:
    d = route(_m(800, 270), Routing(min_words_text_route=5, table_rects_force_vlm=50))
    assert d.route == "B"
    assert "tabella densa" in d.reason
