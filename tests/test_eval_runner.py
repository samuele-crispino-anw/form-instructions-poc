"""Test dei pezzi deterministici del runner di eval: giudice e aggregazione report."""

from poc_istruzioni.eval.judge import is_refusal, must_include_coverage, retrieval_hit
from poc_istruzioni.eval.report import summarize


def test_is_refusal() -> None:
    assert is_refusal("Le istruzioni fornite non contengono la risposta a questa domanda.")
    assert not is_refusal("La detrazione spetta al 19%.")


def test_must_include_coverage_normalizza() -> None:
    ans = 'La detrazione è del 19% oltre la franchigia di 129,11 euro.'
    hit, tot = must_include_coverage(ans, ["19%", "129,11", "scontrino"])
    assert (hit, tot) == (2, 3)
    assert must_include_coverage(ans, []) == (0, 0)


def test_retrieval_hit() -> None:
    assert retrieval_hit("RP7", "Rigo RP7 Interessi per mutui ipotecari") is True
    assert retrieval_hit('codice 29', 'Codice "29" (Spese veterinarie)') is True
    assert retrieval_hit("RP7", "Rigo RP1 Spese sanitarie") is False
    assert retrieval_hit(None, "qualsiasi") is None       # fuori_corpus: non applicabile
    assert retrieval_hit("RP7", None) is False            # retrieval ha rifiutato


def test_summarize_calcola_metriche_per_gruppo() -> None:
    results = [
        {"arm": "navigazione", "origin": "external", "correct": True,
         "retrieval_hit": True, "cost_usd": 0.02, "latency_ms": 1000},
        {"arm": "navigazione", "origin": "external", "correct": False,
         "retrieval_hit": False, "cost_usd": 0.04, "latency_ms": 3000},
        {"arm": "servi_intero", "origin": "external", "correct": True,
         "retrieval_hit": None, "cost_usd": 0.10, "latency_ms": 2000},
    ]
    s = summarize(results, ["arm"])
    nav = s[("navigazione",)]
    assert nav["n"] == 2 and nav["correct"] == 1 and nav["correct_pct"] == 50.0
    assert nav["retr_hit_pct"] == 50.0
    # servi_intero non ha retrieval-hit applicabile -> None
    assert s[("servi_intero",)]["retr_hit_pct"] is None
    assert s[("servi_intero",)]["cost_usd"] == 0.10
