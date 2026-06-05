"""Regola di routing per-pagina (Nota raffinamento §B): A=text-layer, B=VLM.

Regola deterministica e ispezionabile derivata dai fallimenti MISURATI nello spike:
la Rotta A regge tutte le classi di PF1 (incluse le table_heavy), quindi il default è A;
si instrada a VLM solo dove il text-layer è genuinamente inutile (pagine quasi-vuote/immagine).
Soglie in config per tipo-documento (nessuna assunzione PF1 nel codice). Ogni decisione motivata.
"""

from __future__ import annotations

from dataclasses import dataclass

from poc_istruzioni.config import Routing
from poc_istruzioni.ingest.layout import LayoutMetrics


@dataclass(frozen=True)
class RouteDecision:
    route: str  # "A" (text-layer) | "B" (VLM)
    reason: str


def route(metrics: LayoutMetrics, cfg: Routing) -> RouteDecision:
    """Sceglie la rotta per una pagina dalle sue metriche di layout.

    B.3: le pagine `anomalous` (text-layer inaffidabile, es. testo-fantasma promosso a
    identità) vanno al VLM. Altrimenti Rotta A; gli slip stocastici di Haiku li gestisce
    il gate+escalation (A.2 per densità è stata scartata: non separa i fallimenti).
    """
    if metrics.classification == "anomalous":
        return RouteDecision("B", "classe anomalous (text-layer inaffidabile)")
    if metrics.n_words < cfg.min_words_text_route:
        return RouteDecision(
            "B", f"text-layer scarso (n_words={metrics.n_words} < {cfg.min_words_text_route})"
        )
    if cfg.table_rects_force_vlm is not None and metrics.n_lines_rects >= cfg.table_rects_force_vlm:
        return RouteDecision(
            "B", f"tabella densa (rects={metrics.n_lines_rects} >= {cfg.table_rects_force_vlm})"
        )
    return RouteDecision("A", "default text-layer")


def route_all(
    metrics: list[LayoutMetrics], cfg: Routing
) -> list[tuple[LayoutMetrics, RouteDecision]]:
    """Applica la regola a tutte le pagine."""
    return [(m, route(m, cfg)) for m in metrics]
