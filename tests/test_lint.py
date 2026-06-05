"""Test del lint d'igiene FR-B3 (§B.2)."""

from poc_istruzioni.ingest.lint import lint_markdown


def test_markdown_pulito_passa() -> None:
    md = "## QUADRO RP\n### Rigo RP1\n- **1** = spese sanitarie\nfranchigia 129,11"
    res = lint_markdown(md)
    assert res.ok
    assert res.fails == []


def test_dingbat_non_mappato_blocca() -> None:
    res = lint_markdown("## QUADRO RP\nn spese mediche detraibili")
    assert not res.ok
    assert any("dingbat" in f for f in res.fails)


def test_simbolo_doppio_blocca() -> None:
    res = lint_markdown("detrazione del 1,73%% sulle spese")
    assert not res.ok
    assert any("simbolo doppio" in f for f in res.fails)


def test_header_nel_corpo_blocca() -> None:
    res = lint_markdown(
        "## QUADRO RP\nIstruzioni PF 2026\ntesto", boilerplate={"Istruzioni PF 2026"}
    )
    assert not res.ok
    assert any("header/footer" in f for f in res.fails)


def test_numero_pagina_orfano_blocca() -> None:
    res = lint_markdown("## QUADRO RP\ntesto\n75", page_number=75)
    assert not res.ok
    assert any("numero di pagina" in f for f in res.fails)


def test_stringa_orfana_e_heading_dup_sono_warning() -> None:
    md = "## QUADRO RP\n## QUADRO RP\nAgenzia Entrate\ntesto"
    res = lint_markdown(md, orphan_warn_strings=("Agenzia Entrate",))
    assert res.ok  # solo warning, non blocca
    assert any("orfana" in w for w in res.warnings)
    assert any("duplicati" in w for w in res.warnings)
