"""CLI del PoC. I comandi vengono aggiunti per fase."""

from __future__ import annotations

import typer

from poc_istruzioni import __version__

app = typer.Typer(
    help="PoC Istruzioni — assistente Q&A sui modelli dichiarativi",
    no_args_is_help=True,
)

report_app = typer.Typer(help="Contabilità chiamate e costi (FR-T2).")
app.add_typer(report_app, name="report")

ingest_app = typer.Typer(help="Ingestion del corpus (Stadio B).")
app.add_typer(ingest_app, name="ingest")

# Default del corpus pilota: Redditi PF Fascicolo 1, edizione 2026.
_PILOT_PDF = "PF1_istruzioni_2026_agg 13 05 2026.pdf"


@app.callback()
def main() -> None:
    """Entrypoint del PoC. I sottocomandi vengono aggiunti per fase."""


@app.command()
def version() -> None:
    """Stampa la versione del PoC."""
    typer.echo(__version__)


@report_app.command("costs")
def report_costs(
    by: str = typer.Option(
        None, "--by", help="Aggrega per: purpose | day | query | model. Omesso = totale."
    ),
) -> None:
    """Mostra i costi dal ledger (totale o aggregati)."""
    from poc_istruzioni.bootstrap import build_context
    from poc_istruzioni.ledger.report import render_rows, render_total
    from poc_istruzioni.ledger.store import report_by, total

    ctx = build_context()
    if by is None:
        typer.echo(render_total(total(ctx.conn)))
        return
    try:
        rows = report_by(ctx.conn, by)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from None
    typer.echo(render_rows(rows))


@ingest_app.command("render")
def ingest_render(
    doc_id: str = typer.Option("PF1-2026", help="Identificatore documento."),
    modello: str = typer.Option("REDDITI-PF-F1", help="Modello dichiarativo."),
    edizione: str = typer.Option("2026", help="Edizione delle istruzioni."),
    periodo_imposta: str = typer.Option("2025", help="Periodo d'imposta."),
    agg_data: str = typer.Option("2026-05-13", help="Data aggiornamento edizione."),
    pdf: str = typer.Option(None, help="Percorso PDF (default: corpus pilota in raw_dir)."),
) -> None:
    """FR-B1: renderizza il PDF in PNG per pagina e registra documento e pagine."""
    from poc_istruzioni.bootstrap import build_context, resolve_path
    from poc_istruzioni.ingest.pipeline import render_document

    ctx = build_context()
    pdf_path = resolve_path(pdf) if pdf else resolve_path(ctx.settings.paths.raw_dir) / _PILOT_PDF
    pages_dir = resolve_path(ctx.settings.paths.pages_dir) / doc_id

    if not pdf_path.exists():
        raise typer.BadParameter(f"PDF non trovato: {pdf_path}")

    typer.echo(f"Rendering {pdf_path.name} -> {pages_dir} a {ctx.settings.rendering.dpi} DPI ...")
    n = render_document(
        ctx.conn,
        doc_id=doc_id,
        modello=modello,
        edizione=edizione,
        periodo_imposta=periodo_imposta,
        agg_data=agg_data,
        pdf_path=pdf_path,
        pages_dir=pages_dir,
        dpi=ctx.settings.rendering.dpi,
    )
    typer.echo(f"OK: {n} pagine renderizzate e registrate (doc_id={doc_id}).")


