# NOTA INTEGRATIVA — Stop temporaneo e verifica della rotta di conversione (FR-B1/B2)

**Priorità: eseguire PRIMA di proseguire qualsiasi lavoro di conversione.**
**Integra:** `PoC-Istruzioni_Requisiti_v1.md` (§0 e Trappola 1 aggiornati) — questa nota la dettaglia operativamente.

## Cosa è cambiato

L'assunzione che motivava la rotta VLM-first ("layout a 2 colonne su tutte le pagine")
è risultata **errata**: una verifica geometrica corretta (gutter-test + distribuzione
larghezza righe) mostra che il PF1 è **prevalentemente a colonna singola a piena
larghezza**. Il vantaggio chiave del VLM (reading order su multi-colonna) qui pesa
molto meno del previsto. La rotta "layer testuale + strutturazione LLM senza vision"
diventa una candidata seria: più semplice, più economica, e senza rischio di
allucinazione di trascrizione.

**Il lavoro VLM già fatto NON è sprecato**: il markdown prodotto serve comunque —
come candidato nel confronto e/o come testimone del checksum incrociato.

## Direttive

### 1. STOP all'estensione del lavoro VLM
Non proseguire la conversione né raffinare i prompt finché l'analisi sotto non è
conclusa e la decisione presa.

### 2. Analisi di layout sull'INTERO documento (183 pagine, non un campione)
Per ogni pagina, calcolare e persistere:
- **Gutter-test**: n. di parole il cui bounding box attraversa la banda centrale
  (x ∈ [0.47w, 0.53w]) — valori alti ⇒ colonna singola;
- **Distribuzione larghezza righe** (ricostruzione righe da `top`, span x1−x0 / w):
  mediana e % righe > 0.75w;
- **Densità tabellare**: n. di `lines` + `rects` (pdfplumber);
- **Anomalie**: mismatch tra header di pagina e contenuto (es. dicitura spuria
  "REDDITI SC 2023"), pagine con immagini, pagine quasi vuote.

Output: `layout_analysis.csv` con classificazione per pagina:
`single_column | multi_column | table_heavy | anomalous`
+ statistiche di sintesi nel report. Questa classificazione è un asset permanente
(servirà anche per il routing per-pagina, vedi §4).

### 3. Spike comparativo su campione STRATIFICATO dall'analisi
Selezionare 10-15 pagine che coprano tutte le classi rilevate (incluse le più
ostiche: table_heavy, anomalous, liste dense di codici). Confrontare:

- **Rotta A (nuova):** estrazione layer testuale (pdfplumber, con metadati font per
  inferire titoli/grassetti) + passata LLM **testo→markdown** (niente vision);
- **Rotta B (esistente):** la pipeline VLM page-as-image già costruita — riusare il
  markdown già prodotto dove disponibile.

Metriche di confronto (per pagina, persistite):
1. fedeltà strutturale (heading quadro/rigo corretti, gerarchia liste);
2. integrità delle liste codici (numero↔etichetta mai disallineati);
3. fedeltà testuale vs sorgente (token-overlap, come il checksum esistente);
4. costo per pagina (dal ledger, purpose `spike:conversion-route`) e tempo;
5. failure modes osservati (descrizione libera).

### 4. Criteri di decisione (espliciti, da applicare ai numeri)
- Se la Rotta A eguaglia o batte la B su struttura+fedeltà nel ≥95% delle pagine
  del campione → **A primaria**, VLM retrocesso a verificatore sulle pagine
  flaggate/anomale (risparmio + zero rischio trascrizione).
- Se la B è chiaramente superiore sulle classi difficili → **B resta primaria**,
  A diventa testimone del checksum.
- **Ibrido ammesso e anzi probabile:** routing per-pagina guidato dalla
  classificazione del §2 (A per `single_column`, B per `table_heavy`/`anomalous`).

In ogni caso il design del checksum NON cambia: due estrazioni indipendenti
confrontate, divergenze → flag → revisione umana.

### 5. Deliverable prima di riprendere la Fase 1 su scala
Breve **decision report**: classificazione layout (sintesi), tabella comparativa
A vs B con i numeri, costo dello spike dal ledger, raccomandazione motivata.
Stop-point: validazione umana del report prima di convertire le restanti pagine.