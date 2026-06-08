# Report finale — Fase 1: conversione PF1 2026 (183 pagine)

**Data:** 2026-06-08 · **Modalità:** Opus-first (priorità accuratezza) · **Esito:** completato.

## 1. Sintesi

Le **183 pagine** del PF1 2026 sono state convertite in markdown strutturato con la pipeline
step-0 (routing + escalation + gate + lint + audit + human-in-the-loop). Risultato:
**181/183 pagine pulite al primo colpo**; le 2 segnalazioni sono risultate **entrambe falsi
positivi** della stessa guardia (parole-critiche), causati da sillabazione PDF — già corretti.

## 2. Governance del run (FR-T2/D)

| Metrica | Valore |
|---|---|
| Pagine convertite | 183/183 |
| Rotta A (text-layer, Opus) | 182 |
| Rotta B (VLM, Opus) | 1 (p.1, frontespizio anomalous) |
| Escalation | 2 (p.71, p.170) |
| `needs_human` (aperte) | 0 (coda vuota) |
| Risolte da umano | 2 (p.71, p.170 — falsi positivi) |
| Gate-miss (audit) | 0 (audit non attivo in Opus-first) |
| **Costo totale del run** | **$15,30** (entro il tetto $20; in linea con la stima "Sicura" ~$15,9) |

Routing coerente con l'analisi di layout: 0 pagine multi-colonna, quindi quasi tutto Rotta A;
solo il frontespizio (anomalous, testo-fantasma) instradato al VLM.

## 3. Finding rilevante: falsi positivi da sillabazione

Le uniche 2 pagine bloccate (p.71, p.170) sono **falsi positivi**:
- **p.71:** la fonte ha `esclusi¬vamente` spezzata dal soft-hyphen → frammento "esclusi"; Opus ha
  ricongiunto "esclusivamente". La guardia contava "esclusi" 1→0 e flaggava.
- **p.170:** stessa cosa con `non¬ché` → "nonché". Guardia "non" 14→13.

In entrambi i casi **Opus ha fatto la cosa giusta** (ricongiunto la parola); era il **gate** a
sbagliare, ingannato dal soft-hyphen nel testo di riferimento.

**Loop di calibrazione (come previsto):** i 2 falsi positivi sono stati registrati via
`review resolve --action falso-positivo`; `false_positive_rules` segna `gate:parole_critiche: 2`,
tutti da sillabazione → segnale-dati netto.

**Fix applicato e validato:** `checks.dehyphenate()` rimuove il soft-hyphen dal testo di
riferimento prima dei confronti (numeri, overlap, parole-critiche, pair-check). Provato sui 2 casi
reali (de-ifenando i conteggi combaciano) + test unitari. Elimina l'intera classe di falsi positivi
per i run futuri.

## 4. Tracciabilità e provenienza

- Ogni `pNNN.md` porta un **frontmatter YAML**: doc_id, pagina, timestamp di generazione, rotta,
  modello, escalation, status, sha256 dell'immagine sorgente (catena PDF→immagine→markdown, FR-T1).
- Le pagine andate in revisione producono `needs_review.html` (cosa cercare) + snapshot immutabile
  della versione rifiutata (FR-T3).
- Decisioni umane in tabella `reviews` (audit trail + dataset di calibrazione regole).

## 5. Qualità (verifica a campione)

Ispezione manuale di pagine ad alto valore: p.75 (codici/franchigia: 129,11, 15.493,71, RP1,
"scontrino parlante", negazioni preservate); p.73/p.117/p.181 (table_heavy: tabelle ricostruite,
codici 12/13/14/55/57 preservati, convenzione "Colonne:"). Output fedele e strutturato.

## 6. Limiti noti / aperti (per le fasi successive)

- **Non-determinismo del modello:** lo stesso input può dare output diversi tra run (visto su
  p.181 col refuso "1,73%%" riprodotto/normalizzato a run diversi). Il gate+escalation lo gestisce.
- **Rischio attribuzione tabelle (§B.6):** il riordino delle tabelle aliquote è interpretativo e il
  gate a token non vede gli scambi (regione↔aliquota). Difesa rimandata: pair-check sulle triple +
  spot-check umano di FR-D2 **contro il PDF** + golden set.
- **Edizione 2025 non procurata** → blocca il confronto cross-anno (FR-D5).
- **Ottimizzazione costi rimandata:** pipeline economica (Haiku-first) disponibile a un flag
  (`--economical` / `[escalation].economical_first`), da valutare allo scaling dopo l'evaluation.

## 7. Costo complessivo del PoC finora

Il run di conversione è la voce principale; il totale del PoC (incl. esplorazioni, spike, misure,
review) è tracciato dal ledger (`poc report costs`). Il run completo: **$15,30**.

## 8. Stato e prossimi passi

- **Fase 1 (conversione) completa:** asset markdown per 183 pagine + provenienza + governance.
- Stop-point umano: validazione del markdown finale (campione già verificato) prima di Fase 2.
- **Prossimo (Fase 2 — serving):** router (alias-table + classificatore LLM con l'indice di p.2),
  serving long-context cachato, risposte con citazioni + answer-trace + rifiuto. Poi golden set
  ed eval baseline (Fase 3), quindi Stadio D (ontologia/lookup) e confronto B vs B+D.
