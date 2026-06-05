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

## §3 — Spike A vs B (campione stratificato, 9/10 pagine; p.4 fallita per 529)
Medie per classe (A=text-layer, B=VLM, stesso modello Opus 4.8):

| Classe | pag | overlap A | overlap B | numeri A | numeri B | $/pag A | $/pag B |
|---|---|---|---|---|---|---|---|
| single_column | 5 | 0,96 | 0,96 | 1,00 | 0,95 | 0,088 | 0,089 |
| table_heavy | 3 | 0,94 | 0,94 | 0,99 | 0,98 | 0,082 | 0,086 |
| anomalous | 1 | 1,00 | 0,99 | 1,00 | 1,00 | 0,038 | 0,050 |

Costo spike: **$1,48**. Ispezione visiva p.73: entrambe ricostruiscono la tabella; A cattura
anche l'intro delle sezioni.

### Caveat metodologici
- `token-overlap` è insensibile all'ordine; non basta a provare la fedeltà d'ordine sulle
  tabelle — mitigato dall'ispezione visiva.
- Il riferimento è il text-layer, quindi favorisce A per costruzione; il fatto che B (fonte
  indipendente) resti a 0,94-0,96 indica comunque buon accordo.
- Il gap numeri di B è in gran parte artefatto (numeri di pagina/footer correttamente omessi).
- Costo A≈B perché Opus su entrambe: il vantaggio di A richiede un modello più economico.

## §4 — Raccomandazione (da confermare con review umana)
**Rotta A primaria su tutte le classi di PF1**, con VLM retrocesso a **verificatore** sulle
pagine `anomalous` (routing guidato dalla classificazione §2). Motivi:
1. A eguaglia/batte B su struttura e fedeltà su tutte le classi del campione;
2. zero rischio di allucinazione di trascrizione (A non "inventa", legge il testo reale);
3. su questo documento non esistono pagine multi-colonna → il vantaggio chiave del VLM non si applica;
4. con un modello più economico A diventa nettamente più conveniente (da misurare).

**Routing autonomo mantenuto** come predisposizione: la classificazione §2 instrada per-pagina,
così il sistema gestisce da solo eventuali casi ostici (table_heavy/anomalous → VLM) senza
intervento umano. Su PF1 sarebbero pochissime pagine.

Il design del checksum NON cambia: due estrazioni indipendenti confrontate, divergenze → flag → revisione umana.

## Da completare
- Ritentare p.4 (table_heavy) fallita per 529, per chiudere il campione.
- Misurare la Rotta A con modello economico (Haiku) per quantificare il risparmio reale.
- Validazione umana della review affiancata (HTML) prima di convertire le restanti pagine.
