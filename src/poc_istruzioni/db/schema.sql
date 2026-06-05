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

-- Ledger: una riga per ogni chiamata LLM (FR-T2). eur nella valuta configurata.
CREATE TABLE IF NOT EXISTS llm_calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    scopo       TEXT NOT NULL,              -- conversion:p054 | router | answer | compile:RP | eval
    modello     TEXT NOT NULL,
    tok_in      INTEGER NOT NULL DEFAULT 0,
    tok_out     INTEGER NOT NULL DEFAULT 0,
    tok_cache_r INTEGER NOT NULL DEFAULT 0,
    tok_cache_w INTEGER NOT NULL DEFAULT 0,
    eur         REAL NOT NULL DEFAULT 0,
    query_id    TEXT                         -- opzionale: lega la chiamata a una query
);

CREATE INDEX IF NOT EXISTS idx_llm_calls_scopo ON llm_calls(scopo);
CREATE INDEX IF NOT EXISTS idx_llm_calls_query ON llm_calls(query_id);

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
