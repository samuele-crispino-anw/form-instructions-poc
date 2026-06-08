"""Test della logica pura dell'orchestratore retrieval (gate + assembly)."""

from poc_istruzioni.serving.pins import Pin
from poc_istruzioni.serving.retrieval import build_served_context, classify_fastpath


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
