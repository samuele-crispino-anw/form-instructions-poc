"""Aggregazione delle metriche di eval (FR-E). Logica pura, testabile senza IO."""

from __future__ import annotations

from collections import defaultdict


def summarize(results: list[dict], keys: list[str]) -> dict[tuple, dict]:
    """Raggruppa i risultati per `keys` e calcola le metriche per gruppo.

    Metriche: n, correct%, retrieval-hit% (solo dove applicabile), costo totale, latency media.
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in results:
        groups[tuple(r[k] for k in keys)].append(r)

    out: dict[tuple, dict] = {}
    for g, rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
        n = len(rs)
        correct = sum(1 for r in rs if r["correct"])
        hits = [r["retrieval_hit"] for r in rs if r["retrieval_hit"] is not None]
        out[g] = {
            "n": n,
            "correct": correct,
            "correct_pct": round(100 * correct / n, 1) if n else 0.0,
            "retr_hit_pct": round(100 * sum(hits) / len(hits), 1) if hits else None,
            "cost_usd": round(sum(r["cost_usd"] for r in rs), 4),
            "avg_latency_ms": int(sum(r["latency_ms"] for r in rs) / n) if n else 0,
        }
    return out


def format_table(summary: dict[tuple, dict], label: str) -> str:
    """Resa testuale di una summary (chiave -> metriche)."""
    lines = [f"  {label:28} {'n':>3}  {'correct':>8}  {'retr-hit':>8}  {'$tot':>7}  {'ms':>6}"]
    for g, m in summary.items():
        key = " · ".join(str(x) for x in g)
        rh = "—" if m["retr_hit_pct"] is None else f"{m['retr_hit_pct']:.0f}%"
        lines.append(
            f"  {key:28} {m['n']:>3}  {m['correct_pct']:>7.0f}%  {rh:>8}  "
            f"{m['cost_usd']:>7.3f}  {m['avg_latency_ms']:>6}"
        )
    return "\n".join(lines)
