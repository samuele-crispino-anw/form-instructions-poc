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
