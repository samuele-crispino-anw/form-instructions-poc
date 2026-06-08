"""Test del logger Q&A markdown strutturato."""

from poc_istruzioni.tracing.qa_log import QaLog, fence


def test_render_sezioni_ordinate_e_numerate() -> None:
    log = QaLog(query_id="run_x", ts="2026-06-08T00:00:00Z", doc_id="PF1-2026", query="domanda?")
    log.section("Query utente", fence("domanda?"))
    log.section("Retrieval", "gate netto")
    log.section("Risposta", fence("ecco la risposta"))
    md = log.render()

    assert md.startswith("# Q&A log — run_x")
    assert "**query:** domanda?" in md
    assert "## 1. Query utente" in md
    assert "## 2. Retrieval" in md
    assert "## 3. Risposta" in md
    # ordine preservato
    assert md.index("## 1.") < md.index("## 2.") < md.index("## 3.")
    assert "```\ndomanda?\n```" in md


def test_write_crea_il_file(tmp_path) -> None:
    log = QaLog(query_id="run_y", ts="t", doc_id="D", query="q")
    log.section("X", "y")
    p = log.write(tmp_path / "logs")
    assert p.exists() and p.name == "qa_run_y.md"
    assert "## 1. X" in p.read_text(encoding="utf-8")