@ingest_app.command("layout")
def ingest_layout(
    doc_id: str = typer.Option("PF1-2026", help="Identificatore documento."),
    pdf: str = typer.Option(None, help="Percorso PDF (default: corpus pilota)."),
) -> None:
    """Nota strategica §2: analizza il layout di tutte le pagine e scrive layout_analysis.csv."""
    from poc_istruzioni.bootstrap import resolve_path
    from poc_istruzioni.config import load_settings
    from poc_istruzioni.ingest.layout import analyze_document, summarize, write_csv

    settings = load_settings()
    pdf_path = resolve_path(pdf) if pdf else resolve_path(settings.paths.raw_dir) / _PILOT_PDF
    if not pdf_path.exists():
        raise typer.BadParameter(f"PDF non trovato: {pdf_path}")

    typer.echo(f"Analisi layout di {pdf_path.name} ...")
    metrics = analyze_document(pdf_path)
    out = resolve_path(settings.paths.markdown_dir) / doc_id / "layout_analysis.csv"
    write_csv(metrics, out)

    counts = summarize(metrics)
    total = len(metrics)
    typer.echo(f"\n{total} pagine analizzate. Distribuzione classi:")
    for cls, n in counts.items():
        pct = 100 * n / total if total else 0
        typer.echo(f"  {cls:<14} {n:>4}  ({pct:.1f}%)")

    anomalous = [m.page for m in metrics if m.classification == "anomalous"]
    table = [m.page for m in metrics if m.classification == "table_heavy"]
    multi = [m.page for m in metrics if m.classification == "multi_column"]
    typer.echo(f"\nmulti_column: {multi}")
    typer.echo(f"table_heavy:  {table}")
    typer.echo(f"anomalous:    {anomalous}")
    typer.echo(f"\nCSV: {out}")


# Campione stratificato di default per lo spike (copre tutte le classi di layout):
# single_column: 6,62,75,146,180 · table_heavy: 4,73,117,181 · anomalous: 1
_SPIKE_SAMPLE = "1,4,6,62,73,75,117,146,180,181"


@ingest_app.command("spike")
def ingest_spike(
    pages: str = typer.Option(_SPIKE_SAMPLE, help="Pagine del campione, es. '1,4,75'."),
    doc_id: str = typer.Option("PF1-2026", help="Identificatore documento."),
    pdf: str = typer.Option(None, help="Percorso PDF (default: corpus pilota)."),
) -> None:
    """Nota strategica §3: spike comparativo Rotta A (testo) vs B (VLM) sul campione.

    Effettua chiamate a pagamento (entrambe le rotte). Richiede ANTHROPIC_API_KEY.
    """
    from poc_istruzioni.bootstrap import build_context, resolve_path
    from poc_istruzioni.config import load_prompt
    from poc_istruzioni.ingest.layout import analyze_document
    from poc_istruzioni.ingest.spike import (
        build_spike_html,
        run_spike,
        summarize_by_class,
        write_spike_csv,
    )
    from poc_istruzioni.ingest.textlayer import (
        extract_pages_text,
        find_boilerplate_lines,
        strip_lines,
    )
    from poc_istruzioni.llm.client import LlmClient

    ctx = build_context()
    sample = [int(x) for x in pages.split(",") if x.strip()]
    pdf_path = resolve_path(pdf) if pdf else resolve_path(ctx.settings.paths.raw_dir) / _PILOT_PDF
    if not pdf_path.exists():
        raise typer.BadParameter(f"PDF non trovato: {pdf_path}")

    pages_text = extract_pages_text(pdf_path)
    boiler = find_boilerplate_lines(pages_text)
    ref_texts = {n: strip_lines(pages_text[n - 1], boiler) for n in sample}
    klass_by_page = {m.page: m.classification for m in analyze_document(pdf_path)}

    out_dir = resolve_path(ctx.settings.paths.markdown_dir) / doc_id / "spike"
    pages_dir = resolve_path(ctx.settings.paths.pages_dir) / doc_id

    typer.echo(f"Spike A vs B su {len(sample)} pagine: {sample} ...")
    rows = run_spike(
        LlmClient(ctx.conn, ctx.prices, settings=ctx.settings),
        pdf_path,
        sample=sample,
        klass_by_page=klass_by_page,
        ref_texts=ref_texts,
        pages_dir=pages_dir,
        out_dir=out_dir,
        model=ctx.settings.model_for("conversion"),
        prompt_text=load_prompt("convert_text"),
        prompt_vision=load_prompt("conversion"),
    )
    write_spike_csv(rows, out_dir / "spike_results.csv")
    (out_dir / "spike_review.html").write_text(
        build_spike_html(rows, out_dir, pages_dir), encoding="utf-8"
    )

    failed = [n for n in sample if n not in {r.page for r in rows}]
    if failed:
        typer.echo(f"FALLITE (ritenta con --pages): {failed}")

    typer.echo("\nMedie per classe (A=testo, B=VLM):")
    typer.echo(f"  {'classe':<14} {'pag':>3} {'ovl_A':>6} {'ovl_B':>6} "
               f"{'num_A':>6} {'num_B':>6} {'$_A':>8} {'$_B':>8}")
    for klass, s in summarize_by_class(rows).items():
        typer.echo(
            f"  {klass:<14} {int(s['pages']):>3} {s['overlap_a']:>6.2f} {s['overlap_b']:>6.2f} "
            f"{s['numrec_a']:>6.2f} {s['numrec_b']:>6.2f} {s['cost_a']:>8.4f} {s['cost_b']:>8.4f}"
        )
    tot_a = sum(r.cost_a for r in rows)
    tot_b = sum(r.cost_b for r in rows)
    typer.echo(f"\nCosto spike: A ${tot_a:.4f} + B ${tot_b:.4f} = ${tot_a + tot_b:.4f}")
    typer.echo(f"CSV: {out_dir / 'spike_results.csv'}")
    typer.echo(f"Review: {out_dir / 'spike_review.html'}")


