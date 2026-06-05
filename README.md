# PoC Istruzioni — Assistente Q&A sui modelli dichiarativi

Assistente che risponde a domande sulla **compilazione dei modelli dichiarativi**
(corpus pilota: istruzioni *Redditi PF — Fascicolo 1*, ed. 2026) con **citazioni
verificabili** (quadro/rigo/pagina/edizione) e rifiuto quando l'informazione non è nel corpus.

Due stadi confrontati con numeri:

- **B** — conversione PDF→Markdown via VLM, router su ~20 sezioni, sezione intera in
  contesto con prompt caching, risposta citata. Nessun vector store.
- **D** — estrazione one-time di un DB ontologico (rigo→codici→vincoli); a runtime un
  modello piccolo fa lookup deterministico (i numeri vengono dal DB, mai dalla memoria del modello).

Requisiti trasversali non negoziabili: tracciabilità end-to-end, answer trace per ogni
risposta, contabilità token/€ completa (ledger), evaluation misurabile.

## Setup

```bash
uv sync                      # crea .venv e installa le dipendenze
cp .env.example .env         # poi valorizza ANTHROPIC_API_KEY
```

Il PDF sorgente va posto in `data/raw/` (non versionato).

## Struttura

```
config/        settings.toml, prices.toml, alias_table.yaml  (config = dati, non codice)
src/poc_istruzioni/
  config.py    caricamento tipizzato di settings/prices
  provenance.py  hashing sha256, run_id, timestamp (tracciabilità FR-T1/T3)
  llm/         LlmClient (unico accesso ai modelli) + pricing (FR-T2)
  db/          schema.sql + accesso SQLite (no ORM)
  ledger/      registro chiamate e costi (FR-T2)
  ingest/      Stadio B1-B3: rendering, trascrizione VLM, markdown
  serving/     Stadio B4-B6: router, contesto cachato, risposta+citazioni
  ontology/    Stadio D: schema, compilazione, lookup, runtime
  tracing/     answer trace + comando `trace`
  eval/        golden set + runner (FR-E)
tests/         pytest, mirror di src/
```

## Stato

Fase 0 (fondamenta: ledger + `LlmClient`) in corso.
