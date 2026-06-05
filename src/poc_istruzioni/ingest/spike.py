"""Spike comparativo Rotta A (text-layer) vs Rotta B (VLM) per-classe (Nota §3/§4).

Per ogni pagina del campione: converte con entrambe le rotte, misura fedeltà (overlap,
recall numeri), struttura (n. heading), costo e tempo; aggrega per classe di layout per
validare la policy di routing (A per single_column, VLM per table_heavy/anomalous).
"""

from __future__ import annotations

import base64
import csv
import html
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

import fitz  # PyMuPDF

from poc_istruzioni.ingest.checks import DEFAULT_ARTIFACTS, run_checks
from poc_istruzioni.ingest.textroute import convert_text_to_markdown, extract_text_with_cues
from poc_istruzioni.ingest.transcribe import transcribe_page
from poc_istruzioni.llm.client import LlmClient


def count_headings(md: str) -> int:
    """Numero di heading markdown (## quadro o ### rigo)."""
    return sum(1 for ln in md.splitlines() if ln.startswith("## ") or ln.startswith("### "))


def _strip_artifacts(text: str, artifacts: tuple[str, ...]) -> str:
    for a in artifacts:
        text = text.replace(a, "")
    return text


@dataclass
class SpikeRow:
    page: int
    klass: str
    overlap_a: float
    numrec_a: float
    headings_a: int
    cost_a: float
    secs_a: float
    overlap_b: float
    numrec_b: float
    headings_b: int
    cost_b: float
    secs_b: float


def _metrics(md: str, ref: str) -> tuple[float, float, int]:
    rep = run_checks(md, ref)
    return round(rep.overlap, 3), round(rep.number_recall, 3), count_headings(md)


def run_spike(
    llm: LlmClient,
    pdf_path: Path | str,
    *,
    sample: list[int],
    klass_by_page: dict[int, str],
    ref_texts: dict[int, str],
    pages_dir: Path | str,
    out_dir: Path | str,
    model: str,
    prompt_text: str,
    prompt_vision: str,
    artifacts: tuple[str, ...] = DEFAULT_ARTIFACTS,
) -> list[SpikeRow]:
    """Esegue A e B su ogni pagina del campione e ritorna le righe di confronto."""
    pages_dir = Path(pages_dir)
    out_dir = Path(out_dir)
    (out_dir / "routeA").mkdir(parents=True, exist_ok=True)
    (out_dir / "routeB").mkdir(parents=True, exist_ok=True)

    doc = fitz.open(Path(pdf_path))
    rows: list[SpikeRow] = []
    try:
        for n in sample:
            ref = _strip_artifacts(ref_texts.get(n, ""), artifacts)

            try:
                # Rotta A: text-layer -> markdown
                t0 = perf_counter()
                res_a = convert_text_to_markdown(
                    llm, extract_text_with_cues(doc[n - 1]),
                    model=model, prompt=prompt_text, page_n=n,
                )
                secs_a = perf_counter() - t0

                # Rotta B: immagine -> markdown (VLM)
                t0 = perf_counter()
                res_b = transcribe_page(
                    llm, pages_dir / f"p{n:03d}.png", model=model, prompt=prompt_vision, page_n=n
                )
                secs_b = perf_counter() - t0
            except Exception:  # noqa: BLE001 — resilienza: una pagina fallita non ferma lo spike
                continue

            (out_dir / "routeA" / f"p{n:03d}.md").write_text(res_a.text, encoding="utf-8")
            (out_dir / "routeB" / f"p{n:03d}.md").write_text(res_b.text, encoding="utf-8")

            ov_a, nr_a, h_a = _metrics(res_a.text, ref)
            ov_b, nr_b, h_b = _metrics(res_b.text, ref)
            rows.append(
                SpikeRow(
                    page=n,
                    klass=klass_by_page.get(n, "?"),
                    overlap_a=ov_a, numrec_a=nr_a, headings_a=h_a,
                    cost_a=round(res_a.cost.usd, 6), secs_a=round(secs_a, 2),
                    overlap_b=ov_b, numrec_b=nr_b, headings_b=h_b,
                    cost_b=round(res_b.cost.usd, 6), secs_b=round(secs_b, 2),
                )
            )
    finally:
        doc.close()
    return rows


def summarize_by_class(rows: list[SpikeRow]) -> dict[str, dict[str, float]]:
    """Media per classe delle metriche chiave delle due rotte."""
    by: dict[str, list[SpikeRow]] = {}
    for r in rows:
        by.setdefault(r.klass, []).append(r)

    def avg(vals: list[float]) -> float:
        return round(statistics.mean(vals), 3) if vals else 0.0

    out: dict[str, dict[str, float]] = {}
    for klass, items in by.items():
        out[klass] = {
            "pages": len(items),
            "overlap_a": avg([r.overlap_a for r in items]),
            "overlap_b": avg([r.overlap_b for r in items]),
            "numrec_a": avg([r.numrec_a for r in items]),
            "numrec_b": avg([r.numrec_b for r in items]),
            "cost_a": avg([r.cost_a for r in items]),
            "cost_b": avg([r.cost_b for r in items]),
        }
    return out


def write_spike_csv(rows: list[SpikeRow], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(asdict(rows[0]).keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow(asdict(r))
    return path


def build_spike_html(rows: list[SpikeRow], out_dir: Path | str, pages_dir: Path | str) -> str:
    """HTML a 3 colonne (immagine | Rotta A | Rotta B) per la review umana."""
    out_dir = Path(out_dir)
    pages_dir = Path(pages_dir)
    css = (
        "body{font-family:system-ui,sans-serif;margin:1.5rem}"
        ".p{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1rem;"
        "border-top:2px solid #888;padding-top:1rem;margin:2rem 0}"
        ".p img{max-width:100%}.p pre{white-space:pre-wrap;background:#f6f6f6;"
        "padding:.6rem;font-size:.8rem}.m{grid-column:1/4;background:#fafafa;padding:.5rem}"
    )
    sections = []
    for r in rows:
        img = pages_dir / f"p{r.page:03d}.png"
        img_uri = (
            f"data:image/png;base64,{base64.b64encode(img.read_bytes()).decode('ascii')}"
            if img.exists()
            else ""
        )
        md_a = html.escape((out_dir / "routeA" / f"p{r.page:03d}.md").read_text(encoding="utf-8"))
        md_b = html.escape((out_dir / "routeB" / f"p{r.page:03d}.md").read_text(encoding="utf-8"))
        sections.append(
            f"<div class='p'><div><h3>p{r.page:03d} [{r.klass}]</h3>"
            f"<img src='{img_uri}'></div>"
            f"<div><h4>Rotta A (testo)</h4><pre>{md_a}</pre></div>"
            f"<div><h4>Rotta B (VLM)</h4><pre>{md_b}</pre></div>"
            f"<div class='m'>A: overlap {r.overlap_a} · numeri {r.numrec_a} · "
            f"heading {r.headings_a} · ${r.cost_a:.4f} · {r.secs_a}s &nbsp;|&nbsp; "
            f"B: overlap {r.overlap_b} · numeri {r.numrec_b} · heading {r.headings_b} · "
            f"${r.cost_b:.4f} · {r.secs_b}s</div></div>"
        )
    return (
        "<!doctype html><html lang='it'><head><meta charset='utf-8'>"
        f"<title>Spike A vs B</title><style>{css}</style></head><body>"
        f"<h1>Spike conversione — A (testo) vs B (VLM)</h1>{''.join(sections)}</body></html>"
    )
