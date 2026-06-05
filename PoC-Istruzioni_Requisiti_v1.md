# PoC ISTRUZIONI — Assistente Q\&A sulla compilazione dei modelli dichiarativi · Requisiti funzionali e tecnici v1

**Progetto:** Ancora — efficienza degli studi contabili **Destinatario:** agente di implementazione (Claude Code) **e** lettore umano: ogni requisito ha una riga "in parole povere" prima della specifica. **Repo:** nuova e autonoma (suggerito: `poc-istruzioni-qa`). **Questo documento è autosufficiente**: non dipende da altri progetti/PoC. **Corpus pilota:** Istruzioni *Redditi Persone Fisiche, Fascicolo 1*, edizione **2026** (file fornito: `PF1_istruzioni_2026_agg 13 05 2026.pdf`) \+ edizione **2025** (da procurare, per il confronto cross-anno).

---

## 0\. Contesto e obiettivo (leggimi)

I commercialisti compilano i modelli dichiarativi (Redditi PF, 730, IVA…) usando le **istruzioni ministeriali**: PDF di \~100-200 pagine che spiegano, quadro per quadro e rigo per rigo, cosa indicare, con quali **codici**, **limiti** e **condizioni**. L'obiettivo della PoC: un assistente che risponde con accuratezza verificabile a domande come *"dove indico le spese sanitarie di mio figlio e con che codice? c'è una franchigia?"* → *"Righi RP1-RP4, codice 1, franchigia €129,11 — pag. 54, istruzioni PF1 ed. 2026 (periodo d'imposta 2025)"*.

**Strategia in due stadi (entrambi in scope):**

- **Stadio B — "leggi bene, servi intero":** conversione del PDF in Markdown strutturato tramite modello vision (pagina come immagine) → router che individua la sezione pertinente → l'**intera sezione** in contesto (con prompt caching) → risposta con citazioni. Niente vector store: a questa scala il retrieval è una classificazione su \~20 sezioni.  
- **Stadio D — "compila i fatti in dati":** un modello potente estrae **una tantum** dal Markdown un **DB strutturato** (rigo→colonne→codici→limiti→condizioni); a runtime un **modello piccolo** risponde facendo lookup sul DB (i numeri vengono letti da dati, mai "ricordati") \+ sezione di testo per le spiegazioni.

**Quattro requisiti trasversali non negoziabili** (dettagliati in §5-§6): (1) **tracciabilità totale** — ogni artefatto e ogni risposta ricostruibili a ritroso fino ai byte del PDF; (2) **ogni risposta dichiara i passaggi usati** (answer trace); (3) **contabilità completa di chiamate e token/€**; (4) **evaluation misurabile e ripetibile**.

**Vincoli:** Python; esecuzione locale; LLM via API Anthropic dietro interfaccia astratta `LlmClient` (Opus-class per compilazione one-time, Haiku/Sonnet-class per runtime); SQLite; nessun vector store in questa PoC (non-goal esplicito).

**Fatti già noti sul file** (da analisi preliminare, da ri-verificare in Fase 1): 183 pagine A4, **testo nativo** (niente OCR), **layout a 2 colonne** su tutte le pagine campionate, header ripetuto per pagina, \~290k token totali stimati, poche tabelle delineate (i codici sono per lo più elenchi testuali), **artefatto noto**: su almeno una pagina il layer testuale contiene la dicitura spuria "REDDITI SC 2023" → l'identità del documento va validata dal contenuto, non dall'header.

---

## 1\. Stadio B — Requisiti funzionali

### FR-B1 — Rendering pagine

*In parole povere: trasformare ogni pagina del PDF in un'immagine, perché il testo "nascosto" del PDF mente (colonne mischiate, testi fantasma).*

PyMuPDF, \~150-200 DPI, PNG per pagina, nominate `p{NNN}.png`, hash e provenance registrati. **Accettazione:** 183 immagini riproducibili (stesso input → stessi hash).

### FR-B2 — Trascrizione VLM \+ checksum incrociato

*In parole povere: un modello vision trascrive ogni pagina in Markdown fedele. Per sicurezza, si confronta con il testo interno del PDF: dove i due divergono troppo, la pagina va a revisione umana.*

- Trascrizione pagina-per-pagina (temperature 0), prompt vincolato: fedeltà totale, niente riassunti/correzioni, struttura con heading (`##` quadro, `###` rigo), elenchi per i codici, numero di pagina in coda a ogni sezione.  
- **Cross-check automatico:** similarità token-overlap tra output VLM e testo estratto dal layer PDF (due estrazioni indipendenti) → sotto soglia configurabile, pagina flaggata `needs_review`; lista per revisione umana.  
- Cucitura delle sezioni che proseguono tra pagine. **Accettazione:** markdown completo; % pagine flaggate riportata; campione di 10 pagine verificato a mano documentato.

### FR-B3 — Struttura del Markdown (il formato-asset)

*In parole povere: un file per quadro, con metadati in testa e la gerarchia quadro→rigo come titoli. È l'asset che tutto il resto consuma.*

```
---
modello: REDDITI-PF-F1   edizione: 2026   periodo_imposta: 2025
agg_edizione: 2026-05-13   pagine: 54-78   sha256_sorgente: ...
---
## QUADRO RP — Oneri e spese
> Regole generali del quadro: franchigia €129,11 sulle spese sanitarie ...
### Righi RP1-RP4 — Spese sanitarie  [pag. 54]
Codici: **1** = ... · **2** = ...
Vedi anche: [rigo RN32, PF 2025](ref://PF1-2025/RN/RN32)
```

Regole: frontmatter YAML obbligatorio; pagina di origine annotata per sezione; header/footer di pagina rimossi; artefatti noti (dicitura spuria) rimossi e loggati; **rinvii ad altri righi/modelli/anni marcati come link espliciti** `ref://modello-edizione/quadro/rigo` (saranno tool-ready per il futuro agente). **Accettazione:** un file per quadro; lint strutturale (gerarchia heading coerente, frontmatter valido, pagine monotone) verde.

### FR-B4 — Router

*In parole povere: data la domanda, scegliere quale sezione caricare. È una classificazione su \~20 sezioni, non una ricerca su migliaia di chunk.*

Cascata: (1) **alias-table** curata e versionata (es. "farmacia/ticket/occhiali → RP"), match deterministico; (2) fallback: classificatore LLM economico con in input **l'indice del fascicolo** \+ la domanda → top-1/top-2 sezioni con confidenza. Output sempre tracciato (metodo usato, candidati, confidenza). **Accettazione:** accuratezza ≥90% su un set etichettato di ≥40 domande (vedi eval); l'alias-table è un file dati modificabile senza toccare codice.

### FR-B5 — Serving long-context con prompt caching

*In parole povere: si mette l'intera sezione nel contesto del modello. La parte fissa (istruzioni di sistema \+ sezione) viene "cachata" dal provider: dalle chiamate successive in poi costa \~1/10 ed è più veloce.*

- Struttura prompt rigida: `[system fisso] + [sezione markdown] (cache_control)` \+ `[domanda]` in coda. Il prefisso deve restare **byte-identico** tra chiamate (disciplina di template).  
- Caso incerto del router: top-2 sezioni entrambe in contesto. **Accettazione:** dalla seconda query sulla stessa sezione, il ledger (§6) mostra token `cache_read` \> 0 e costo/query ridotto di ≥70%.

### FR-B6 — Generazione risposta: citazioni, rifiuto, answer trace

*In parole povere: la risposta cita sempre quadro/rigo/pagina/edizione; se l'informazione non è nella sezione, lo dice invece di inventare; e ogni risposta porta con sé il "verbale" dei passaggi fatti.*

- **Citazioni obbligatorie:** ogni affermazione fattuale → (quadro, rigo, pagina, edizione). Formato citazione machine-parseable nel JSON di risposta \+ leggibile nel testo.  
- **Politica di rifiuto:** se la sezione non contiene la risposta → dichiararlo \+ indicare (se deducibile dall'indice) quale sezione/documento servirebbe. Mai riempitivi.  
- **Answer trace (requisito chiave):** ogni risposta produce un oggetto strutturato e una resa leggibile:

```json
{"query_id": "...", "timestamp": "...",
 "route": {"metodo": "alias|llm", "sezioni": ["RP"], "confidenza": 0.93},
 "llm_calls": [{"scopo": "router", ...}, {"scopo": "answer", ...}],
 "tools": [],
 "evidenze": [{"sezione": "RP", "rigo": "RP1", "pagina": 54, "span": "..."}],
 "costo": {"chiamate": 2, "token_in": 31200, "token_cached": 29800, "token_out": 410, "eur": 0.014},
 "esito": "answered|refused|escalation_suggerita"}
```

**Accettazione:** il CLI mostra per ogni risposta la trace umana ("Ho instradato su RP via alias 'farmacia' → caricata sezione RP (pag. 54-78, cache hit) → risposta basata su righi RP1-RP4 pag. 54 → costo €0,014"); la trace è persistita e interrogabile per `query_id`.

## 2\. Stadio D — Requisiti funzionali

### FR-D1 — Schema dell'ontologia del modulo

*In parole povere: lo schema dati formale del dominio "modulo": modello→quadro→rigo→colonna→codici, con limiti, condizioni e riferimenti. Definito una volta, vale per tutti i modelli futuri.*

Entità minime: `Modello(edizione, periodo_imposta)`, `Quadro`, `Rigo`, `Colonna`, `Codice(valore, label)`, `Vincolo(tipo: franchigia|limite|percentuale|massimale, valore, unità)`, `Condizione(testo, soggetti)`, `Alias(termine_colloquiale → rigo/codice)`, `Rif(rigo → ref:// target)`. Ogni record porta `fonte: {sezione, pagina}` e `estratto_da: {modello_llm, run_id}`. **Accettazione:** schema in `schema.sql` \+ pydantic; documentato con 3 esempi popolati a mano.

### FR-D2 — Compilatore (estrazione one-time con modello potente)

*In parole povere: il modello potente legge il Markdown (non il PDF) e popola il DB, sezione per sezione, con output JSON vincolato. Si valida automaticamente e a campione da umano. Si rifà una volta per edizione.*

- Input: markdown di FR-B3. Output: record conformi a FR-D1 (structured output / JSON schema).  
- Validazioni automatiche: conformità schema, codici univoci per rigo, numerici parsabili, pagine esistenti, ogni record con fonte.  
- **Spot-check umano:** campione ≥15 record (tutti i vincoli numerici del quadro pilota inclusi) verificato contro il markdown e contro il PDF; esiti registrati.  
- Generazione **alias e domande sintetiche** per rigo (es. "scontrino farmacia" → RP1 cod. 1\) come parte della compilazione, marcate `synthetic`.  
- Scope PoC: **quadro RP completo** (estendibile a un secondo quadro se i tempi lo consentono). **Accettazione:** DB popolato per RP ed. 2026; 0 errori di validazione; spot-check documentato; costo di compilazione riportato dal ledger.

### FR-D3 — Lookup DB come tool

*In parole povere: il DB si interroga con funzioni semplici e deterministiche, esposte al modello come "tool".*

Funzioni minime: `codici_per_rigo(modello, edizione, rigo)`, `vincoli(rigo|codice)`, `dove_va(termine)` (via alias), `diff_edizioni(rigo, ed1, ed2)`. **Accettazione:** funzioni testate con pytest su casi noti; ogni invocazione loggata nella answer trace.

### FR-D4 — Runtime con modello piccolo \+ tools

*In parole povere: a runtime risponde un modello economico che PRIMA consulta il DB per i fatti (codici, limiti) e POI, se serve spiegare, legge la sezione di testo. I numeri vengono sempre dal DB.*

- Modello runtime: Haiku/Sonnet-class, con tools `lookup` (FR-D3) e `leggi_sezione` (la sezione markdown, cachata).  
- **Regola dura:** valori numerici e codici nella risposta DEVONO provenire da un risultato di `lookup` (verificato programmaticamente: ogni numero nella risposta deve matchare un campo restituito dai tool) — altrimenti la risposta è flaggata.  
- Answer trace estesa con le chiamate tool e i record usati. **Accettazione:** sul golden set di domande "fattuali" (codici/limiti), 100% dei valori numerici riconducibili a record DB; confronto B vs B+D prodotto dall'eval (§7).

### FR-D5 — Confronto cross-anno

*In parole povere: "cosa cambia per le spese sanitarie rispetto all'anno scorso?" deve diventare una query su due edizioni, non una rilettura di 60 pagine.*

Richiede: conversione (B1-B3) e compilazione (D2) anche dell'edizione 2025 **limitata al quadro RP**. **Accettazione:** `diff_edizioni` risponde correttamente su ≥3 differenze reali note (verificate a mano) tra ed. 2025 e 2026\.

## 3\. Requisiti trasversali

### FR-T1 — Tracciabilità end-to-end

Catena ricostruibile per ogni risposta: `PDF (sha256) → immagine pagina → markdown sezione (hash, versione) → [record DB] → risposta (query_id)`. Ogni artefatto ha provenance (origine, run\_id, timestamp, modello LLM usato). Nessun artefatto "orfano". **Accettazione:** comando `trace <query_id>` che stampa l'intera catena in formato leggibile.

### FR-T2 — Ledger chiamate e costi (token accounting)

*In parole povere: ogni singola chiamata LLM viene registrata con scopo, token (anche cached) e costo in €. Si deve poter rispondere a "quanto è costata questa risposta?", "quanto la compilazione?", "quanto oggi?".*

- Wrapper unico `LlmClient` (nessuna chiamata fuori da esso) che logga: timestamp, modello, **scopo** (`conversion:p054 | router | answer | compile:RP | eval`), token input/output/`cache_read`/`cache_write` (dai campi usage dell'API), costo calcolato da `config/prices.toml` (tariffe per modello, modificabili).  
- Tabella `llm_calls` \+ aggregazioni: `report costs --by purpose|day|query|model`. **Accettazione:** totale per fase riportato nel report finale; per ogni query il costo appare nella answer trace; i prezzi sono config, non hardcoded.

### FR-T3 — Riproducibilità

Stessi input \+ stessa config → stessi artefatti (hash) per le parti deterministiche; per le parti LLM, output versionati con `run_id` e mai sovrascritti.

## 4\. Evaluation (FR-E)

*In parole povere: un set di domande con risposte verificate da umani, e un runner che misura tutto — accuratezza, citazioni, rifiuti, costi — ripetibile a ogni modifica.*

- **FR-E1 Golden set:** ≥40 domande etichettate su PF1, in 4 categorie: *fattuali* (codice/limite — risposta numerica esatta), *procedurali* (come/dove indicare), *fuori-corpus* (es. domande IVA → rifiuto atteso), *cross-anno* (per D5). Sorgenti: casi curati a mano \+ domande raccolte dai fiscalisti. Formato: YAML con risposta attesa, citazione attesa, categoria.  
- **FR-E2 Metriche:** correttezza risposta (match esatto per le fattuali; rubrica \+ LLM-judge con validazione umana per le procedurali); **fedeltà delle citazioni** (check programmatico: la pagina/sezione citata esiste e contiene i termini chiave dell'affermazione); accuratezza router; correttezza dei rifiuti; per D: % numeri riconducibili a record DB; costo e latenza per query.  
- **FR-E3 Runner e confronto:** `eval run --config B|BD` → stesso golden set sulle due configurazioni → **tabella comparativa B vs B+D** (accuratezza per categoria, costo medio/query, latenza). È il deliverable decisionale della PoC.  
- **FR-E4 Regressione:** l'eval gira a ogni modifica significativa; i risultati sono persistiti per run e confrontabili nel tempo.

## 5\. Data model (SQLite)

```
documents(id, modello, edizione, periodo_imposta, agg_data, sha256, path)
pages(doc_id, n, png_path, png_sha, vlm_status, overlap_score, needs_review)
sections(id, doc_id, quadro, titolo, pagine, md_path, md_sha, versione)
ontology_*(...)            -- per FR-D1 (righi, codici, vincoli, alias, refs)
queries(query_id, testo, ts, route_json, esito, costo_eur, latenza_ms)
answer_traces(query_id, trace_json)
llm_calls(id, ts, scopo, modello, tok_in, tok_out, tok_cache_r, tok_cache_w, eur, query_id?)
eval_cases(id, categoria, domanda, attesa_json) · eval_results(run_id, case_id, config, esiti_json)
```

## 6\. Stack tecnico

Python 3.11+ · uv · **PyMuPDF** (rendering) · **Anthropic SDK** dietro `LlmClient` (Opus-class: conversione FR-B2 e compilazione FR-D2; Haiku/Sonnet-class: router e runtime; prompt caching via cache\_control) · pydantic v2 · SQLite (no ORM) · typer (CLI) · structlog · pytest. **Non-goal espliciti:** vector store, OCR, fine-tuning, UI web (il CLI basta per la PoC).

## 7\. Roadmap a fasi

| Fase | Contenuto | Effort | Done quando |
| :---- | :---- | :---- | :---- |
| 0 | Scaffolding \+ **FR-T2 ledger PRIMA di tutto** (ogni chiamata successiva nasce misurata) \+ `LlmClient` | 0,5 g | `report costs` funziona su una chiamata di prova |
| 1 | FR-B1→B3: rendering, trascrizione VLM con checksum, markdown PF1-2026 | 1-2 g | Markdown completo, lint verde, pagine flaggate gestite |
| 2 | FR-B4→B6: router, serving cachato, risposte con citazioni e answer trace | 1-2 g | 10 domande di prova con trace completa e cache hit dimostrato |
| 3 | FR-E1→E2: golden set v1 (≥40) \+ eval runner su config B | 1 g | Report accuratezza/citazioni/costi su B |
| 4 | FR-D1→D4: schema, compilazione quadro RP, lookup, runtime con tools | 2-3 g | DB validato \+ spot-check; regola "numeri solo da DB" attiva |
| 5 | FR-D5: edizione 2025 (solo RP) \+ diff cross-anno | 1 g | 3 differenze reali verificate |
| 6 | FR-E3: eval comparativa **B vs B+D** \+ report finale (accuratezza, costi, raccomandazione) | 0,5-1 g | Tabella comparativa \+ report costi totale PoC |

Stop-point per validazione umana: fine Fase 1 (qualità markdown) e fine Fase 3 (baseline B) prima di investire su D.

## 8\. Criteri di successo complessivi

1. Risposte con **citazioni verificate** (fedeltà ≥95% sul golden set) e rifiuti corretti sulle domande fuori-corpus.  
2. **Ogni risposta spiegabile**: answer trace completa e comando `trace` funzionante (FR-T1).  
3. **Contabilità totale**: costo per query, per fase e complessivo della PoC, da ledger (FR-T2).  
4. **Confronto B vs B+D misurato** sul golden set: la decisione "D quanto migliora e quanto costa" presa con numeri.  
5. Asset riusabili: markdown strutturato, schema ontologia, alias-table, golden set.

## 9\. Fuori scope (esplicito) e predisposizioni al futuro

Fuori scope: orchestratore agentico completo; altri modelli oltre PF1; FAQ e circolari; integrazione col corpus normativo (TUIR versionato — esiste come workstream separato; qui basta che i riferimenti normativi citati nelle istruzioni siano salvati come stringhe strutturate in FR-D1); vector retrieval; UI. Predisposizioni richieste (costano \~zero ora): i rinvii come link `ref://` (FR-B3), il lookup e `leggi_sezione` già con interfaccia da tool (FR-D3/D4), lo schema ontologia multi-modello (FR-D1) — sono i punti di aggancio del futuro agente e del layer normativo.

## 10\. Trappole note (dall'analisi del file — leggere prima di iniziare)

1. **Layout a 2 colonne** su tutte le pagine → mai fidarsi del layer testuale per l'ordine di lettura (per questo FR-B1/B2 usano le immagini).  
2. **Testo-fantasma** ("REDDITI SC 2023" su pagina con contenuto PF 2026\) → identità del documento validata dal contenuto; artefatti rimossi e loggati.  
3. **Header/footer ripetuti** per pagina → strippare prima del checksum, o l'overlap-score si gonfia.  
4. **Regole "a monte"** (franchigie/limiti dichiarati a inizio quadro, validi per tutti i righi) → mai servire un rigo senza l'intro del suo quadro (il serving per sezione intera di B5 lo garantisce; attenzione se in futuro si spezzasse di più).  
5. **Iper-referenzialità** ("riportato nel rigo RN32 del Mod. REDDITI PF 2025, ovvero nel rigo 159 del 730/2025") → i rinvii vanno marcati come link, non persi nel testo.  
6. **Edizioni aggiornate infra-stagione** (il file stesso è un "agg. 13/05/2026") → `agg_edizione` nel frontmatter; ri-pubblicazioni \= nuova versione della sezione, mai sovrascrittura.  
7. **Disciplina del prefisso per il caching**: un byte diverso nel prompt fisso \= cache persa → template rigidi e versionati.

