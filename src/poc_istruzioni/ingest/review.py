"""Generatore di review affiancata in HTML per la trascrizione VLM (FR-B2, livello C).

Produce un file autocontenuto (immagini in base64) per validare a colpo d'occhio:
immagine pagina | markdown trascritto | esiti dei check automatici. Un file per batch.
"""

from __future__ import annotations

import base64
import html
from dataclasses import dataclass
from pathlib import Path

from poc_istruzioni.ingest.checks import CheckReport

_CSS = """
body { font-family: system-ui, sans-serif; margin: 1.5rem; color: #1a1a1a; }
table.summary { border-collapse: collapse; margin-bottom: 2rem; width: 100%; }
table.summary th, table.summary td { border: 1px solid #ccc; padding: 4px 8px; font-size: 0.9rem; }
.ok { color: #137333; font-weight: 600; }
.review { color: #c5221f; font-weight: 600; }
.page { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin: 2rem 0;
        border-top: 2px solid #888; padding-top: 1rem; }
.page img { max-width: 100%; border: 1px solid #ddd; }
.page pre { white-space: pre-wrap; background: #f6f6f6; padding: 0.8rem; font-size: 0.85rem; }
.checks { grid-column: 1 / 3; background: #fafafa; padding: 0.6rem 1rem; font-size: 0.9rem; }
.reasons { color: #c5221f; }
"""


@dataclass
class ReviewItem:
    """Una pagina da rivedere: numero, immagine, markdown VLM, esito check."""

    page_n: int
    image_path: Path
    vlm_md: str
    report: CheckReport


def _img_data_uri(image_path: Path) -> str:
    data = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def _status(report: CheckReport) -> tuple[str, str]:
    return ("review", "DA RIVEDERE") if report.needs_review else ("ok", "OK")


def _summary_row(item: ReviewItem) -> str:
    cls, label = _status(item.report)
    r = item.report
    reasons = html.escape("; ".join(r.reasons)) if r.reasons else ""
    return (
        f"<tr><td><a href='#p{item.page_n}'>p{item.page_n:03d}</a></td>"
        f"<td class='{cls}'>{label}</td>"
        f"<td>{r.overlap:.2f}</td><td>{r.number_recall:.2f}</td><td>{r.coverage:.2f}</td>"
        f"<td class='reasons'>{reasons}</td></tr>"
    )


def _page_section(item: ReviewItem) -> str:
    r = item.report
    cls, label = _status(item.report)
    missing = html.escape(", ".join(r.missing_numbers[:20]))
    reasons = html.escape("; ".join(r.reasons)) if r.reasons else "nessun problema rilevato"
    return (
        f"<div class='page' id='p{item.page_n}'>"
        f"<div><h3>p{item.page_n:03d} — <span class='{cls}'>{label}</span></h3>"
        f"<img src='{_img_data_uri(item.image_path)}' alt='pagina {item.page_n}'></div>"
        f"<div><h3>markdown VLM</h3><pre>{html.escape(item.vlm_md)}</pre></div>"
        f"<div class='checks'><b>Check:</b> overlap {r.overlap:.2f} · "
        f"numeri recall {r.number_recall:.2f} · copertura {r.coverage:.2f}<br>"
        f"<span class='reasons'>{reasons}</span>"
        f"{f'<br>numeri mancanti: {missing}' if missing else ''}</div>"
        f"</div>"
    )


def build_review_html(title: str, items: list[ReviewItem]) -> str:
    """Costruisce l'HTML di review per un batch di pagine."""
    n_review = sum(1 for it in items if it.report.needs_review)
    summary = "".join(_summary_row(it) for it in items)
    sections = "".join(_page_section(it) for it in items)
    return (
        "<!doctype html><html lang='it'><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head><body>"
        f"<h1>{html.escape(title)}</h1>"
        f"<p>{len(items)} pagine · <span class='review'>{n_review} da rivedere</span></p>"
        "<table class='summary'><tr><th>pagina</th><th>stato</th><th>overlap</th>"
        "<th>num.recall</th><th>copertura</th><th>motivi</th></tr>"
        f"{summary}</table>{sections}</body></html>"
    )


def write_review_html(path: Path | str, title: str, items: list[ReviewItem]) -> Path:
    """Scrive l'HTML di review su file e ne ritorna il percorso."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_review_html(title, items), encoding="utf-8")
    return path


@dataclass
class AnomalyItem:
    """Una pagina finita in revisione umana: cosa il revisore deve controllare."""

    page_n: int
    image_path: Path
    markdown: str
    reasons: list[str]
    model_used: str
    escalations: int


def build_anomaly_report_html(items: list[AnomalyItem]) -> str:
    """Report per il revisore umano: per pagina, MOTIVI in evidenza + immagine + markdown."""
    sections = []
    for it in items:
        reasons = "".join(f"<li>{html.escape(r)}</li>" for r in it.reasons) or "<li>—</li>"
        sections.append(
            f"<div class='page' id='p{it.page_n}'>"
            f"<div class='checks'><h3>p{it.page_n:03d} — DA RIVEDERE</h3>"
            f"<b>Cosa controllare (motivi del blocco):</b><ul class='reasons'>{reasons}</ul>"
            f"<small>modelli saliti: {it.escalations} escalation · ultimo modello: "
            f"{html.escape(it.model_used)}</small></div>"
            f"<div><h4>pagina (immagine)</h4>"
            f"<img src='{_img_data_uri(it.image_path)}' alt='pagina {it.page_n}'></div>"
            f"<div><h4>markdown prodotto (rifiutato)</h4>"
            f"<pre>{html.escape(it.markdown)}</pre></div>"
            f"</div>"
        )
    n = len(items)
    intro = "Per ogni pagina: i <b>motivi</b> dicono cosa cercare; confronta immagine e markdown."
    return (
        "<!doctype html><html lang='it'><head><meta charset='utf-8'>"
        f"<title>Pagine da rivedere</title><style>{_CSS}</style></head><body>"
        f"<h1>Revisione umana — {n} pagine bloccate</h1>"
        f"<p>{intro}</p>"
        f"{''.join(sections)}</body></html>"
    )
