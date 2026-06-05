"""Test dell'orchestrazione transcribe_pages (mock, nessuna chiamata reale)."""

from types import SimpleNamespace

import pytest

from poc_istruzioni.config import CachePricing, Currency, ModelPrice, Prices
from poc_istruzioni.db.connection import connect, init_db
from poc_istruzioni.db.repositories import Document, Page, get_pages, insert_document, insert_page
from poc_istruzioni.ingest.pipeline import transcribe_pages
from poc_istruzioni.llm.client import LlmClient

PRICES = Prices(
    updated="t",
    models={"claude-opus-4-8": ModelPrice(input_per_mtok=5.0, output_per_mtok=25.0)},
    cache=CachePricing(read_multiplier=0.10, write_5m_multiplier=1.25, write_1h_multiplier=2.00),
    currency=Currency(usd_to_eur=0.87),
)

VLM_MD = "## QUADRO RP codice 1"  # output finto, uguale per ogni pagina


class FakeMessages:
    def create(self, **kwargs):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=VLM_MD)],
            usage=SimpleNamespace(
                input_tokens=1000, output_tokens=200,
                cache_read_input_tokens=0, cache_creation_input_tokens=0,
            ),
        )


class FakeAnthropic:
    def __init__(self):
        self.messages = FakeMessages()


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "poc.db")
    init_db(c)
    yield c
    c.close()


def test_transcribe_pages_orchestrazione(conn, tmp_path) -> None:
    # Setup: documento + 2 pagine "renderizzate" con PNG fittizi.
    insert_document(
        conn,
        Document(id="PF1-2026", modello="m", edizione="2026", periodo_imposta="2025",
                 sha256="x", path="p.pdf"),
    )
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    for n in (1, 2):
        (pages_dir / f"p{n:03d}.png").write_bytes(b"\x89PNGFAKE")
        insert_page(conn, Page(doc_id="PF1-2026", n=n, png_path=f"p{n:03d}.png", png_sha="s"))

    # Riferimenti: pagina 1 coerente col markdown; pagina 2 contiene un numero mancante.
    ref_texts = {
        1: "QUADRO RP codice 1",
        2: "QUADRO RP codice 1 importo 999",  # 999 e 'importo' assenti nel markdown
    }

    summary = transcribe_pages(
        conn,
        LlmClient(conn, PRICES, client=FakeAnthropic()),
        doc_id="PF1-2026",
        page_numbers=[1, 2],
        pages_dir=pages_dir,
        markdown_dir=tmp_path / "md",
        ref_texts=ref_texts,
        model="claude-opus-4-8",
        prompt="ISTRUZIONI",
        review_path=tmp_path / "review.html",
        title="Calibrazione",
    )

    # Riepilogo: 2 pagine, 1 da rivedere (la 2).
    assert summary.pages == 2
    assert summary.needs_review == 1
    # costo: 2 chiamate * (1000*5 + 200*25)/1e6 = 2 * 0.01 = 0.02 USD
    assert summary.usd == pytest.approx(0.02)

    # markdown salvati su disco
    assert (tmp_path / "md" / "PF1-2026" / "pages" / "p001.md").exists()
    # review HTML generata
    assert summary.review_path.exists()

    # DB aggiornato: pagina 1 ok, pagina 2 needs_review
    by_n = {p.n: p for p in get_pages(conn, "PF1-2026")}
    assert by_n[1].vlm_status == "ok"
    assert by_n[2].vlm_status == "needs_review"
    assert by_n[2].needs_review is True


def _setup_one_page(conn, tmp_path):
    insert_document(
        conn,
        Document(id="PF1-2026", modello="m", edizione="2026", periodo_imposta="2025",
                 sha256="x", path="p.pdf"),
    )
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "p001.png").write_bytes(b"\x89PNGFAKE")
    insert_page(conn, Page(doc_id="PF1-2026", n=1, png_path="p001.png", png_sha="s"))
    return pages_dir


def test_skip_existing_non_richiama_ne_addebita(conn, tmp_path) -> None:
    pages_dir = _setup_one_page(conn, tmp_path)
    # markdown già presente -> deve essere riusato, niente chiamata
    md_dir = tmp_path / "md" / "PF1-2026" / "pages"
    md_dir.mkdir(parents=True)
    (md_dir / "p001.md").write_text("## QUADRO RP codice 1", encoding="utf-8")

    summary = transcribe_pages(
        conn, LlmClient(conn, PRICES, client=FakeAnthropic()),
        doc_id="PF1-2026", page_numbers=[1], pages_dir=pages_dir,
        markdown_dir=tmp_path / "md", ref_texts={1: "QUADRO RP codice 1"},
        model="claude-opus-4-8", prompt="P",
        review_path=tmp_path / "r.html", title="T",
    )
    assert summary.transcribed == 0
    assert summary.skipped == 1
    assert summary.usd == 0.0
    assert summary.pages == 1  # comunque presente in review


class FlakyMessages:
    """Solleva alla prima create, poi risponde (simula un 529 transitorio)."""

    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("Overloaded 529")
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="## QUADRO RP codice 1")],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=200,
                                  cache_read_input_tokens=0, cache_creation_input_tokens=0),
        )


class FlakyAnthropic:
    def __init__(self):
        self.messages = FlakyMessages()


def test_errore_pagina_isolato_non_interrompe_batch(conn, tmp_path) -> None:
    insert_document(
        conn,
        Document(id="PF1-2026", modello="m", edizione="2026", periodo_imposta="2025",
                 sha256="x", path="p.pdf"),
    )
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    for n in (1, 2):
        (pages_dir / f"p{n:03d}.png").write_bytes(b"\x89PNGFAKE")
        insert_page(conn, Page(doc_id="PF1-2026", n=n, png_path=f"p{n:03d}.png", png_sha="s"))

    summary = transcribe_pages(
        conn, LlmClient(conn, PRICES, client=FlakyAnthropic()),
        doc_id="PF1-2026", page_numbers=[1, 2], pages_dir=pages_dir,
        markdown_dir=tmp_path / "md", ref_texts={1: "x", 2: "QUADRO RP codice 1"},
        model="claude-opus-4-8", prompt="P",
        review_path=tmp_path / "r.html", title="T",
    )
    # pagina 1 fallita (isolata), pagina 2 riuscita; review comunque generata
    assert summary.failed == [1]
    assert summary.transcribed == 1
    assert summary.pages == 1
    assert summary.review_path.exists()
