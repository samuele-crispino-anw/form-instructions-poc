"""Test della catena di escalation per pagina (convert_page), in mock."""

from types import SimpleNamespace

import pytest

from poc_istruzioni.config import (
    CachePricing,
    Currency,
    ModelPrice,
    Prices,
    load_settings,
)
from poc_istruzioni.db.connection import connect, init_db
from poc_istruzioni.ingest.convert import convert_page
from poc_istruzioni.llm.client import LlmClient

SETTINGS = load_settings()  # default reale: economical_first=false (parti da Opus)
# Variante economica (Haiku-first) per i test della catena graduata.
ECON = SETTINGS.model_copy(
    update={"escalation": SETTINGS.escalation.model_copy(update={"economical_first": True})}
)

PRICES = Prices(
    updated="t",
    models={
        "claude-haiku-4-5": ModelPrice(input_per_mtok=1.0, output_per_mtok=5.0),
        "claude-opus-4-8": ModelPrice(input_per_mtok=5.0, output_per_mtok=25.0),
    },
    cache=CachePricing(read_multiplier=0.10, write_5m_multiplier=1.25, write_1h_multiplier=2.00),
    currency=Currency(usd_to_eur=0.87),
)

REF = "codice 1 franchigia 129,11 spese sanitarie detrazione"
GOOD = "## QUADRO RP\ncodice 1 franchigia 129,11 spese sanitarie detrazione"
BAD = "## QUADRO RP\ncodice 1 spese sanitarie detrazione"  # manca 129,11 -> gate boccia


def _usage():
    return SimpleNamespace(
        input_tokens=500, output_tokens=200,
        cache_read_input_tokens=0, cache_creation_input_tokens=0,
    )


class ByModel:
    """create() ritorna GOOD per Opus, BAD per Haiku (simula escalation che ripara)."""

    def create(self, **kw):
        text = GOOD if "opus" in kw["model"] else BAD
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], usage=_usage())


class Always:
    def __init__(self, text):
        self.text = text

    def create(self, **kw):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.text)], usage=_usage()
        )


def _fake(messages):
    return SimpleNamespace(messages=messages)


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "c.db")
    init_db(c)
    yield c
    c.close()


def _call(conn, client, route, tmp_path, *, settings=ECON, force_strong=False):
    img = tmp_path / "p001.png"
    img.write_bytes(b"\x89PNGFAKE")
    return convert_page(
        LlmClient(conn, PRICES, client=client),
        route=route, page_n=1, cues_text="dummy", image_path=img, ref_text=REF,
        settings=settings, prompt_text="PA", prompt_vision="PB",
        boilerplate=frozenset(), force_strong=force_strong,
    )


def test_economica_haiku_passa_subito(conn, tmp_path) -> None:
    # economical_first=True: la Rotta A parte da Haiku
    out = _call(conn, _fake(Always(GOOD)), "A", tmp_path, settings=ECON)
    assert out.status == "ok"
    assert out.escalations == 0
    assert "haiku" in out.model_used


def test_economica_escalation_haiku_a_opus(conn, tmp_path) -> None:
    out = _call(conn, _fake(ByModel()), "A", tmp_path, settings=ECON)
    assert out.status == "ok"
    assert out.escalations == 1  # Haiku fallita, Opus ripara
    assert "opus" in out.model_used


def test_default_sicuro_parte_da_opus(conn, tmp_path) -> None:
    # default PoC (economical_first=false): la Rotta A parte da Opus, niente Haiku
    out = _call(conn, _fake(ByModel()), "A", tmp_path, settings=SETTINGS)
    assert out.status == "ok"
    assert out.escalations == 0  # Opus passa al primo colpo
    assert "opus" in out.model_used


def test_force_strong_parte_da_opus(conn, tmp_path) -> None:
    out = _call(conn, _fake(ByModel()), "A", tmp_path, settings=ECON, force_strong=True)
    assert out.status == "ok"
    assert out.escalations == 0  # parte già forte (circuit breaker)
    assert "opus" in out.model_used


def test_tutto_fallisce_needs_human(conn, tmp_path) -> None:
    out = _call(conn, _fake(Always(BAD)), "A", tmp_path, settings=ECON)
    assert out.status == "needs_human"
    assert out.escalations == 2  # haiku -> opus -> vlm, tutti falliti
    assert out.reasons  # motivi dell'ultimo tentativo


