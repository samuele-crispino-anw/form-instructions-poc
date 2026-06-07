"""Orchestratore di conversione per pagina con escalation Graduata (Nota consolidata §A).

Catena Rotta A: economico (Haiku) -> forte (Opus) -> VLM -> coda umana, salendo di gradino
ogni volta che gate+lint non passano. Le pagine `anomalous` partono dal VLM (routing B.3).
Tutto guidato da config ([models]/[escalation]/[gate]/[lint]); nessun hardcode PF1.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

from poc_istruzioni.config import Settings
from poc_istruzioni.db.repositories import ConversionRow, insert_audit, upsert_conversion
from poc_istruzioni.ingest.checks import extract_numbers, run_gate_from_settings
from poc_istruzioni.ingest.layout import analyze_document
from poc_istruzioni.ingest.lint import lint_markdown
from poc_istruzioni.ingest.routing import route
from poc_istruzioni.ingest.textlayer import (
    extract_pages_text,
    find_boilerplate_lines,
    strip_lines,
)
from poc_istruzioni.ingest.textroute import convert_text_to_markdown, extract_text_with_cues
from poc_istruzioni.ingest.transcribe import transcribe_page
from poc_istruzioni.llm.client import LlmClient, LlmResult
from poc_istruzioni.provenance import utc_now_iso


@dataclass
class PageOutcome:
    n: int
    route: str  # A | B (rotta iniziale)
    model_used: str  # modello dell'output finale/accettato
    escalations: int  # gradini saliti oltre il primo
    status: str  # ok | needs_human
    markdown: str
    reasons: list[str]  # motivi gate/lint dell'ultimo tentativo (se needs_human)
    usd: float  # costo totale (tutti i tentativi)


def _gate_and_lint(
    md: str, ref: str, settings: Settings, *, page_number: int, boilerplate
) -> tuple[bool, list[str]]:
    """True+[] se gate e lint passano; altrimenti False + motivi (gate prima, lint poi)."""
    rep = run_gate_from_settings(md, ref, settings, page_number=page_number)
    lint = lint_markdown(
        md,
        boilerplate=boilerplate,
        page_number=page_number,
        orphan_warn_strings=tuple(settings.lint.orphan_warn_strings),
    )
    reasons = list(rep.reasons) + [f"lint: {f}" for f in lint.fails]
    return (not reasons), reasons


def _attempt(
    llm: LlmClient, route: str, model: str, *, cues_text, image_path,
    prompt_text, prompt_vision, page_n, scopo,
) -> LlmResult:
    if route == "A":
        return convert_text_to_markdown(
            llm, cues_text, model=model, prompt=prompt_text, page_n=page_n, scopo=scopo
        )
    return transcribe_page(
        llm, image_path, model=model, prompt=prompt_vision, page_n=page_n, scopo=scopo
    )


def convert_page(
    llm: LlmClient,
    *,
    route: str,
    page_n: int,
    cues_text: str,
    image_path,
    ref_text: str,
    settings: Settings,
    prompt_text: str,
    prompt_vision: str,
    boilerplate,
    scopo: str = "conversion:full-run",
    force_strong: bool = False,
) -> PageOutcome:
    """Converte una pagina salendo la catena di escalation finché gate+lint passano."""
    esc = settings.escalation
    if route == "B":
        attempts = [("B", esc.route_b_model)]
    else:
        chain = esc.route_a_chain
        # Default PoC (economical_first=false): parti dal forte (Opus), salta l'economico.
        # Circuit breaker: stesso effetto sulle pagine restanti.
        if (not esc.economical_first or force_strong) and len(chain) > 1:
            chain = chain[1:]
        attempts = [("A", s) for s in chain] + [("B", esc.route_b_model)]

    usd = 0.0
    escalations = 0
    last_md = ""
    last_reasons: list[str] = []
    model_used = ""
    for i, (r, scope) in enumerate(attempts):
        model = settings.model_for(scope)
        res = _attempt(
            llm, r, model, cues_text=cues_text, image_path=image_path,
            prompt_text=prompt_text, prompt_vision=prompt_vision, page_n=page_n, scopo=scopo,
        )
        usd += res.cost.usd
        last_md, model_used = res.text, model
        passed, last_reasons = _gate_and_lint(
            res.text, ref_text, settings, page_number=page_n, boilerplate=boilerplate
        )
        if passed:
            return PageOutcome(page_n, route, model_used, escalations, "ok", last_md, [], usd)
        if i < len(attempts) - 1:
            escalations += 1
    return PageOutcome(
        page_n, route, model_used, escalations, "needs_human", last_md, last_reasons, usd
    )


def _audit_diff(haiku_md: str, opus_md: str, critical_words: list[str]) -> bool:
    """True se Haiku e Opus divergono su numeri o conteggio di parole critiche (§M2.3)."""
    if extract_numbers(haiku_md) != extract_numbers(opus_md):
        return True
    for w in critical_words:
        pat = re.compile(r"\b" + re.escape(w.lower()) + r"\b")
        if len(pat.findall(haiku_md.lower())) != len(pat.findall(opus_md.lower())):
            return True
    return False


@dataclass
class RunSummary:
    pages: int
    route_a: int
    route_b: int
    escalated: int
    needs_human: int
    gate_misses: int
    breaker_tripped: bool
    usd: float


def convert_document(
    conn: sqlite3.Connection,
    llm: LlmClient,
    *,
    doc_id: str,
    pdf_path: Path | str,
    pages_dir: Path | str,
    markdown_dir: Path | str,
    settings: Settings,
    prompt_text: str,
    prompt_vision: str,
    page_numbers: list[int] | None = None,
) -> RunSummary:
    """Converte le pagine con routing + escalation + audit + circuit breaker, e logga tutto."""
    pdf_path = Path(pdf_path)
    pages_dir = Path(pages_dir)
    md_dir = Path(markdown_dir) / doc_id / "pages"
    md_dir.mkdir(parents=True, exist_ok=True)

    pages_text = extract_pages_text(pdf_path)
    boiler = find_boilerplate_lines(pages_text)
    metrics = {m.page: m for m in analyze_document(pdf_path)}
    page_numbers = page_numbers or sorted(metrics)

    economical = settings.model_for(settings.escalation.route_a_chain[0])
    strong = settings.model_for(settings.escalation.route_a_chain[-1])
    frac = settings.escalation.audit_fraction
    audit_every = round(1 / frac) if frac else 0

    doc = fitz.open(pdf_path)
    breaker = False
    haiku_ok = misses = 0
    usd = 0.0
    try:
        for n in page_numbers:
            decision = route(metrics[n], settings.routing)
            cues = extract_text_with_cues(doc[n - 1], boilerplate=boiler, page_number=n)
            ref = strip_lines(pages_text[n - 1], boiler)
            outcome = convert_page(
                llm, route=decision.route, page_n=n, cues_text=cues,
                image_path=pages_dir / f"p{n:03d}.png", ref_text=ref, settings=settings,
                prompt_text=prompt_text, prompt_vision=prompt_vision, boilerplate=boiler,
                scopo="conversion:full-run", force_strong=breaker,
            )
            md_path = md_dir / f"p{n:03d}.md"
            md_path.write_text(outcome.markdown, encoding="utf-8")
            usd += outcome.usd
            upsert_conversion(conn, ConversionRow(
                doc_id=doc_id, n=n, route=outcome.route, model_used=outcome.model_used,
                escalations=outcome.escalations, status=outcome.status,
                reasons="; ".join(outcome.reasons) or None, md_path=str(md_path),
                usd=round(outcome.usd, 6), ts=utc_now_iso(),
            ))

            # Audit campionario: pagine Rotta A accettate al primo tier (Haiku).
            accepted_haiku = (
                decision.route == "A" and outcome.status == "ok"
                and outcome.escalations == 0 and outcome.model_used == economical
            )
            if accepted_haiku and audit_every:
                haiku_ok += 1
                if haiku_ok % audit_every == 0:
                    res = convert_text_to_markdown(
                        llm, cues, model=strong, prompt=prompt_text, page_n=n,
                        scopo="audit:haiku-sample",
                    )
                    usd += res.cost.usd
                    diff = _audit_diff(outcome.markdown, res.text, settings.gate.critical_words)
                    insert_audit(
                        conn, doc_id, n, gate_flagged=False, diff_found=diff,
                        gate_miss=diff, ts=utc_now_iso(),
                    )
                    if diff:
                        misses += 1
                        if settings.escalation.circuit_breaker:
                            breaker = True  # default forte per le pagine restanti
    finally:
        doc.close()

    from poc_istruzioni.db.repositories import governance

    g = governance(conn, doc_id)
    return RunSummary(
        pages=g["pages"], route_a=g["route_a"], route_b=g["route_b"],
        escalated=g["escalated"], needs_human=g["needs_human"],
        gate_misses=misses or g["gate_misses"],
        breaker_tripped=breaker, usd=round(usd, 4),
    )
