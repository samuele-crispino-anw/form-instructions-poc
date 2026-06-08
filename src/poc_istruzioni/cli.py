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

review_app = typer.Typer(help="Revisione umana delle pagine bloccate (human-in-the-loop).")
app.add_typer(review_app, name="review")

nav_app = typer.Typer(help="Navigazione gerarchica (Fase 2): albero dei nodi, retrieval.")
app.add_typer(nav_app, name="nav")

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
    economical: bool = typer.Option(
        False, "--economical", help="Pipeline economica: parti da Haiku invece che da Opus."
    ),
    force: bool = typer.Option(
        False, "--force", help="Riconverti anche le pagine già risolte da un umano (lock off)."
    ),
) -> None:
    """Run di conversione: routing + escalation + audit + circuit breaker (a pagamento).

    Default: priorità accuratezza (Rotta A parte da Opus). `--economical` parte da Haiku.
    """
    from poc_istruzioni.bootstrap import build_context, resolve_path
    from poc_istruzioni.config import load_prompt
    from poc_istruzioni.ingest.convert import convert_document
    from poc_istruzioni.llm.client import LlmClient

    ctx = build_context()
    settings = ctx.settings
    if economical:  # override a runtime: pipeline Haiku-first
        settings = settings.model_copy(
            update={"escalation": settings.escalation.model_copy(update={"economical_first": True})}
        )
    page_numbers = None
    if pages or frm is not None:
        page_numbers = _parse_pages(pages, frm, to)
    pdf_path = resolve_path(pdf) if pdf else resolve_path(settings.paths.raw_dir) / _PILOT_PDF
    if not pdf_path.exists():
        raise typer.BadParameter(f"PDF non trovato: {pdf_path}")

    n = len(page_numbers) if page_numbers else "tutte le"
    modo = "economica (Haiku-first)" if economical else "accuratezza (Opus-first)"
    typer.echo(f"Conversione {n} pagine — modalità {modo} ...")
    summary = convert_document(
        ctx.conn,
        LlmClient(ctx.conn, ctx.prices, settings=settings),
        doc_id=doc_id,
        pdf_path=pdf_path,
        pages_dir=resolve_path(settings.paths.pages_dir) / doc_id,
        markdown_dir=resolve_path(settings.paths.markdown_dir),
        settings=settings,
        prompt_text=load_prompt("convert_text"),
        prompt_vision=load_prompt("conversion"),
        page_numbers=page_numbers,
        force=force,
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


@review_app.command("list")
def review_list(doc_id: str = typer.Option("PF1-2026", help="Identificatore documento.")) -> None:
    """Elenca le pagine in attesa di revisione umana (needs_human non ancora risolte)."""
    from poc_istruzioni.bootstrap import build_context
    from poc_istruzioni.db.repositories import pending_reviews

    ctx = build_context()
    rows = pending_reviews(ctx.conn, doc_id)
    if not rows:
        typer.echo("Nessuna pagina in attesa di revisione.")
        return
    typer.echo(f"{len(rows)} pagine da rivedere:")
    for r in rows:
        typer.echo(
            f"  p{r['n']:03d} [{r['model_used']}, {r['escalations']} escal] -> {r['reasons']}"
        )
    typer.echo("\nRisolvi con: poc review resolve --page N --action corretta|falso-positivo --by X")


@review_app.command("resolve")
def review_resolve(
    page: int = typer.Option(..., help="Pagina da risolvere."),
    action: str = typer.Option(..., help="corretta | falso-positivo"),
    by: str = typer.Option(..., "--by", help="Nome del revisore."),
    note: str = typer.Option("", help="Nota libera del revisore."),
    doc_id: str = typer.Option("PF1-2026", help="Identificatore documento."),
) -> None:
    """Registra la decisione umana su una pagina: correzione o falso positivo (e la blocca)."""
    from poc_istruzioni.bootstrap import build_context, resolve_path
    from poc_istruzioni.db.repositories import (
        ReviewRow,
        insert_review,
        update_conversion_status,
    )
    from poc_istruzioni.provenance import sha256_file, utc_now_iso

    azione = {"corretta": "corretta", "falso-positivo": "falso_positivo"}.get(action)
    if azione is None:
        raise typer.BadParameter("action deve essere 'corretta' o 'falso-positivo'")

    ctx = build_context()
    conv = ctx.conn.execute(
        "SELECT reasons FROM conversions WHERE doc_id = ? AND n = ?", (doc_id, page)
    ).fetchone()
    if conv is None:
        raise typer.BadParameter(f"pagina {page} non convertita per {doc_id}")

    pages_dir = resolve_path(ctx.settings.paths.markdown_dir) / doc_id / "pages"
    md = pages_dir / f"p{page:03d}.md"
    rejected = (
        resolve_path(ctx.settings.paths.markdown_dir)
        / doc_id / "needs_review" / f"p{page:03d}.rejected.md"
    )
    sha_now = sha256_file(md) if md.exists() else None
    if azione == "corretta":
        sha_rif = sha256_file(rejected) if rejected.exists() else None
        sha_ris = sha_now
        status = "corretta_umano"
    else:  # falso_positivo: markdown accettato così com'è
        sha_rif = sha_ris = sha_now
        status = "accettata_umano"

    insert_review(ctx.conn, ReviewRow(
        doc_id=doc_id, n=page, azione=azione, revisore=by, nota=note or None,
        regole_flaggate=conv["reasons"], sha_rifiutato=sha_rif, sha_risolto=sha_ris,
        ts=utc_now_iso(),
    ))
    update_conversion_status(ctx.conn, doc_id, page, status)
    typer.echo(
        f"p{page:03d} risolta come '{azione}' da {by}. Stato: {status}. "
        "Pagina bloccata al re-run (usa --force per riconvertirla)."
    )


def _write_nav_explorer(ctx, doc_id: str, frm: int, to: int):
    """Rigenera l'explorer HTML dallo stato corrente del DB. Single source per tutti i comandi
    che modificano nodi/grafo: chiamarlo SEMPRE dopo una mutazione. Ritorna il Path o None."""
    from poc_istruzioni.bootstrap import resolve_path
    from poc_istruzioni.db.repositories import get_nodes, get_pins
    from poc_istruzioni.serving.explorer import build_explorer_html
    from poc_istruzioni.serving.nodes import Node
    from poc_istruzioni.serving.pins import Pin, collect_pins
    from poc_istruzioni.serving.summaries import build_scope_inputs

    rows = get_nodes(ctx.conn, doc_id)
    if not rows:
        return None
    nodes = [
        Node(id=r["id"], parent_id=r["parent_id"], kind=r["kind"], level=r["level"],
             title=r["title"], page_start=r["page_start"], page_end=r["page_end"], ord=r["ord"])
        for r in rows
    ]
    summaries = {r["id"]: r["summary"] for r in rows}
    prov_keys = ("built_run_id", "summary_model", "summary_prompt_sha", "summary_ts",
                 "summary_call_id")
    provenance = {r["id"]: {k: r[k] for k in prov_keys} for r in rows}
    pins = [
        Pin(owner_node_id=r["owner_node_id"], owner_kind=r["owner_kind"],
            owner_title=r["owner_title"], text=r["text"])
        for r in get_pins(ctx.conn, doc_id)
    ]
    pins_by_node = {
        n.id: [
            {"kind": p.owner_kind, "title": p.owner_title, "text": p.text}
            for p in collect_pins(n.id, nodes, pins)
        ]
        for n in nodes
    }
    pages_dir = resolve_path(ctx.settings.paths.markdown_dir) / doc_id / "pages"
    md_by_page = {}
    for n in range(frm, to + 1):
        f = pages_dir / f"p{n:03d}.md"
        if f.exists():
            md_by_page[n] = f.read_text(encoding="utf-8")
    scopes = {s.node_id: s for s in build_scope_inputs(nodes, md_by_page)}
    out_html = build_explorer_html(
        nodes, scopes, summaries, md_by_page, doc_id=doc_id,
        provenance=provenance, pins_by_node=pins_by_node,
    )
    out_path = pages_dir.parent / "nav_explorer.html"
    out_path.write_text(out_html, encoding="utf-8")
    return out_path


@nav_app.command("tree")
def nav_tree(
    frm: int = typer.Option(69, "--from", help="Prima pagina (default: inizio quadro RP)."),
    to: int = typer.Option(133, "--to", help="Ultima pagina (default: fine quadro RP)."),
    doc_id: str = typer.Option("PF1-2026", help="Identificatore documento."),
) -> None:
    """D1: costruisce l'albero di navigazione (per pattern strutturale) e lo mostra."""
    from poc_istruzioni.bootstrap import build_context, resolve_path
    from poc_istruzioni.db.repositories import insert_nav_build, insert_nodes
    from poc_istruzioni.provenance import new_run_id, utc_now_iso
    from poc_istruzioni.serving.nodes import (
        build_tree,
        parse_structural_headings,
        patterns_version,
        render_tree,
    )

    ctx = build_context()
    pages_dir = resolve_path(ctx.settings.paths.markdown_dir) / doc_id / "pages"
    slice_pages = list(range(frm, to + 1))
    md_by_page = {}
    for n in slice_pages:
        f = pages_dir / f"p{n:03d}.md"
        if f.exists():
            md_by_page[n] = f.read_text(encoding="utf-8")

    run_id = new_run_id()
    nodes = build_tree(parse_structural_headings(md_by_page), slice_pages)
    insert_nodes(ctx.conn, doc_id, nodes, run_id=run_id)
    insert_nav_build(
        ctx.conn, run_id=run_id, doc_id=doc_id, page_from=frm, page_to=to,
        n_nodes=len(nodes), pattern_version=patterns_version(), ts=utc_now_iso(),
    )
    typer.echo(render_tree(nodes))
    kinds = {}
    for n in nodes:
        kinds[n.kind] = kinds.get(n.kind, 0) + 1
    typer.echo(f"\n{len(nodes)} nodi: {kinds}")
    p = _write_nav_explorer(ctx, doc_id, frm, to)  # ricalcolo forzato dell'explorer
    if p:
        typer.echo(f"Explorer aggiornato: {p}")


@nav_app.command("summaries")
def nav_summaries(
    frm: int = typer.Option(69, "--from", help="Prima pagina (per il testo delle foglie)."),
    to: int = typer.Option(133, "--to", help="Ultima pagina."),
    doc_id: str = typer.Option("PF1-2026", help="Identificatore documento."),
    limit: int = typer.Option(0, help="Mini-run: genera solo N nodi rappresentativi (0 = tutti)."),
    force: bool = typer.Option(False, "--force", help="Rigenera anche i riassunti gia' presenti."),
) -> None:
    """D2: genera le etichette di navigazione scope-aware dei nodi (LLM, compile-once)."""
    from poc_istruzioni.bootstrap import build_context, resolve_path
    from poc_istruzioni.config import load_prompt
    from poc_istruzioni.db.repositories import get_nodes, update_node_summary
    from poc_istruzioni.llm.client import LlmClient
    from poc_istruzioni.provenance import sha256_text, utc_now_iso
    from poc_istruzioni.serving.nodes import Node
    from poc_istruzioni.serving.summaries import build_scope_inputs, generate_summary

    ctx = build_context()
    rows = get_nodes(ctx.conn, doc_id)
    if not rows:
        typer.echo("Nessun nodo: esegui prima `poc nav tree`.")
        raise typer.Exit(1)

    nodes = [
        Node(id=r["id"], parent_id=r["parent_id"], kind=r["kind"], level=r["level"],
             title=r["title"], page_start=r["page_start"], page_end=r["page_end"], ord=r["ord"])
        for r in rows
    ]
    existing = {r["id"]: r["summary"] for r in rows}

    pages_dir = resolve_path(ctx.settings.paths.markdown_dir) / doc_id / "pages"
    md_by_page = {}
    for n in range(frm, to + 1):
        f = pages_dir / f"p{n:03d}.md"
        if f.exists():
            md_by_page[n] = f.read_text(encoding="utf-8")

    scopes = build_scope_inputs(nodes, md_by_page)
    if limit:  # campione rappresentativo: 1 quadro + 1 sezione + foglie fino a `limit`
        sample = [s for s in scopes if s.kind == "quadro"][:1]
        sample += [s for s in scopes if s.kind == "sezione"][:1]
        for s in scopes:
            if len(sample) >= limit:
                break
            if s.is_leaf and s not in sample:
                sample.append(s)
        scopes = sample[:limit]

    model = ctx.settings.model_for("compile")
    system = load_prompt("node_summary")
    prompt_sha = sha256_text(system)[:16]  # provenienza: quale prompt ha generato il summary [A]
    client = LlmClient(ctx.conn, ctx.prices, settings=ctx.settings)
    titles = {n.id: n.title for n in nodes}

    total_usd = 0.0
    done = 0
    for s in scopes:
        if not force and existing.get(s.node_id):
            continue
        text, res = generate_summary(client, s, model=model, system_prompt=system)
        update_node_summary(
            ctx.conn, doc_id, s.node_id, text,
            model=res.model, prompt_sha=prompt_sha, ts=utc_now_iso(), call_id=res.call_id,
        )
        total_usd += res.cost.usd
        done += 1
        typer.echo(f"\n[{s.kind}] {titles[s.node_id][:70]}")
        typer.echo(f"  -> {text}")

    typer.echo(f"\nGenerati {done} riassunti con {model}. Costo: ${total_usd:.4f}")
    p = _write_nav_explorer(ctx, doc_id, frm, to)  # ricalcolo forzato dell'explorer
    if p:
        typer.echo(f"Explorer aggiornato: {p}")


@nav_app.command("explore")
def nav_explore(
    frm: int = typer.Option(69, "--from", help="Prima pagina."),
    to: int = typer.Option(133, "--to", help="Ultima pagina."),
    doc_id: str = typer.Option("PF1-2026", help="Identificatore documento."),
) -> None:
    """Rigenera l'explorer HTML statico (struttura + input + pagine + summary) per il browser."""
    from poc_istruzioni.bootstrap import build_context

    ctx = build_context()
    out_path = _write_nav_explorer(ctx, doc_id, frm, to)
    if out_path is None:
        typer.echo("Nessun nodo: esegui prima `poc nav tree`.")
        raise typer.Exit(1)
    typer.echo(f"Explorer generato: {out_path}\nAprilo nel browser (es. open '{out_path}').")


@nav_app.command("pins")
def nav_pins(
    frm: int = typer.Option(69, "--from", help="Prima pagina."),
    to: int = typer.Option(133, "--to", help="Ultima pagina."),
    doc_id: str = typer.Option("PF1-2026", help="Identificatore documento."),
) -> None:
    """D2.5: estrae le regole governanti (preamboli dei rami) e le pinna; rigenera l'explorer."""
    from poc_istruzioni.bootstrap import build_context, resolve_path
    from poc_istruzioni.db.repositories import get_nodes, replace_pins
    from poc_istruzioni.provenance import new_run_id, utc_now_iso
    from poc_istruzioni.serving.nodes import Node
    from poc_istruzioni.serving.pins import build_pins

    ctx = build_context()
    rows = get_nodes(ctx.conn, doc_id)
    if not rows:
        typer.echo("Nessun nodo: esegui prima `poc nav tree`.")
        raise typer.Exit(1)
    nodes = [
        Node(id=r["id"], parent_id=r["parent_id"], kind=r["kind"], level=r["level"],
             title=r["title"], page_start=r["page_start"], page_end=r["page_end"], ord=r["ord"])
        for r in rows
    ]
    pages_dir = resolve_path(ctx.settings.paths.markdown_dir) / doc_id / "pages"
    md_by_page = {}
    for n in range(frm, to + 1):
        f = pages_dir / f"p{n:03d}.md"
        if f.exists():
            md_by_page[n] = f.read_text(encoding="utf-8")
    pins = build_pins(nodes, md_by_page)
    replace_pins(ctx.conn, doc_id, pins, source="preamble",
                 run_id=new_run_id(), ts=utc_now_iso())
    typer.echo(f"Pin estratti (preamboli governanti): {len(pins)} rami.")
    for p in pins:
        typer.echo(f"  [{p.owner_kind}] {p.owner_title[:55]}  ({len(p.text)} char)")
    out = _write_nav_explorer(ctx, doc_id, frm, to)
    if out:
        typer.echo(f"Explorer aggiornato: {out}")


@nav_app.command("index")
def nav_index(doc_id: str = typer.Option("PF1-2026", help="Identificatore documento.")) -> None:
    """D3: costruisce il keyword index (term->nodo, tf x idf) da titoli + summary dei nodi."""
    from poc_istruzioni.bootstrap import build_context
    from poc_istruzioni.db.repositories import get_nodes, replace_keywords
    from poc_istruzioni.serving.keywords import build_index

    ctx = build_context()
    rows = get_nodes(ctx.conn, doc_id)
    if not rows:
        typer.echo("Nessun nodo: esegui prima `poc nav tree`.")
        raise typer.Exit(1)
    items = [(r["id"], r["title"], r["summary"] or "") for r in rows]
    entries = build_index(items)
    replace_keywords(ctx.conn, doc_id, entries)
    n_terms = len({e.term for e in entries})
    typer.echo(
        f"Keyword index: {len(entries)} voci, {n_terms} termini distinti su {len(items)} nodi."
    )


@nav_app.command("match")
def nav_match(
    query: str = typer.Argument(..., help="Domanda/parole dell'utente."),
    doc_id: str = typer.Option("PF1-2026", help="Identificatore documento."),
    top: int = typer.Option(5, help="Quanti nodi candidati mostrare."),
) -> None:
    """D3: risolve una query nei nodi candidati via fast-path deterministico (no LLM)."""
    from poc_istruzioni.bootstrap import build_context
    from poc_istruzioni.config import load_aliases
    from poc_istruzioni.db.repositories import get_keywords, get_nodes
    from poc_istruzioni.serving.keywords import IndexEntry, expand_query, score_nodes

    ctx = build_context()
    rows = get_keywords(ctx.conn, doc_id)
    if not rows:
        typer.echo("Indice vuoto: esegui prima `poc nav index`.")
        raise typer.Exit(1)
    entries = [IndexEntry(term=r["term"], node_id=r["node_id"], weight=r["weight"]) for r in rows]
    aliases = load_aliases()
    meta = {
        r["id"]: (r["kind"], r["title"], r["page_start"], r["page_end"])
        for r in get_nodes(ctx.conn, doc_id)
    }
    ranked = score_nodes(query, entries, aliases)[:top]
    typer.echo(f"Query: {query!r}")
    typer.echo(f"Termini cercati (espansi): {sorted(set(expand_query(query, aliases)))}\n")
    if not ranked:
        typer.echo("Nessun candidato dal fast-path -> si passerebbe alla navigazione-LLM.")
        return
    for nid, sc in ranked:
        kind, title, ps, pe = meta.get(nid, ("?", "?", 0, 0))
        typer.echo(f"  {sc:7.2f}  [{kind}] {title[:62]}  (p.{ps}-{pe})")


@nav_app.command("retrieve")
def nav_retrieve(
    query: str = typer.Argument(..., help="Domanda dell'utente."),
    doc_id: str = typer.Option("PF1-2026", help="Identificatore documento."),
    show_context: bool = typer.Option(False, "--show-context", help="Stampa il contesto servito."),
) -> None:
    """D-orchestrazione: fast-path -> gate -> (navigazione-LLM) -> pin -> contesto + trace."""
    import json

    from poc_istruzioni.bootstrap import build_context, resolve_path
    from poc_istruzioni.config import load_aliases, load_prompt
    from poc_istruzioni.db.repositories import get_keywords, get_nodes, get_pins
    from poc_istruzioni.llm.client import LlmClient
    from poc_istruzioni.provenance import new_run_id, utc_now_iso
    from poc_istruzioni.serving.keywords import IndexEntry, score_nodes
    from poc_istruzioni.serving.nodes import Node
    from poc_istruzioni.serving.pins import Pin, collect_pins
    from poc_istruzioni.serving.retrieval import (
        build_served_context,
        classify_fastpath,
        navigate_llm,
    )
    from poc_istruzioni.serving.summaries import _page_text

    ctx = build_context()
    rows = get_nodes(ctx.conn, doc_id)
    if not rows:
        typer.echo("Nessun nodo: esegui prima `poc nav tree`/`index`/`pins`.")
        raise typer.Exit(1)
    nodes = [
        Node(id=r["id"], parent_id=r["parent_id"], kind=r["kind"], level=r["level"],
             title=r["title"], page_start=r["page_start"], page_end=r["page_end"], ord=r["ord"])
        for r in rows
    ]
    by_id = {n.id: n for n in nodes}
    summaries = {r["id"]: r["summary"] for r in rows}
    entries = [
        IndexEntry(term=r["term"], node_id=r["node_id"], weight=r["weight"])
        for r in get_keywords(ctx.conn, doc_id)
    ]
    pins = [
        Pin(owner_node_id=r["owner_node_id"], owner_kind=r["owner_kind"],
            owner_title=r["owner_title"], text=r["text"])
        for r in get_pins(ctx.conn, doc_id)
    ]
    cfg = ctx.settings.retrieval
    ranked = score_nodes(query, entries, load_aliases())
    gate, reason = classify_fastpath(ranked, min_abs=cfg.gate_min_abs, margin=cfg.gate_margin)

    cost = 0.0
    if gate == "netto":
        method, target = "fast_path", ranked[0][0]
    else:
        shortlist = [nid for nid, _ in ranked[: cfg.top_k]] or [
            n.id for n in nodes if n.kind in ("sezione", "rigo")
        ]
        cand = [
            (n.id, n.kind, n.title, summaries.get(n.id) or "")
            for n in nodes if n.id in set(shortlist)
        ]
        client = LlmClient(ctx.conn, ctx.prices, settings=ctx.settings)
        target, res = navigate_llm(
            query, cand, client,
            model=ctx.settings.model_for("router"), system_prompt=load_prompt("nav_router"),
        )
        cost += res.cost.usd
        method = "navigation_llm" if target is not None else "refused"

    typer.echo(f"Query: {query!r}")
    typer.echo(f"Gate: {gate} ({reason})  ->  metodo: {method}")
    typer.echo("Top candidati fast-path:")
    for nid, sc in ranked[:5]:
        n = by_id.get(nid)
        typer.echo(f"  {sc:7.2f}  [{n.kind}] {n.title[:55]}" if n else f"  {sc:7.2f}  ?{nid}")

    served, pin_owners = "", []
    if target is None:
        typer.echo("\nEsito: REFUSED — nessuna voce pertinente trovata.")
    else:
        t = by_id[target]
        md = {}
        pages_dir = resolve_path(ctx.settings.paths.markdown_dir) / doc_id / "pages"
        for p in range(t.page_start, t.page_end + 1):
            f = pages_dir / f"p{p:03d}.md"
            if f.exists():
                md[p] = f.read_text(encoding="utf-8")
        pinned = collect_pins(target, nodes, pins)
        pin_owners = [p.owner_node_id for p in pinned]
        served = build_served_context(
            t.title, _page_text(md, t.page_start, t.page_end), pinned
        )
        typer.echo(f"\nVoce servita: [{t.kind}] {t.title}  (p.{t.page_start}-{t.page_end})")
        typer.echo(f"Pin ereditati: {[f'{p.owner_kind}:{p.owner_node_id}' for p in pinned]}")
        typer.echo(f"Contesto servito: {len(served)} char")
    eur = round(cost * ctx.prices.currency.usd_to_eur, 4)
    typer.echo(f"Costo retrieval: ${cost:.4f} (€{eur})")
    if show_context and served:
        typer.echo("\n" + "=" * 60 + "\n" + served)

    # Persistenza trace (FR-T1/B6): query + trace strutturata.
    qid = new_run_id()
    trace = {
        "gate": gate, "reason": reason, "method": method, "target_node_id": target,
        "candidates": ranked[:cfg.top_k], "pin_owners": pin_owners,
    }
    esito = "refused" if target is None else method
    ctx.conn.execute(
        "INSERT OR REPLACE INTO queries (query_id, testo, ts, route_json, esito, costo_eur) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (qid, query, utc_now_iso(), json.dumps(trace, ensure_ascii=False), esito, eur),
    )
    ctx.conn.execute(
        "INSERT OR REPLACE INTO answer_traces (query_id, trace_json) VALUES (?, ?)",
        (qid, json.dumps(trace, ensure_ascii=False)),
    )
    ctx.conn.commit()
    typer.echo(f"Trace registrata: query_id={qid}")


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