@ingest_app.command("route")
def ingest_route(
    pdf: str = typer.Option(None, help="Percorso PDF (default: corpus pilota)."),
) -> None:
    """Nota raffinamento §B: applica la regola di routing e mostra la distribuzione."""
    from poc_istruzioni.bootstrap import resolve_path
    from poc_istruzioni.config import load_settings
    from poc_istruzioni.ingest.layout import analyze_document
    from poc_istruzioni.ingest.routing import route_all

    settings = load_settings()
    pdf_path = resolve_path(pdf) if pdf else resolve_path(settings.paths.raw_dir) / _PILOT_PDF
    if not pdf_path.exists():
        raise typer.BadParameter(f"PDF non trovato: {pdf_path}")

    decisions = route_all(analyze_document(pdf_path), settings.routing)
    a = sum(1 for _, d in decisions if d.route == "A")
    b = [(m.page, d.reason) for m, d in decisions if d.route == "B"]
    total = len(decisions)
    typer.echo(f"{total} pagine instradate: Rotta A (testo) {a} · Rotta B (VLM) {len(b)}")
    for page, reason in b:
        typer.echo(f"  p{page:03d} -> B: {reason}")


@ingest_app.command("measure-escalation")
def measure_escalation(
    model: str = typer.Option("claude-haiku-4-5", help="Modello Rotta A da misurare."),
    n: int = typer.Option(15, help="Numero di pagine single_column da campionare."),
    doc_id: str = typer.Option("PF1-2026", help="Identificatore documento."),
    pdf: str = typer.Option(None, help="Percorso PDF (default: corpus pilota)."),
) -> None:
    """Nota §M3: misura il tasso di escalation E (% pagine bocciate dal gate) di un modello."""
    import fitz

    from poc_istruzioni.bootstrap import build_context, resolve_path
    from poc_istruzioni.config import load_prompt
    from poc_istruzioni.ingest.checks import run_gate_from_settings
    from poc_istruzioni.ingest.layout import analyze_document
    from poc_istruzioni.ingest.textlayer import (
        extract_pages_text,
        find_boilerplate_lines,
        strip_lines,
    )
    from poc_istruzioni.ingest.textroute import convert_text_to_markdown, extract_text_with_cues
    from poc_istruzioni.llm.client import LlmClient

    ctx = build_context()
    pdf_path = resolve_path(pdf) if pdf else resolve_path(ctx.settings.paths.raw_dir) / _PILOT_PDF
    if not pdf_path.exists():
        raise typer.BadParameter(f"PDF non trovato: {pdf_path}")

    pages_text = extract_pages_text(pdf_path)
    boiler = find_boilerplate_lines(pages_text)
    single = sorted(
        m.page for m in analyze_document(pdf_path) if m.classification == "single_column"
    )
    step = max(1, len(single) // n)
    sample = single[::step][:n]

    prompt = load_prompt("convert_text")
    llm = LlmClient(ctx.conn, ctx.prices, settings=ctx.settings)
    doc = fitz.open(pdf_path)
    out_dir = resolve_path(ctx.settings.paths.markdown_dir) / doc_id / "escalation_measure"
    out_dir.mkdir(parents=True, exist_ok=True)

    typer.echo(f"Misura escalation: {len(sample)} pagine single_column con {model} -> {sample}")
    fails = 0
    cost = 0.0
    for p in sample:
        res = convert_text_to_markdown(
            llm, extract_text_with_cues(doc[p - 1]), model=model, prompt=prompt,
            page_n=p, scopo="spike:haiku-escalation-rate",
        )
        (out_dir / f"p{p:03d}.md").write_text(res.text, encoding="utf-8")  # salvataggio per re-gate
        cost += res.cost.usd
        ref = strip_lines(pages_text[p - 1], boiler)
        rep = run_gate_from_settings(res.text, ref, ctx.settings, page_number=p)
        if rep.needs_review:
            fails += 1
            typer.echo(f"  p{p:03d} BOCCIATA: {rep.reasons}")

    e = fails / len(sample) if sample else 0.0
    typer.echo(f"\nE = {fails}/{len(sample)} = {100 * e:.0f}%  (costo misura ${cost:.4f})")
    if e < 0.15:
        typer.echo("=> Graduata (Haiku): E < 15%")
    elif e > 0.30:
        typer.echo("=> Sicura (Opus): E > 30%")
    else:
        typer.echo("=> Zona grigia (15-30%): stop-point, decidere coi numeri")


@ingest_app.command("identity")
def ingest_identity(
    doc_id: str = typer.Option("PF1-2026", help="Identificatore documento."),
    page: int = typer.Option(1, help="Pagina del frontespizio."),
) -> None:
    """B.5: estrae l'identità dal frontespizio (VLM) e la valida vs i metadati registrati."""
    from poc_istruzioni.bootstrap import build_context, resolve_path
    from poc_istruzioni.config import load_prompt
    from poc_istruzioni.db.repositories import get_document
    from poc_istruzioni.ingest.identity import extract_identity, validate_identity
    from poc_istruzioni.llm.client import LlmClient

    ctx = build_context()
    doc = get_document(ctx.conn, doc_id)
    if doc is None:
        raise typer.BadParameter(
            f"documento {doc_id!r} non registrato: esegui prima `poc ingest render`"
        )

    image = resolve_path(ctx.settings.paths.pages_dir) / doc_id / f"p{page:03d}.png"
    if not image.exists():
        raise typer.BadParameter(f"immagine non trovata: {image}")

    llm = LlmClient(ctx.conn, ctx.prices, settings=ctx.settings)
    rec, res = extract_identity(
        llm, image, model=ctx.settings.model_for("route_b"), prompt=load_prompt("identity")
    )

    typer.echo("Identità estratta dal frontespizio (vision):")
    typer.echo(f"  modello         : {rec.modello}")
    typer.echo(f"  edizione        : {rec.edizione}")
    typer.echo(f"  periodo_imposta : {rec.periodo_imposta}")
    typer.echo(f"  agg_data        : {rec.agg_data or '(non rilevata)'}")
    typer.echo(
        f"Atteso (da DB)    : edizione={doc.edizione}, periodo_imposta={doc.periodo_imposta}"
    )

    issues = validate_identity(
        rec,
        expected_edizione=doc.edizione,
        expected_periodo=doc.periodo_imposta,
        expected_modello_hint=doc.modello.split("-")[0],
    )
    typer.echo(f"Costo: ${res.cost.usd:.6f}")
    if issues:
        typer.echo("\nIDENTITÀ NON COERENTE — errore bloccante:")
        for i in issues:
            typer.echo(f"  - {i}")
        raise typer.Exit(code=1)
    typer.echo("\nIdentità coerente con le attese: OK.")


@ingest_app.command("convert")
def ingest_convert(
    pages: str = typer.Option(None, help="Pagine specifiche, es. '6,75'. Omesso = tutte."),
    frm: int = typer.Option(None, "--from", help="Inizio range (incluso)."),
    to: int = typer.Option(None, "--to", help="Fine range (incluso)."),
    doc_id: str = typer.Option("PF1-2026", help="Identificatore documento."),
    pdf: str = typer.Option(None, help="Percorso PDF (default: corpus pilota)."),
) -> None:
    """Run di conversione: routing + escalation Graduata + audit + circuit breaker (a pagamento)."""
    from poc_istruzioni.bootstrap import build_context, resolve_path
    from poc_istruzioni.config import load_prompt
    from poc_istruzioni.ingest.convert import convert_document
    from poc_istruzioni.llm.client import LlmClient

    ctx = build_context()
    page_numbers = None
    if pages or frm is not None:
        page_numbers = _parse_pages(pages, frm, to)
    pdf_path = resolve_path(pdf) if pdf else resolve_path(ctx.settings.paths.raw_dir) / _PILOT_PDF
    if not pdf_path.exists():
        raise typer.BadParameter(f"PDF non trovato: {pdf_path}")

    n = len(page_numbers) if page_numbers else "tutte le"
    typer.echo(f"Conversione {n} pagine (routing + escalation Graduata) ...")
    summary = convert_document(
        ctx.conn,
        LlmClient(ctx.conn, ctx.prices, settings=ctx.settings),
        doc_id=doc_id,
        pdf_path=pdf_path,
        pages_dir=resolve_path(ctx.settings.paths.pages_dir) / doc_id,
        markdown_dir=resolve_path(ctx.settings.paths.markdown_dir),
        settings=ctx.settings,
        prompt_text=load_prompt("convert_text"),
        prompt_vision=load_prompt("conversion"),
        page_numbers=page_numbers,
    )
    typer.echo(
        f"Fatto: {summary.pages} pagine (A={summary.route_a}, B={summary.route_b}); "
        f"escalate {summary.escalated} ({100 * summary.escalated / max(1, summary.pages):.0f}%); "
        f"da rivedere a mano {summary.needs_human}; gate-miss audit {summary.gate_misses}."
    )
    if summary.breaker_tripped:
        typer.echo("CIRCUIT BREAKER attivato: default forte (Opus) per le pagine restanti.")
    typer.echo(f"Costo run: ${summary.usd:.4f}")


def _parse_pages(pages: str | None, frm: int | None, to: int | None) -> list[int]:
    if pages:
        return [int(x) for x in pages.split(",") if x.strip()]
    if frm is not None and to is not None:
        return list(range(frm, to + 1))
    raise typer.BadParameter("specifica --pages '54,99' oppure --from/--to")


@ingest_app.command("transcribe")
def ingest_transcribe(
    pages: str = typer.Option(None, help="Pagine specifiche, es. '54,99,120'."),
    frm: int = typer.Option(None, "--from", help="Inizio range (incluso)."),
    to: int = typer.Option(None, "--to", help="Fine range (incluso)."),
    doc_id: str = typer.Option("PF1-2026", help="Identificatore documento."),
    pdf: str = typer.Option(None, help="Percorso PDF (default: corpus pilota)."),
    title: str = typer.Option("Trascrizione VLM", help="Titolo della review."),
    force: bool = typer.Option(False, "--force", help="Ritrascrivi anche le pagine già presenti."),
) -> None:
    """FR-B2: trascrive pagine con il VLM, esegue i check e genera la review HTML.

    Effettua chiamate a pagamento (modello 'conversion' da settings). Richiede ANTHROPIC_API_KEY.
    """
    from poc_istruzioni.bootstrap import build_context, resolve_path
    from poc_istruzioni.config import load_prompt
    from poc_istruzioni.ingest.pipeline import transcribe_pages
    from poc_istruzioni.ingest.textlayer import (
        extract_pages_text,
        find_boilerplate_lines,
        strip_lines,
    )
    from poc_istruzioni.llm.client import LlmClient

    ctx = build_context()
    page_list = _parse_pages(pages, frm, to)
    pdf_path = resolve_path(pdf) if pdf else resolve_path(ctx.settings.paths.raw_dir) / _PILOT_PDF
    if not pdf_path.exists():
        raise typer.BadParameter(f"PDF non trovato: {pdf_path}")

    # Testo di riferimento per pagina (text-layer ripulito da header/footer).
    pages_text = extract_pages_text(pdf_path)
    boiler = find_boilerplate_lines(pages_text)
    ref_texts = {n: strip_lines(pages_text[n - 1], boiler) for n in page_list}

    model = ctx.settings.model_for("conversion")
    pages_dir = resolve_path(ctx.settings.paths.pages_dir) / doc_id
    tag = f"{min(page_list):03d}-{max(page_list):03d}"
    review_path = resolve_path(ctx.settings.paths.markdown_dir) / doc_id / "reviews" / f"{tag}.html"

    typer.echo(f"Trascrivo {len(page_list)} pagine con {model} (pagine: {page_list}) ...")
    summary = transcribe_pages(
        ctx.conn,
        LlmClient(ctx.conn, ctx.prices, settings=ctx.settings),
        doc_id=doc_id,
        page_numbers=page_list,
        pages_dir=pages_dir,
        markdown_dir=resolve_path(ctx.settings.paths.markdown_dir),
        ref_texts=ref_texts,
        model=model,
        prompt=load_prompt("conversion"),
        review_path=review_path,
        title=title,
        skip_existing=not force,
    )
    typer.echo(
        f"OK: {summary.pages} in review "
        f"(trascritte {summary.transcribed}, riusate {summary.skipped}, "
        f"da rivedere {summary.needs_review}). "
        f"Costo run: ${summary.usd:.4f} / €{summary.eur:.4f}"
    )
    if summary.failed:
        typer.echo(f"FALLITE (da ritentare): {summary.failed}")
    typer.echo(f"Review: {summary.review_path}")


@app.command()
def smoke(
    scope: str = typer.Option("router", help="Scopo->modello da settings.toml [models]."),
    text: str = typer.Option("Rispondi solo con: OK", help="Prompt di prova."),
    max_tokens: int = typer.Option(64, help="Tetto output per la prova."),
) -> None:
    """Chiamata di prova reale via LlmClient: registra nel ledger e stampa costo (FR-T2).

    Richiede ANTHROPIC_API_KEY nell'ambiente.
    """
    from poc_istruzioni.bootstrap import build_context
    from poc_istruzioni.llm.client import LlmClient

    ctx = build_context()
    model = ctx.settings.model_for(scope)
    client = LlmClient(ctx.conn, ctx.prices, settings=ctx.settings)
    res = client.complete(
        scopo="smoke",
        model=model,
        messages=[{"role": "user", "content": text}],
        max_tokens=max_tokens,
    )
    typer.echo(f"[{model}] {res.text}")
    typer.echo(
        f"token in={res.usage.input_tokens} out={res.usage.output_tokens} "
        f"cache_r={res.usage.cache_read_input_tokens} "
        f"cache_w={res.usage.cache_creation_input_tokens}"
    )
    typer.echo(f"costo: ${res.cost.usd:.6f} / €{res.cost.eur:.6f}  (ledger id={res.call_id})")


if __name__ == "__main__":
    app()
