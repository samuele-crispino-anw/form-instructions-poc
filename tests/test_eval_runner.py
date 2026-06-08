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


def test_retrieval_hit_ignora_qualificatori_verbosi() -> None:
    # i casi che la vecchia metrica contava come miss ma che erano nodo-giusto
    assert retrieval_hit("Rigo RP71, codice 4", "Rigo RP71 Inquilini di alloggi") is True
    assert retrieval_hit("Rigo RP90 (art. 188-bis TUIR)", "Rigo RP90 — Redditi prodotti") is True
    assert retrieval_hit("Sezione III-B (RP51-RP53)", "Sezione III B – Dati catastali") is True
    assert retrieval_hit("Righi RP51-RP52, col. 7", "Righi RP51 e RP52 - Dati catastali") is True
    # word-boundary: RP1 non deve matchare RP10
    assert retrieval_hit("RP1", "Rigo RP10 Spese") is False


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
