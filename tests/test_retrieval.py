"""Test della logica pura dell'orchestratore retrieval (gate + assembly)."""

from types import SimpleNamespace

from poc_istruzioni.serving.nodes import Node
from poc_istruzioni.serving.pins import Pin
from poc_istruzioni.serving.retrieval import (
    build_served_context,
    classify_fastpath,
    navigate_hierarchical,
    served_page_range,
)


class _FakeClient:
    """Client LLM finto: restituisce in sequenza le risposte scriptate."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0

    def complete(self, **kw):
        text = self.answers[self.calls]
        self.calls += 1
        return SimpleNamespace(text=text, cost=SimpleNamespace(usd=0.001))


def _tree():
    return [
        Node(1, None, "quadro", 1, "QUADRO RP", 69, 133, 1),
        Node(2, 1, "sezione", 2, "SEZIONE I spese 19%", 74, 89, 2),
        Node(3, 1, "sezione", 2, "SEZIONE II deduzioni", 90, 97, 3),
        Node(4, 2, "rigo", 3, "Rigo RP1 Spese sanitarie", 75, 75, 4),
        Node(5, 2, "rigo", 3, "Rigo RP7 Interessi mutuo", 78, 79, 5),
    ]


def test_navigate_hierarchical_scende_fino_alla_foglia() -> None:
    nodes = _tree()
    summ = {n.id: n.title for n in nodes}
    # auto-descend del quadro (figlio unico), poi sceglie SEZIONE I (2), poi Rigo RP1 (4)
    client = _FakeClient(["2", "4"])
    target, cost, path = navigate_hierarchical(client, "spese mediche", nodes, summ,
                                               model="m", system_prompt="p")
    assert target == 4 and path == [1, 2, 4]
    assert client.calls == 2 and round(cost, 3) == 0.002  # 1 call per livello, quadro auto


def test_navigate_hierarchical_nessuna_rifiuta() -> None:
    nodes = _tree()
    summ = {n.id: n.title for n in nodes}
    client = _FakeClient(["NESSUNA"])  # nessuna sezione pertinente -> rifiuto
    target, _c, _p = navigate_hierarchical(client, "quadro RW estero", nodes, summ,
                                           model="m", system_prompt="p")
    assert target is None


def test_navigate_hierarchical_ferma_a_livello_sezione() -> None:
    nodes = _tree()
    summ = {n.id: n.title for n in nodes}
    client = _FakeClient(["2", "FERMA"])  # scende a SEZIONE I, poi si ferma lì
    target, _c, path = navigate_hierarchical(client, "panoramica spese 19%", nodes, summ,
                                             model="m", system_prompt="p")
    assert target == 2 and path == [1, 2]


def test_gate_netto_quando_top1_alto_e_distante() -> None:
    g, _ = classify_fastpath([(7, 129.0), (3, 39.0)], min_abs=8.0, margin=1.5)
    assert g == "netto"


def test_gate_ambiguo_per_margine_stretto() -> None:
    g, why = classify_fastpath([(1, 50.0), (2, 46.0)], min_abs=8.0, margin=1.5)
    assert g == "ambiguo" and "margine" in why


def test_gate_ambiguo_per_punteggio_basso() -> None:
    g, why = classify_fastpath([(9, 4.9), (1, 4.5)], min_abs=8.0, margin=1.5)
    assert g == "ambiguo" and "soglia_assoluta" in why


def test_gate_vuoto_senza_candidati() -> None:
    g, _ = classify_fastpath([], min_abs=8.0, margin=1.5)
    assert g == "vuoto"


def test_gate_netto_con_unico_candidato() -> None:
    g, _ = classify_fastpath([(5, 20.0)], min_abs=8.0, margin=1.5)
    assert g == "netto"  # nessun top2 -> margine infinito


def test_build_served_context_mette_i_pin_prima_della_voce() -> None:
    pins = [Pin(1, "quadro", "QUADRO RP", "Regola del quadro."),
            Pin(2, "sezione", "SEZIONE I", "Franchigia sulle spese.")]
    out = build_served_context("Rigo RP1 Spese sanitarie", "Dettaglio del rigo.", pins)
    assert out.index("REGOLE GOVERNANTI") < out.index("VOCE")
    assert "Franchigia sulle spese." in out and "Dettaglio del rigo." in out


def test_build_served_context_senza_pin() -> None:
    out = build_served_context("Rigo RP1", "Testo.", [])
    assert "REGOLE GOVERNANTI" not in out and "Testo." in out


def test_served_page_range_estende_alla_continuazione() -> None:
    # RP90 (p.132) col nodo successivo RP91 a p.133 -> serve 132-133 (cattura la coda su p.133)
    assert served_page_range(132, 132, [110, 128, 132, 133]) == (132, 133)
    # ultimo nodo: nessun successivo -> resta il proprio range
    assert served_page_range(133, 133, [110, 132, 133]) == (133, 133)
    # nodo che già copre più pagine, prossimo nodo subito dopo
    assert served_page_range(78, 79, [75, 78, 80]) == (78, 80)
