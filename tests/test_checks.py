"""Test dei check automatici di qualità VLM (FR-B2, livello A)."""

from poc_istruzioni.ingest.checks import (
    code_pair_mismatches,
    coverage_ratio,
    critical_word_losses,
    extract_numbers,
    find_artifacts,
    has_repetition,
    is_empty_or_refusal,
    lint_headings,
    run_checks,
    token_overlap,
)


def test_extract_numbers_normalizza() -> None:
    nums = extract_numbers("franchigia 129,11 euro, codice 1, limite 1.234,56, 19%")
    assert "129.11" in nums
    assert "1" in nums
    assert "1234.56" in nums
    assert "19" in nums


def test_number_recall_in_run_checks() -> None:
    pdf = "codice 1 franchigia 129,11 limite 530"
    vlm = "codice 1, franchigia 129,11"  # manca 530
    rep = run_checks(vlm, pdf, overlap_threshold=0.0, coverage_min=0.0, coverage_max=99)
    assert "530" in rep.missing_numbers
    assert rep.needs_review is True
    assert any("numeri mancanti" in r for r in rep.reasons)


def test_token_overlap() -> None:
    assert token_overlap("alfa beta gamma", "alfa beta gamma") == 1.0
    assert token_overlap("alfa", "alfa beta") == 0.5  # 1 dei 2 token pdf presenti


def test_coverage_ratio() -> None:
    assert coverage_ratio("abcd", "abcd") == 1.0
    assert coverage_ratio("ab", "abcd") == 0.5


def test_has_repetition() -> None:
    normale = "questa e una frase normale senza ripetizioni evidenti di sorta qui"
    assert has_repetition(normale) is False
    loop = " ".join(["riga uno due tre quattro cinque sei sette otto nove dieci"] * 5)
    assert has_repetition(loop) is True


def test_is_empty_or_refusal() -> None:
    assert is_empty_or_refusal("   ") is True
    assert is_empty_or_refusal("Mi dispiace, ma non posso") is True
    # "non possono" NON deve essere scambiato per un rifiuto
    assert is_empty_or_refusal("Le spese non possono essere dedotte") is False


def test_lint_headings() -> None:
    assert lint_headings("## QUADRO RP\n### Rigo RP1") == []
    assert lint_headings("### Rigo RP1\n## QUADRO RP") != []


def test_find_artifacts() -> None:
    assert find_artifacts("testo REDDITI SC 2023 qui", ("REDDITI SC 2023",)) == ["REDDITI SC 2023"]
    assert find_artifacts("testo pulito", ("REDDITI SC 2023",)) == []


def test_run_checks_pagina_buona() -> None:
    pdf = "QUADRO RP Oneri Righi RP1 RP4 spese sanitarie codice 1 franchigia 129,11"
    vlm = "## QUADRO RP\n### Righi RP1-RP4\nspese sanitarie codice 1 franchigia 129,11"
    rep = run_checks(vlm, pdf)
    assert rep.needs_review is False
    assert rep.reasons == []


def test_run_checks_pagina_cattiva_artefatto() -> None:
    pdf = "QUADRO RP spese sanitarie codice 1"
    vlm = "## QUADRO RP REDDITI SC 2023 spese sanitarie codice 1"
    rep = run_checks(vlm, pdf)
    assert rep.needs_review is True
    assert any("artefatti" in r for r in rep.reasons)


def test_artefatto_nel_riferimento_non_conta_come_numero_mancante() -> None:
    # Il VLM rimuove correttamente "REDDITI SC 2023"; il "2023" è nel solo riferimento.
    pdf = "QUADRO RP REDDITI SC 2023 codice 1 franchigia 129,11"
    vlm = "## QUADRO RP\ncodice 1 franchigia 129,11"
    rep = run_checks(vlm, pdf)
    assert "2023" not in rep.missing_numbers
    assert rep.needs_review is False


def test_numero_di_pagina_escluso_dal_confronto() -> None:
    # "75" è il numero di pagina nel footer del riferimento; il markdown lo omette.
    pdf = "Righi RP1 RP4 codice 1 franchigia 129,11 spese sanitarie 75"
    vlm = "### Righi RP1-RP4\ncodice 1 franchigia 129,11 spese sanitarie"
    assert run_checks(vlm, pdf, page_number=75).needs_review is False
    assert "75" in run_checks(vlm, pdf).missing_numbers  # senza page_number, sarebbe flaggato


def test_pair_check_scambio_etichette() -> None:
    ref = "1 = spese sanitarie; 2 = persone con disabilità"
    swap = "- **1** = persone con disabilità\n- **2** = spese sanitarie"  # etichette invertite
    issues = code_pair_mismatches(swap, ref, label_overlap_min=0.5)
    assert any("codice 1" in i for i in issues)
    ok = "- **1** = spese sanitarie\n- **2** = persone con disabilità"
    assert code_pair_mismatches(ok, ref, label_overlap_min=0.5) == []


def test_critical_word_negazione_persa() -> None:
    ref = "le spese non sono deducibili salvo eccezioni"
    vlm = "le spese sono deducibili salvo eccezioni"  # perso "non"
    losses = critical_word_losses(vlm, ref, ("non", "salvo"))
    assert any("'non'" in x for x in losses)
    # "salvo" presente in entrambi -> non segnalato
    assert not any("'salvo'" in x for x in losses)


def test_pair_e_critical_sono_bloccanti_in_run_checks() -> None:
    ref = "le spese non deducibili; 1 = sanitarie"
    vlm = "le spese deducibili; **1** = altro completamente diverso"
    rep = run_checks(vlm, ref, overlap_threshold=0.0, number_recall_threshold=0.0)
    assert rep.needs_review is True
    assert rep.critical_losses and rep.code_pair_issues


def test_heading_e_copertura_sono_warning_non_bloccanti() -> None:
    # ### prima di ## (pagina di continuazione) + testo fedele -> warning, non needs_review.
    pdf = "Righi RP1 RP4 codice 1 franchigia 129,11 spese sanitarie detrazione"
    vlm = "### Righi RP1-RP4\ncodice 1 franchigia 129,11 spese sanitarie detrazione"
    rep = run_checks(vlm, pdf)
    assert rep.needs_review is False
    assert any("gerarchia heading" in w for w in rep.warnings)
