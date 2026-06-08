"""Test del pinning deterministico (preambolo governante + raccolta antenati)."""

from poc_istruzioni.serving.nodes import Node
from poc_istruzioni.serving.pins import build_pins, collect_pins, extract_preamble


def _node(nid, parent, kind, level, title, ps, pe):
    return Node(id=nid, parent_id=parent, kind=kind, level=level, title=title,
                page_start=ps, page_end=pe, ord=nid)


def test_extract_preamble_si_ferma_al_primo_figlio() -> None:
    quadro = _node(1, None, "quadro", 1, "QUADRO RP", 69, 70)
    md = {
        69: "## QUADRO RP\nIstruzioni generali del quadro: definizione di familiare a carico.\n"
            "### Rigo RP1\nTesto del rigo, da NON includere nel preambolo.\n",
    }
    pre = extract_preamble(quadro, md)
    assert "familiare a carico" in pre
    assert "Testo del rigo" not in pre  # si ferma al primo heading strutturale (Rigo RP1)


def test_build_e_collect_pins_risale_gli_antenati() -> None:
    nodes = [
        _node(1, None, "quadro", 1, "QUADRO RP", 69, 75),
        _node(2, 1, "sezione", 2, "SEZIONE I", 74, 75),
        _node(3, 2, "rigo", 3, "Rigo RP1", 75, 75),
    ]
    md = {
        69: "## QUADRO RP\nRegola del quadro.\n",
        74: "## SEZIONE I\nRegola della sezione: franchigia sulle spese.\n",
        75: "### Rigo RP1\nDettaglio rigo.\n",
    }
    pins = build_pins(nodes, md)
    owners = {p.owner_node_id for p in pins}
    assert owners == {1, 2}  # solo i rami (quadro, sezione); il rigo foglia non è owner

    pinned = collect_pins(3, nodes, pins)  # per il Rigo RP1
    assert [p.owner_kind for p in pinned] == ["quadro", "sezione"]  # radice -> giù
    assert "franchigia" in pinned[1].text


def test_collect_pins_radice_senza_antenati_vuoto() -> None:
    nodes = [_node(1, None, "quadro", 1, "QUADRO RP", 69, 70)]
    md = {69: "## QUADRO RP\nRegola.\n"}
    assert collect_pins(1, nodes, build_pins(nodes, md)) == []


def test_pins_repo_round_trip(tmp_path) -> None:
    from poc_istruzioni.db.connection import connect, init_db
    from poc_istruzioni.db.repositories import get_pins, replace_pins

    c = connect(tmp_path / "p.db")
    init_db(c)
    nodes = [
        _node(1, None, "quadro", 1, "QUADRO RP", 69, 75),
        _node(2, 1, "sezione", 2, "SEZIONE I", 74, 75),
        _node(3, 2, "rigo", 3, "Rigo RP1", 75, 75),
    ]
    md = {69: "## QUADRO RP\nRegola quadro.\n", 74: "## SEZIONE I\nRegola sezione.\n",
          75: "### Rigo RP1\nDettaglio.\n"}
    replace_pins(c, "DOC", build_pins(nodes, md), source="preamble", run_id="run_x", ts="t")
    rows = get_pins(c, "DOC")
    assert {r["owner_node_id"] for r in rows} == {1, 2}
    assert any("Regola sezione" in r["text"] for r in rows)