def test_route_b_usa_vlm(conn, tmp_path) -> None:
    out = _call(conn, _fake(Always(GOOD)), "B", tmp_path, settings=SETTINGS)
    assert out.status == "ok"
    assert out.route == "B"
    assert out.escalations == 0


def test_audit_diff() -> None:
    from poc_istruzioni.ingest.convert import _audit_diff

    cw = ["non"]
    assert _audit_diff("codice 1 importo 100", "codice 1 importo 100", cw) is False
    assert _audit_diff("codice 1", "codice 1 importo 100", cw) is True  # numeri diversi
    assert _audit_diff("spese non deducibili", "spese deducibili", cw) is True  # 'non' diverso


class Echo:
    """Per la Rotta A echeggia l'input (md fedele al testo pagina -> gate passa)."""

    def create(self, **kw):
        content = kw["messages"][0]["content"]
        if isinstance(content, str):
            text = "## QUADRO RP\n" + content.replace("〖H〗 ", "")
        else:
            text = GOOD
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], usage=_usage())


def test_convert_document_integrazione(conn, tmp_path) -> None:
    import fitz

    from poc_istruzioni.db.repositories import governance
    from poc_istruzioni.ingest.convert import convert_document

    # 2 pagine DISTINTE single_column (>=18 parole -> non anomalous, niente boilerplate spurio)
    extra = "alfa beta gamma delta epsilon zeta eta theta iota kappa lambda mu"
    bodies = [
        f"codice 1 franchigia 129,11 spese sanitarie detrazione {extra}",
        f"codice 2 detrazione spese universitarie mediche aliquota 19 per cento {extra}",
    ]
    doc = fitz.open()
    for b in bodies:
        doc.new_page().insert_textbox(fitz.Rect(50, 50, 540, 750), b, fontsize=11)
    pdf = tmp_path / "d.pdf"
    doc.save(str(pdf))
    doc.close()

    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    for n in (1, 2):
        (pages_dir / f"p{n:03d}.png").write_bytes(b"\x89PNGFAKE")

    summary = convert_document(
        conn, LlmClient(conn, PRICES, client=_fake(Echo())),
        doc_id="PF1-2026", pdf_path=pdf, pages_dir=pages_dir, markdown_dir=tmp_path / "md",
        settings=SETTINGS, prompt_text="PA", prompt_vision="PB",
    )
    assert summary.pages == 2
    assert summary.route_a == 2 and summary.needs_human == 0
    md_file = tmp_path / "md" / "PF1-2026" / "pages" / "p001.md"
    assert md_file.exists()
    # frontmatter di provenienza presente in testa al file
    content = md_file.read_text()
    assert content.startswith("---\n")
    assert "modello:" in content and "generato_il:" in content and "rotta:" in content
    assert governance(conn, "PF1-2026")["pages"] == 2


def test_convert_document_pagina_bloccata_genera_report(conn, tmp_path) -> None:
    import fitz

    from poc_istruzioni.ingest.convert import convert_document

    body = "codice 1 franchigia 129,11 spese sanitarie detrazione " + " ".join(
        f"voce{i}" for i in range(15)
    )
    doc = fitz.open()
    doc.new_page().insert_textbox(fitz.Rect(50, 50, 540, 750), body, fontsize=11)
    pdf = tmp_path / "d.pdf"
    doc.save(str(pdf))
    doc.close()
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "p001.png").write_bytes(b"\x89PNGFAKE")

    # output con simbolo doppio -> il lint blocca su ogni tier -> needs_human
    bad = "## QUADRO RP\ncodice 1 franchigia 129,11 spese sanitarie detrazione 1,73%%"
    summary = convert_document(
        conn, LlmClient(conn, PRICES, client=_fake(Always(bad))),
        doc_id="PF1-2026", pdf_path=pdf, pages_dir=pages_dir, markdown_dir=tmp_path / "md",
        settings=SETTINGS, prompt_text="PA", prompt_vision="PB",
    )
    assert summary.needs_human == 1
    report = tmp_path / "md" / "PF1-2026" / "needs_review.html"
    assert report.exists()
    html = report.read_text()
    assert "DA RIVEDERE" in html
    assert "simbolo doppio" in html
