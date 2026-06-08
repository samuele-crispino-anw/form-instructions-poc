"""Test del builder deterministico degli input scope-aware (D2)."""

from poc_istruzioni.serving.nodes import Node
from poc_istruzioni.serving.summaries import build_scope_inputs


def _node(nid, parent, kind, level, title, ps, pe):
    return Node(id=nid, parent_id=parent, kind=kind, level=level, title=title,
                page_start=ps, page_end=pe, ord=nid)


def test_ramo_usa_titoli_figli_foglia_usa_testo() -> None:
    nodes = [
        _node(1, None, "quadro", 1, "QUADRO RP", 69, 90),
        _node(2, 1, "sezione", 2, "SEZIONE I", 74, 89),
        _node(3, 2, "rigo", 3, "Rigo RP1 Spese sanitarie", 75, 75),
    ]
    md = {75: "---\nx: 1\n---\n\n### Rigo RP1\nSpese sani\xad\ntarie sostenute nell'anno.\n"}
    by_id = {s.node_id: s for s in build_scope_inputs(nodes, md)}

    # QUADRO (ramo) -> non foglia, usa i titoli dei figli, niente testo proprio
    assert by_id[1].is_leaf is False
    assert by_id[1].child_titles == ["SEZIONE I"]
    assert by_id[1].own_text == ""

    # SEZIONE (ramo) -> figli = il rigo
    assert by_id[2].child_titles == ["Rigo RP1 Spese sanitarie"]

    # Rigo (foglia) -> testo delle pagine, senza frontmatter e de-ifenato
    leaf = by_id[3]
    assert leaf.is_leaf is True
    assert leaf.child_titles == []
    assert "x: 1" not in leaf.own_text          # frontmatter rimosso
    assert "Spese sanitarie" in leaf.own_text   # "sani-\ntarie" ricongiunto


def test_troncamento_testo_foglia() -> None:
    nodes = [_node(1, None, "rigo", 3, "Rigo RP1", 75, 75)]
    md = {75: "A" * 10_000}
    [s] = build_scope_inputs(nodes, md, max_own_chars=100)
    assert len(s.own_text) == 100
