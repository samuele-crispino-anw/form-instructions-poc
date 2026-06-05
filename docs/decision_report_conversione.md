# Decision report — rotta di conversione (Nota strategica §5)

**Stato:** bozza per validazione umana (stop-point prima di convertire le restanti pagine).

## Contesto
L'assunzione "PF1 tutto a 2 colonne" che motivava la rotta VLM-first è risultata errata.
Verifica condotta su tutte le 183 pagine + spike comparativo A (text-layer) vs B (VLM).

## §2 — Analisi layout (183 pagine)
| Classe | Pagine | % |
|---|---|---|
| single_column | 166 | 90,7% |
| multi_column | 0 | 0,0% |
| table_heavy | 16 | 8,7% |
| anomalous | 1 (p.1) | 0,5% |

Validazione: single_column con mediana larghezza riga 0,79 e gutter_ratio alto (testo che
attraversa il centro). Le `table_heavy` sono **tabelle dentro flusso a colonna singola**
(es. p.73: 270 linee/rettangoli), non veri layout multi-colonna. **Zero** pagine multi-colonna.

## §3 — Spike A vs B (campione stratificato, 10/10 pagine)
Medie per classe (A=text-layer, B=VLM, stesso modello Opus 4.8):

| Classe | pag | overlap A | overlap B | numeri A | numeri B | $/pag A | $/pag B |
|---|---|---|---|---|---|---|---|
| single_column | 5 | 0,96 | 0,96 | 1,00 | 0,95 | 0,088 | 0,089 |
| table_heavy | 4 | 0,95 | 0,95 | 0,97 | 0,96 | 0,077 | 0,082 |
| anomalous | 1 | 1,00 | 0,99 | 1,00 | 1,00 | 0,038 | 0,050 |

Costo spike: **~$1,65** (incl. retry p.4). Ispezione visiva p.73: entrambe ricostruiscono la
tabella; A cattura anche l'intro delle sezioni. **La Rotta A regge anche le table_heavy**
(B1: una pagina con 270 rect gestita bene da A NON va instradata a B).

### §3-bis — Cella economica (A3): Rotta A con Haiku vs Opus (single_column)
| pag | overlap Opus | overlap Haiku | numeri Opus | numeri Haiku | $ Opus | $ Haiku |
|---|---|---|---|---|---|---|
| 6 | 0,94 | 0,94 | 1,00 | 0,86 | 0,072 | 0,010 |
| 62 | 0,97 | 0,97 | 0,98 | 0,98 | 0,082 | 0,012 |
| 146 | 0,96 | 0,95 | 1,00 | 0,96 | 0,072 | 0,011 |

Haiku: **~7x più economico**, overlap identico, ma **cala su qualche numero** (p.6: 0,86).
Non sicuro come default cieco per il dominio numerico; **sicuro se il gate checksum/numeri
(escalation §C) ri-lavora le pagine che calano**. Risparmio potenziale in produzione: ~7x.

### A4 — pre-check font
Dimensione font piatta (tutto ~10pt): l'indizio "size" è inerte. Il **grassetto** distingue i
titoli (es. "Righi da RP1 a RP5"), ma è usato anche per enfasi inline → indizio rumoroso.
La struttura la porta l'LLM combinando bold + pattern testuali ("QUADRO/Rigo"); lo spike conferma
heading corretti. Nessun pattern PF1 hardcoded.

### Caveat metodologici
- `token-overlap` è insensibile all'ordine; non basta a provare la fedeltà d'ordine sulle
  tabelle — mitigato dall'ispezione visiva.
- Il riferimento è il text-layer, quindi favorisce A per costruzione; il fatto che B (fonte
  indipendente) resti a 0,94-0,96 indica comunque buon accordo.
- Il gap numeri di B è in gran parte artefatto (numeri di pagina/footer correttamente omessi).
- Costo A≈B perché Opus su entrambe: il vantaggio di A richiede un modello più economico.

## §4 — Raccomandazione (da confermare con review umana)
**Rotta A primaria su tutte le classi di PF1.** Motivi:
1. A eguaglia/batte B su struttura e fedeltà su TUTTE le classi del campione (incl. table_heavy);
2. zero rischio di allucinazione di trascrizione (A legge il testo reale, non "inventa");
3. su questo documento non esistono pagine multi-colonna → il vantaggio chiave del VLM non si applica;
4. con Haiku la Rotta A è ~7x più economica.

**La regola predittiva (§B) è — onestamente — magra:** la Rotta A-Opus non fallisce in nessuna
classe, quindi non ci sono "firme di fallimento" su cui costruire pre-routing aggressivo. La
regola predittiva resta minimale (default A; →VLM solo per pagine dove il text-layer è
genuinamente inutile, es. quasi-vuote/immagine). **Il peso lo porta l'escalation reattiva (§C)**:
è anche ciò che rende sicuro usare Haiku (i cali numerici vengono intercettati dal checksum e
ri-lavorati). Predittivo + reattivo insieme = autonomia sui casi complessi previsti e imprevisti.

**Showcase del checksum (p.1 anomalous):** la Rotta A legge il testo-fantasma "REDDITI SC 2023"
(presente nel layer testuale), la Rotta B non lo vede. Ognuna ha il punto cieco dell'altra →
il design a **due estrazioni indipendenti confrontate** resta valido chiunque vinca.

## Da completare
- Ritentare p.4 (table_heavy) fallita per 529, per chiudere il campione.
- Misurare la Rotta A con modello economico (Haiku) per quantificare il risparmio reale.
- Validazione umana della review affiancata (HTML) prima di convertire le restanti pagine.
