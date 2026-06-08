"""Test del generatore HTML dell'explorer di navigazione (D1/D2)."""

from poc_istruzioni.serving.explorer import build_explorer_html
from poc_istruzioni.serving.nodes import Node
from poc_istruzioni.serving.summaries import build_scope_inputs


def _node(nid, parent, kind, level, title, ps, pe):
    return Node(id=nid, parent_id=parent, kind=kind, level=level, title=title,
                page_start=ps, page_end=pe, ord=nid)


def test_html_contiene_struttura_input_e_summary() -> None:
    nodes = [
        _node(1, None, "quadro", 1, "QUADRO RP", 69, 90),
        _node(2, 1, "rigo", 3, "Rigo RP1 Spese sanitarie", 75, 75),
    ]
    md = {75: "### Rigo RP1\nSpese mediche detraibili.\n"}
    scopes = {s.node_id: s for s in build_scope_inputs(nodes, md)}
    summaries = {1: "Ambito oneri e spese.", 2: None}
    out = build_explorer_html(nodes, scopes, summaries, md, doc_id="PF1-2026")

    assert "<!DOCTYPE html>" in out
    assert "QUADRO RP" in out and "Rigo RP1 Spese sanitarie" in out  # struttura
    assert "Ambito oneri e spese." in out                            # summary nel payload
    assert "Spese mediche detraibili." in out                        # pagine markdown
    assert "Sotto-voci contenute" in out                             # input del ramo (figli)
