# Report di stato — PoC Istruzioni (conversione PF1)

**Aggiornato:** 2026-06-05 · **Commit:** 36 · **Test:** 112 verdi · **Costo LLM finora:** $2,35 / €2,05 (59 chiamate)

---

## 1. Dove siamo

- **Fase 0 (fondamenta)** — completata e pushata: ledger token/€ (FR-T2), `LlmClient` (unico
  accesso ai modelli), config tipizzata, schema SQLite, provenance, CLI `report costs`.
- **Fase 1 (ingestion/conversione)** — B1 (rendering 183 pagine) fatto; la **rotta di
  conversione è stata ri-progettata** dopo due note strategiche e ora la **pipeline step-0**
  (routing + escalation + gate + lint + audit + breaker) è **costruita e testata in mock**.
  Manca: B.5 (validazione identità frontespizio) e il **run completo a pagamento**.

## 2. Scoperte rilevanti (con evidenze)

1. **L'assunzione "PF1 a 2 colonne" era errata.** Analisi layout su tutte le 183 pagine:
   **166 single_column (90,7%), 0 multi_column, 16 table_heavy, 1 anomalous**
   (`data/.../layout_analysis.csv`). Validazione: single_column con mediana larghezza riga 0,79
   e gutter_ratio alto. → Il vantaggio chiave del VLM (reading order) **non si applica** qui.

2. **La Rotta A (text-layer + LLM, no vision) eguaglia il VLM su tutte le classi.** Spike
   comparativo 10/10 pagine (Opus su entrambe): overlap e recall numeri ~pari per
   single_column, table_heavy e anomalous; ispezione visiva p.73 conferma che A ricostruisce
   le tabelle. → Rotta A primaria; VLM retrocesso a verificatore/escalation.

3. **Haiku costa ~7x meno ma non è sicuro da solo.** Cella economica (p.6/62/146): overlap
   identico a Opus, ma cala sui numeri (p.6: recall 0,86). Misura del **tasso di escalation
   E = 20%** (3/15 pagine) col gate rafforzato → zona grigia → **Graduata** scelta.

4. **Un audit-validation ha catturato un bug del gate.** Eseguendo il gate sugli output Opus
   noti-buoni, `has_repetition` risultava un **falso positivo sulle tabelle** (colonne/ditto
   ricorrenti). Corretto con la diversità-righe → ora il gate boccia **solo p.1** (artefatto
   reale). Questo valida l'idea dell'audit campionario (§M2.3): scopre i *miss del gate*.

5. **Routing predittivo magro, escalation reattiva al centro.** La Rotta A-Opus non fallisce
   in nessuna classe → niente "firme di fallimento" per un pre-routing aggressivo. La regola:
   `anomalous → VLM` (p.1: il text-layer promuove il ghost "REDDITI SC 2023" a identità), tutto
   il resto → Rotta A; gli slip stocastici di Haiku li intercetta il **gate + escalation**.

6. **A.2 (pre-routing per densità numerica) NON è supportata dai dati.** La densità non separa
   i fallimenti di Haiku dalle pagine OK (p.070 = 49 numeri OK vs p.157 = 30 FAIL): nessuna
   soglia isola i fail senza catturare ~metà delle pagine. → Scartata; difesa affidata al gate.

## 3. Architettura costruita (step-0 generico, tutto in config per tipo-documento)

- **Routing** (`ingest/routing.py`): `anomalous → VLM`, altrimenti Rotta A. PF1: 182→A, 1→B.
- **Escalation Graduata** (`ingest/convert.py`): Haiku → Opus-testo → VLM → coda umana, salendo
  di gradino quando gate+lint non passano; `force_strong` (circuit breaker) salta l'economico.
- **Gate** (`ingest/checks.py`): preservazione numeri (esclude numero di pagina), overlap,
  pair-check liste codici (anti-scambio), guardia parole critiche (negazioni), ripetizione
  (robusta su tabelle), artefatti. Heading/copertura = warning non bloccanti.
- **Lint d'igiene** (`ingest/lint.py`): dingbat non mappato, simbolo doppio, header nel corpo,
  numero pagina orfano (fail bloccanti) — difende la classe invisibile al checksum.
- **Preprocessore Rotta A** (`ingest/textroute.py`): dingbat→`-`, strip header/footer, indizi font.
- **Audit campionario 10%** + **circuit breaker** + **governance** (rotte, escalation_rate,
  needs_human, gate-miss) loggati nelle tabelle `conversions`/`audits`.
- CLI: `poc ingest layout | route | measure-escalation | convert` (+ `report costs`).

## 4. Criticità e problemi aperti

- **Run completo non ancora eseguito** (183 pagine, ~$5-6 stimati): è il prossimo passo a pagamento.
- **B.5 (validazione identità frontespizio) non implementata.** Senza, un PDF sbagliato non
  verrebbe intercettato all'avvio. Pianificata come ultimo step di codice prima del run.
- **Dipendenza dal gate per la sicurezza numerica.** Haiku perde numeri in modo stocastico
  (~20%); il gate+escalation+audit lo coprono, ma se il gate avesse un *miss* un numero
  sbagliato potrebbe propagarsi. Mitigazioni: audit 10% + circuit breaker; **lo spot-check
  umano di FR-D2 va fatto contro il PDF, non solo contro il markdown** (una corruzione nel
  markdown si propaga "validata").
- **Caveat del gate:** `token-overlap` è insensibile all'ordine; il pair-check codici richiede
  il formato "N = etichetta" in entrambe le fonti; il pair-check sulle **triple**
  `(regione, aliquota, formula)` per le tabelle di aliquote (§B.6) non è ancora implementato.
- **Edizione 2025 non procurata** → blocca FR-D5 (confronto cross-anno) e la categoria
  cross-anno del golden set (FR-E1).
- **Decision report interim:** `docs/decision_report_conversione.md` e
  `docs/findings_e_decisione_escalation.md` vanno chiusi col consuntivo del run (E effettivo,
  escalation per causa, esiti audit, eventuali attivazioni del breaker, costi reali).
- **Haiku-vs-tabelle:** non misurato sistematicamente quanto Haiku regga le `table_heavy`
  (lo spike usava Opus); la Graduata le manda comunque ad Haiku per prime, con escalation a rete.

## 5. Costi a consuntivo (dal ledger, FR-T2)
**$2,35 / €2,05, 59 chiamate.** Di cui: VLM `conversion:*` (calibrazione + spike lato B + retry)
~$1,17; Rotta A `spike:routeA` ~$0,82; misure escalation Haiku ~$0,36; smoke ~0.
Nota: i re-run pre-fix di idempotenza pesano ~$0,30 (non si ripeterebbero ora).

## 6. Prossimi passi (ordine D della nota consolidata)
1. **B.5** validazione identità (p.1) + regression test gate artefatto (già verde).
2. **Mini-run di prova** su ~5 pagine (~$0,1) per validare la pipeline dal vivo.
3. **Run completo** 183 pagine (~$5-6) con governance loggata.
4. **Decision report finale** col consuntivo; stop-point umano sul markdown.
5. (Poi Fase 2: router + serving cachato + risposte con citazioni.)

## 7. Stato repo
- 112 test (unit + integrazione in mock), `ruff` pulito, working tree pulito.
- Artefatti dati (`data/`) non versionati; `layout_analysis.csv`, markdown e review HTML su disco.
- Memoria di progetto aggiornata (decisioni e razionali) per continuità tra sessioni.
