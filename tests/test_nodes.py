"""Test del builder dell'albero di navigazione (D1) per pattern strutturale."""

from poc_istruzioni.serving.nodes import (
    build_tree,
    classify_heading,
    parse_structural_headings,
)


def test_classify_heading() -> None:
    assert classify_heading("9. QUADRO RP – Oneri e spese") == ("quadro", 1)
    assert classify_heading("SEZIONE I – Spese 19%") == ("sezione", 2)
    assert classify_heading("Rigo RP1 Spese sanitarie") == ("rigo", 3)
    assert classify_heading("Righi da RP1 a RP5") == ("rigo", 3)
    assert classify_heading("codice 1 spese sanitarie") == ("codice", 4)
    # rumore / non-strutturale -> None
    assert classify_heading("REDDITI PERSONE FISICHE 2026 - ISTRUZIONI PER LA COMPILAZIONE") is None
    assert classify_heading("ONERI DETRAIBILI") is None


def test_albero_caso_rp6() -> None:
    # Riproduce il caso reale: livelli '#' incoerenti + titolo-doc ripetuto a metà RP.
    md = {
        69: "---\nx: 1\n---\n\n## 9. QUADRO RP – Oneri e spese\n### ONERI DETRAIBILI\n",
        74: "## SEZIONE I – Spese ... 19%\n",
        75: "### Rigo RP1 Spese sanitarie\n",
        77: "# REDDITI PERSONE FISICHE 2026 - ISTRUZIONI PER LA COMPILAZIONE\n"
            "## Rigo RP6 Spese sanitarie rateizzate\n",
    }
    headings = parse_structural_headings(md)
    nodes = build_tree(headings, slice_pages=list(range(69, 78)))

    # il titolo-documento e "ONERI DETRAIBILI" NON sono nodi
    assert all("REDDITI" not in n.title for n in nodes)
    assert all("ONERI DETRAIBILI" not in n.title for n in nodes)

    quadro = next(n for n in nodes if n.kind == "quadro")
    sezione = next(n for n in nodes if n.kind == "sezione")
    righi = [n for n in nodes if n.kind == "rigo"]

    assert quadro.parent_id is None and quadro.level == 1
    assert sezione.parent_id == quadro.id  # SEZIONE figlia di QUADRO ✓
    # RP1 e RP6 entrambi figli di SEZIONE I (non in rami separati) ✓
    assert len(righi) == 2
    assert all(r.parent_id == sezione.id for r in righi)


def test_page_end_clamp_al_blocco() -> None:
    md = {
        69: "## QUADRO RP\n",
        70: "## SEZIONE I\n### Rigo RP1\n",
        72: "### Rigo RP2\n",
    }
    nodes = build_tree(parse_structural_headings(md), slice_pages=list(range(69, 73)))
    rp1 = next(n for n in nodes if "RP1" in n.title)
    assert rp1.page_end == 71  # finisce appena prima di Rigo RP2 (p.72)