"""Orchestrazione del retrieval (riusabile da CLI ed eval): fast-path -> gate -> nav-LLM -> pin.

Estratta qui per essere importabile senza passare dall'app CLI. Fa IO (DB, file, LLM) tramite il
Context applicativo; la logica pura (gate, assembly) resta in serving/retrieval.py.
"""

from __future__ import annotations

from poc_istruzioni.bootstrap import resolve_path
from poc_istruzioni.config import load_aliases, load_prompt
from poc_istruzioni.db.repositories import get_keywords, get_nodes, get_pins
from poc_istruzioni.llm.client import LlmClient
from poc_istruzioni.serving.keywords import IndexEntry, score_nodes
from poc_istruzioni.serving.nodes import Node
from poc_istruzioni.serving.pins import Pin, collect_pins
from poc_istruzioni.serving.retrieval import (
    RetrievalResult,
    build_served_context,
    classify_fastpath,
    navigate_llm,
    served_page_range,
)
from poc_istruzioni.serving.summaries import _page_text


def _read_pages(pages_dir, start: int, end: int) -> dict[int, str]:
    md = {}
    for p in range(start, end + 1):
        f = pages_dir / f"p{p:03d}.md"
        if f.exists():
            md[p] = f.read_text(encoding="utf-8")
    return md


def run_retrieval(ctx, query: str, doc_id: str) -> RetrievalResult | None:
    """Esegue il retrieval completo; ritorna un RetrievalResult (None se non ci sono nodi)."""
    rows = get_nodes(ctx.conn, doc_id)
    if not rows:
        return None
    nodes = [
        Node(id=r["id"], parent_id=r["parent_id"], kind=r["kind"], level=r["level"],
             title=r["title"], page_start=r["page_start"], page_end=r["page_end"], ord=r["ord"])
        for r in rows
    ]
    by_id = {n.id: n for n in nodes}
    summaries = {r["id"]: r["summary"] for r in rows}
    entries = [
        IndexEntry(term=r["term"], node_id=r["node_id"], weight=r["weight"])
        for r in get_keywords(ctx.conn, doc_id)
    ]
    pins = [
        Pin(owner_node_id=r["owner_node_id"], owner_kind=r["owner_kind"],
            owner_title=r["owner_title"], text=r["text"])
        for r in get_pins(ctx.conn, doc_id)
    ]
    cfg = ctx.settings.retrieval
    ranked = score_nodes(query, entries, load_aliases())
    gate, reason = classify_fastpath(ranked, min_abs=cfg.gate_min_abs, margin=cfg.gate_margin)

    cost = 0.0
    if gate == "netto":
        method, target = "fast_path", ranked[0][0]
    else:
        shortlist = [nid for nid, _ in ranked[: cfg.top_k]] or [
            n.id for n in nodes if n.kind in ("sezione", "rigo")
        ]
        cand = [
            (n.id, n.kind, n.title, summaries.get(n.id) or "")
            for n in nodes if n.id in set(shortlist)
        ]
        client = LlmClient(ctx.conn, ctx.prices, settings=ctx.settings)
        target, res = navigate_llm(
            query, cand, client,
            model=ctx.settings.model_for("router"), system_prompt=load_prompt("nav_router"),
        )
        cost += res.cost.usd
        method = "navigation_llm" if target is not None else "refused"

    result = RetrievalResult(
        query=query, gate=gate, reason=reason, method=method,
        target_node_id=target, candidates=ranked[: cfg.top_k], cost_usd=cost,
    )
    if target is not None:
        t = by_id[target]
        pages_dir = resolve_path(ctx.settings.paths.markdown_dir) / doc_id / "pages"
        # estende il serving fino all'inizio del nodo successivo (anti-troncamento)
        s_start, s_end = served_page_range(t.page_start, t.page_end, [n.page_start for n in nodes])
        md = _read_pages(pages_dir, s_start, s_end)
        result.pins = collect_pins(target, nodes, pins)
        result.target_title = t.title
        result.target_pages = f"{t.page_start}-{t.page_end}"  # range del nodo (display invariato)
        result.served_text = build_served_context(
            t.title, _page_text(md, s_start, s_end), result.pins
        )
    return result
