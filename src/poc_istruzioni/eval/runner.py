"""Runner di eval (FR-E): esegue un caso su un arm, giudica, ritorna le metriche.

Due arm:
- servi_intero: serve l'intero quadro come contesto (in `system`, con prompt caching: identico per
  tutte le domande -> 1 write + N read), baseline da battere.
- navigazione: usa l'orchestratore (fast-path/gate/nav-LLM) e serve la voce mirata + i pin.
"""

from __future__ import annotations

import time

from poc_istruzioni.bootstrap import resolve_path
from poc_istruzioni.eval.dataset import EvalCase
from poc_istruzioni.eval.judge import (
    is_refusal,
    judge_answer,
    must_include_coverage,
    retrieval_hit,
)
from poc_istruzioni.llm.client import LlmClient
from poc_istruzioni.serving.nodes import _FRONTMATTER_RE
from poc_istruzioni.serving.orchestrator import run_retrieval

_REFUSAL = "Le istruzioni fornite non contengono la risposta a questa domanda."


def build_full_quadro_context(ctx, doc_id: str, frm: int, to: int) -> str:
    """Concatena il markdown dell'intero quadro (baseline servi-intero)."""
    pages_dir = resolve_path(ctx.settings.paths.markdown_dir) / doc_id / "pages"
    parts = []
    for p in range(frm, to + 1):
        f = pages_dir / f"p{p:03d}.md"
        if f.exists():
            body = _FRONTMATTER_RE.sub("", f.read_text(encoding="utf-8")).strip()
            parts.append(f"== p.{p} ==\n{body}")
    return "\n\n".join(parts)


def _reasoning(raw) -> str:
    out = [getattr(b, "thinking", "") or getattr(b, "text", "")
           for b in getattr(raw, "content", []) or [] if getattr(b, "type", None) == "thinking"]
    return "\n".join(x for x in out if x).strip()


def answer_question(client, *, answer_system, served, query, model, cache_context):
    """Genera la risposta. cache_context=True mette il contesto in system con cache_control (1h)."""
    if cache_context:
        system = [{"type": "text", "text": answer_system}, {"type": "text", "text": served}]
        messages = [{"role": "user", "content": f"DOMANDA: {query}"}]
        res = client.complete(
            scopo="answer:servi_intero", model=model, system=system, cache_ttl="1h",
            messages=messages, thinking={"type": "adaptive", "display": "summarized"},
        )
    else:
        messages = [{"role": "user", "content": f"CONTESTO:\n{served}\n\nDOMANDA: {query}"}]
        res = client.complete(
            scopo="answer:navigazione", model=model, system=answer_system,
            messages=messages, thinking={"type": "adaptive", "display": "summarized"},
        )
    return res.text.strip(), _reasoning(res.raw), res


def run_case(
    ctx, case: EvalCase, arm: str, *, doc_id: str, full_context: str,
    answer_system: str, judge_system: str, answer_model: str, judge_model: str,
) -> dict:
    """Esegue un caso su un arm e ritorna metriche + costi (da persistere in eval_results)."""
    client = LlmClient(ctx.conn, ctx.prices, settings=ctx.settings)
    retr_cost = answer_cost = 0.0
    target_title = None

    if arm == "servi_intero":
        served = full_context
    else:  # navigazione
        r = run_retrieval(ctx, case.domanda, doc_id)
        retr_cost = r.cost_usd if r else 0.0
        served = r.served_text if r and r.target_node_id is not None else ""
        target_title = r.target_title if r else None

    if served:
        t0 = time.perf_counter()
        answer, _reason, res = answer_question(
            client, answer_system=answer_system, served=served, query=case.domanda,
            model=answer_model, cache_context=(arm == "servi_intero"),
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        answer_cost = res.cost.usd
    else:  # retrieval ha rifiutato a monte
        answer, latency_ms = _REFUSAL, 0

    verdict, judge_cost = judge_answer(
        client, model=judge_model, system_prompt=judge_system, question=case.domanda,
        answer=answer, answerable=case.answerable, must_include=case.must_include,
    )
    mi_hit, mi_tot = must_include_coverage(answer, case.must_include)
    correct = verdict in ("CORRETTO", "RIFIUTO_OK")
    # il retrieval-hit ha senso solo per l'arm navigazione (servi-intero non seleziona voci)
    hit = retrieval_hit(case.expected_target, target_title) if arm == "navigazione" else None

    return {
        "case_id": case.id, "arm": arm, "origin": case.origin, "categoria": case.categoria,
        "difficolta": case.difficolta, "hops": case.hops, "answerable": case.answerable,
        "verdict": verdict, "correct": correct, "refused": is_refusal(answer),
        "retrieval_hit": hit,
        "must_include_hit": mi_hit, "must_include_tot": mi_tot,
        "target_title": target_title, "answer": answer,
        "cost_usd": round(retr_cost + answer_cost + judge_cost, 6), "latency_ms": latency_ms,
    }
