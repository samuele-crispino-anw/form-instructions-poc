# NOTA INTEGRATIVA 2 — Direttive per lo spike comparativo e il routing ibrido per-pagina

**Integra:** la nota "Stop temporaneo e verifica rotta di conversione" (§1-§5) e l'esito
dell'analisi layout (§2: 90,7% single_column, 0% multi_column, 16 table_heavy, 1 anomalous).
**Stato:** spike §3 approvato — con le direttive A sotto. In più, due deliverable
aggiuntivi (B e C) che trasformano l'esito dello spike in una pipeline autonoma.

---

## A. Direttive sullo spike (da applicare PRIMA del lancio)

### A1. Definire il giudice prima di lanciare
Il confronto A vs B su fedeltà strutturale e integrità liste NON può essere
auto-giudicato dal modello che ha prodotto gli output. Procedura:
- per ogni pagina del campione, produrre **diff side-by-side** (A vs B vs sorgente);
- il giudizio finale sugli elementi a rischio (liste codici numero↔etichetta,
  grassetti-titolo) è **umano** (review di Samuele, ~30 min);
- nei casi di disaccordo tra A e B, **Docling come terzo testimone** locale.
Dichiarare questi criteri nel report PRIMA dei risultati.

### A2. Decisione per-classe, non sul totale del campione
- Le 5 pagine `single_column` decidono la rotta per il **90,7%** del documento.
- Le 4 pagine `table_heavy` decidono SOLO il lato B dell'ibrido — che la Rotta A
  fallisca sulle griglie è **atteso**, non è una scoperta. Su quelle pagine la
  domanda vera è: **"il VLM basta, o serve la contingenza tabelle (LlamaParse)?"**
  → misurare questo.
- La pagina 1 `anomalous` è il **caso-vetrina del checksum**: la Rotta A legge il
  testo-fantasma ("REDDITI SC 2023"), la Rotta B non lo vede. Ognuna ha il punto
  cieco dell'altra → includere nel report come dimostrazione del perché il design
  a due estrazioni resta, chiunque vinca.

### A3. Cella economica aggiuntiva (quasi gratis)
Il confronto Opus-vs-Opus isola correttamente la variabile vision-vs-testo, ma la
promessa economica della Rotta A è "può girare con un modello piccolo". Aggiungere:
**Rotta A con Haiku/Sonnet su 2-3 pagine single_column** → misurare il degrado di
qualità rispetto ad A-con-Opus. Se il piccolo regge, il risparmio in produzione è
~10-15x sulla conversione: numero da mettere nel decision report.

### A4. Pre-check metadati font (5 minuti, prima di costruire la Rotta A)
La Rotta A inferisce titoli/struttura dai font: verificare subito che il PDF esponga
distinzioni utilizzabili (bold/size diversi per titoli di quadro/rigo, via
`pdfplumber` chars). Se i font fossero piatti o incoerenti → saperlo prima di
scrivere il prompt di strutturazione.

## B. Deliverable aggiuntivo 1 — La regola di routing ibrido (livello predittivo)

Obiettivo: instradamento automatico per-pagina (A economica di default, B/VLM sulle
pagine difficili), così la pipeline gestisce da sola i casi complessi.

- **B1. La regola nasce dai fallimenti MISURATI, non dalle caratteristiche presunte.**
  Ordine obbligato: spike → catalogare *dove e perché* la Rotta A fallisce davvero
  (firme di fallimento) → derivare le soglie dalla casistica osservata → validare la
  regola sull'intero documento (183 pagine, almeno via checksum). Non codificare
  intuizioni a priori: se A gestisce bene una pagina con 200 rect, non va instradata a B.
- **B2. Regola semplice e ispezionabile:** 2-3 soglie deterministiche sulle feature
  già calcolate in §2 (densità lines+rects, gutter ratio, larghezza righe, anomalie
  header/contenuto). NIENTE classificatori ML. Ogni decisione loggata nella trace di
  conversione: es. `p.73 → Rotta B (rects=270 > soglia 50)`.
- **B3. Anti-overfitting:** la regola è derivata da ~11 pagine → va validata su
  tutte le 183 prima di essere dichiarata; le soglie stanno in config, non nel codice.

## C. Deliverable aggiuntivo 2 — Escalation automatica (livello reattivo)

Il pre-routing gestisce le pagine difficili *previste*; l'escalation gestisce quelle
*impreviste*:

```
pagina → classificatore layout → Rotta A (default)
              │ (firma "difficile")        │
              └────────→ Rotta B (VLM)     ↓
                              ↑     checksum fallito?
                              └── escalation automatica a B
                                        ↓ fallisce ancora?
                                  coda revisione umana
```

Una pagina classificata "facile" il cui output non passa il checksum viene
rilavorata col VLM **automaticamente**, senza intervento umano. L'umano è solo
ultima istanza. Ogni escalation loggata (pagina, motivo, esito).

## D. Metriche di governance (nel ledger e nel report)

- % pagine per rotta · tasso di escalation · esiti escalation (risolte da B vs umano);
- il **tasso di escalation è il segnale di salute della regola**: se su un documento
  futuro sale, la regola va ritarata per quel tipo di documento — il sistema deve
  *dirlo*, non nasconderlo.

## E. Framing strategico (per il design, costa zero ora)

Classificazione layout + routing + escalation = **lo "step 0" standard di ingestion
per ogni futuro documento** (PF2, 730, IVA, CU…). Progettare di conseguenza:
- il comando CLI dell'analisi layout (già committato) come primo stadio riusabile;
- le soglie della regola come **config per tipo-documento**, non hardcode;
- nessuna assunzione PF1-specifica nei moduli di routing/escalation.
Questi deliverable non sono patch dello spike: sono la pipeline di ingestion del
layer operativo a regime.

## Aggiornamento del decision report (§5 della nota precedente)

Il report finale deve ora includere: confronto **per-classe** (A2), cella economica
modello-piccolo (A3), **regola di routing proposta con soglie e validazione full-doc**
(B), tasso di escalation stimato (C), costi dello spike dal ledger
(`spike:conversion-route`). Stop-point umano invariato: validazione del report prima
di convertire le restanti pagine.