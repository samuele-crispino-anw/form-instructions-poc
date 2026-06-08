-- Modello dati SQLite del PoC (§5). Idempotente: CREATE TABLE IF NOT EXISTS.
-- Le tabelle ontology_* (FR-D1) vengono aggiunte in Fase 4.

-- Documento sorgente (PDF). sha256 = hash dei byte del file (FR-T1).
CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,       -- es. PF1-2026
    modello         TEXT NOT NULL,
    edizione        TEXT NOT NULL,
    periodo_imposta TEXT NOT NULL,
    agg_data        TEXT,                   -- aggiornamento infra-stagione (es. 2026-05-13)
    sha256          TEXT NOT NULL,
    path            TEXT NOT NULL
);

-- Pagina renderizzata a immagine (FR-B1/B2).
CREATE TABLE IF NOT EXISTS pages (
    doc_id        TEXT NOT NULL REFERENCES documents(id),
    n             INTEGER NOT NULL,
    png_path      TEXT,
    png_sha       TEXT,
    vlm_status    TEXT,                     -- ok | needs_review
    overlap_score REAL,
    needs_review  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (doc_id, n)
);

-- Sezione markdown per quadro (FR-B3). versione mai sovrascritta (FR-T3).
CREATE TABLE IF NOT EXISTS sections (
    id       TEXT PRIMARY KEY,
    doc_id   TEXT NOT NULL REFERENCES documents(id),
    quadro   TEXT NOT NULL,
    titolo   TEXT,
    pagine   TEXT,                          -- es. "54-78"
    md_path  TEXT,
    md_sha   TEXT,
    versione INTEGER NOT NULL DEFAULT 1
);

-- Query utente e suo esito (FR-B6/FR-T1).
CREATE TABLE IF NOT EXISTS queries (
    query_id   TEXT PRIMARY KEY,
    testo      TEXT NOT NULL,
    ts         TEXT NOT NULL,
    route_json TEXT,
    esito      TEXT,                         -- answered | refused | escalation_suggerita
    costo_eur  REAL,
    latenza_ms INTEGER
);

-- Answer trace strutturata, interrogabile per query_id (FR-B6/FR-T1).
CREATE TABLE IF NOT EXISTS answer_traces (
    query_id   TEXT PRIMARY KEY REFERENCES queries(query_id),
    trace_json TEXT NOT NULL
);

-- Ledger: una riga per ogni chiamata LLM (FR-T2). usd = costo nativo, eur = convertito.
CREATE TABLE IF NOT EXISTS llm_calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    scopo       TEXT NOT NULL,              -- conversion:p054 | router | answer | compile:RP | eval
    modello     TEXT NOT NULL,
    tok_in      INTEGER NOT NULL DEFAULT 0,
    tok_out     INTEGER NOT NULL DEFAULT 0,
    tok_cache_r INTEGER NOT NULL DEFAULT 0,
    tok_cache_w INTEGER NOT NULL DEFAULT 0,
    usd         REAL NOT NULL DEFAULT 0,
    eur         REAL NOT NULL DEFAULT 0,
    query_id    TEXT                         -- opzionale: lega la chiamata a una query
);

CREATE INDEX IF NOT EXISTS idx_llm_calls_scopo ON llm_calls(scopo);
CREATE INDEX IF NOT EXISTS idx_llm_calls_query ON llm_calls(query_id);

-- Conversione per pagina: rotta, modello finale, escalation, esito (Nota consolidata).
CREATE TABLE IF NOT EXISTS conversions (
    doc_id      TEXT NOT NULL,
    n           INTEGER NOT NULL,
    route       TEXT NOT NULL,              -- A | B
    model_used  TEXT NOT NULL,              -- modello che ha prodotto l'output accettato/finale
    escalations INTEGER NOT NULL DEFAULT 0, -- n. di gradini di escalation saliti
    status      TEXT NOT NULL,              -- ok | needs_human
    reasons     TEXT,                       -- motivi gate/lint dell'ultimo tentativo
    md_path     TEXT,
    usd         REAL NOT NULL DEFAULT 0,    -- costo totale della pagina (tutti i tentativi)
    ts          TEXT NOT NULL,
    PRIMARY KEY (doc_id, n)
);

-- Audit campionario (§M2.3/C): pagine Haiku ri-fatte con Opus e diffate.
CREATE TABLE IF NOT EXISTS audits (
    doc_id       TEXT NOT NULL,
    n            INTEGER NOT NULL,
    gate_flagged INTEGER NOT NULL,          -- il gate aveva flaggato la pagina?
    diff_found   INTEGER NOT NULL,          -- il diff Haiku-vs-Opus ha trovato differenze?
    gate_miss    INTEGER NOT NULL,          -- diff trovato MA gate non aveva flaggato = bug gate
    ts           TEXT NOT NULL,
    PRIMARY KEY (doc_id, n)
);

-- Albero di navigazione (Fase 2): nodi quadro/sezione/rigo/codice derivati dalla struttura
-- semantica degli heading (non dal numero di '#', incoerente nel markdown per-pagina).
CREATE TABLE IF NOT EXISTS nodes (
    id         INTEGER NOT NULL,
    doc_id     TEXT NOT NULL,
    parent_id  INTEGER,                   -- nodo padre (self-ref); NULL = radice
    kind       TEXT NOT NULL,             -- quadro | sezione | rigo | codice | sezione_doc
    level      INTEGER NOT NULL,          -- profondità canonica (1=quadro ...)
    title      TEXT NOT NULL,
    page_start INTEGER NOT NULL,
    page_end   INTEGER NOT NULL,
    ord        INTEGER NOT NULL,          -- ordine di lettura
    summary    TEXT,                      -- etichetta di navigazione scope-aware (D2)
    PRIMARY KEY (doc_id, id)
);

-- Feedback umano sulle pagine andate in revisione (chiusura del ciclo human-in-the-loop).
CREATE TABLE IF NOT EXISTS reviews (
    doc_id          TEXT NOT NULL,
    n               INTEGER NOT NULL,
    azione          TEXT NOT NULL,          -- corretta | falso_positivo
    revisore        TEXT NOT NULL,
    nota            TEXT,
    regole_flaggate TEXT,                   -- i motivi che il gate/lint avevano sollevato
    sha_rifiutato   TEXT,                   -- sha del markdown rifiutato (versione preservata)
    sha_risolto     TEXT,                   -- sha del markdown risolto (corretto o accettato)
    ts              TEXT NOT NULL,
    PRIMARY KEY (doc_id, n)
);

-- Evaluation (FR-E).
CREATE TABLE IF NOT EXISTS eval_cases (
    id          TEXT PRIMARY KEY,
    categoria   TEXT NOT NULL,              -- fattuale | procedurale | fuori_corpus | cross_anno
    domanda     TEXT NOT NULL,
    attesa_json TEXT
);

CREATE TABLE IF NOT EXISTS eval_results (
    run_id     TEXT NOT NULL,
    case_id    TEXT NOT NULL REFERENCES eval_cases(id),
    config     TEXT NOT NULL,               -- B | BD
    esiti_json TEXT,
    PRIMARY KEY (run_id, case_id, config)
);
