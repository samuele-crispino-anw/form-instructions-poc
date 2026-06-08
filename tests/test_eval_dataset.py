"""Test del golden set: caricamento, stratificazione, round-trip su eval_cases."""

import json
from pathlib import Path

from poc_istruzioni.eval.dataset import load_cases, stratification

_GOLDEN = Path(__file__).resolve().parents[1] / "config" / "eval" / "rp_golden.yaml"


def test_golden_set_carica_e_e_stratificato() -> None:
    cases = load_cases(_GOLDEN)
    assert len(cases) >= 30
    strat = stratification(cases)
    # tutte le categorie chiave presenti, incluso il fuori_corpus (rifiuto)
    cats = set(strat["categoria"])
    assert {"fattuale", "procedurale", "pin_dependent", "disambiguazione",
            "aggregazione", "fuori_corpus"} <= cats
    assert strat["answerable"]["no"] >= 3            # almeno qualche domanda senza risposta
    assert len(strat["difficolta"]) >= 3             # facile/media/difficile
    assert len(strat["hops"]) >= 3                   # piu' livelli di salti


def test_fuori_corpus_non_answerable() -> None:
    cases = {c.id: c for c in load_cases(_GOLDEN)}
    for c in cases.values():
        if c.categoria == "fuori_corpus":
            assert c.answerable is False and c.expected_target is None


def test_eval_cases_round_trip(tmp_path) -> None:
    from poc_istruzioni.db.connection import connect, init_db
    from poc_istruzioni.db.repositories import get_eval_cases, replace_eval_cases

    c = connect(tmp_path / "e.db")
    init_db(c)
    replace_eval_cases(c, load_cases(_GOLDEN))
    rows = get_eval_cases(c)
    assert len(rows) >= 30
    a = json.loads(rows[0]["attesa_json"])
    assert "answerable" in a and "hops" in a and "expected_target" in a
