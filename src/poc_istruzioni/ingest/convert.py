"""Orchestratore di conversione per pagina con escalation Graduata (Nota consolidata §A).

Catena Rotta A: economico (Haiku) -> forte (Opus) -> VLM -> coda umana, salendo di gradino
ogni volta che gate+lint non passano. Le pagine `anomalous` partono dal VLM (routing B.3).
Tutto guidato da config ([models]/[escalation]/[gate]/[lint]); nessun hardcode PF1.
"""

from __future__ import annotations

from dataclasses import dataclass

from poc_istruzioni.config import Settings
from poc_istruzioni.ingest.checks import run_gate_from_settings
from poc_istruzioni.ingest.lint import lint_markdown
from poc_istruzioni.ingest.textroute import convert_text_to_markdown
from poc_istruzioni.ingest.transcribe import transcribe_page
from poc_istruzioni.llm.client import LlmClient, LlmResult


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
        if force_strong and len(chain) > 1:  # circuit breaker: salta l'economico
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
