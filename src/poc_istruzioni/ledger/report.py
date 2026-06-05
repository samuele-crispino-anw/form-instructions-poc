"""Rendering testuale del ledger (presentazione separata dall'accesso ai dati)."""

from __future__ import annotations

from poc_istruzioni.ledger.store import CostRow

_HEADER = (
    f"{'chiave':<22} {'call':>5} {'tok_in':>10} {'tok_out':>9} "
    f"{'cache_r':>9} {'cache_w':>9} {'USD':>13} {'EUR':>13}"
)


def _fmt_row(label: str, r: CostRow) -> str:
    # 6 decimali: i micro-costi (chiamate piccole) non si azzerano in tabella.
    return (
        f"{label:<22} {r.calls:>5} {r.tok_in:>10} {r.tok_out:>9} "
        f"{r.tok_cache_r:>9} {r.tok_cache_w:>9} {r.usd:>13.6f} {r.eur:>13.6f}"
    )


def render_rows(rows: list[CostRow]) -> str:
    """Tabella per un'aggregazione (report_by)."""
    lines = [_HEADER]
    for r in rows:
        lines.append(_fmt_row(r.key or "-", r))
    return "\n".join(lines)


def render_total(r: CostRow) -> str:
    """Riga di totale complessivo."""
    return "\n".join([_HEADER, _fmt_row("TOTALE", r)])
