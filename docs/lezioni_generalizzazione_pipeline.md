# Lezioni per la generalizzazione — verso una pipeline multi-documento

**Scopo:** registro vivo delle correzioni e dei principi appresi processando il primo documento
(Redditi PF — Fascicolo 1, ed. 2026). Serve a chi, in futuro, generalizzerà questa PoC in una
pipeline che processa anche gli altri documenti dichiarativi (almeno della stessa famiglia:
Redditi PF Fascicolo 2/3, Redditi SC/SP/ENC, IRAP, IVA, 770, CU, ecc.).

**Come si usa:** ogni voce è una correzione concreta con il *principio generalizzabile* estratto.
Quando una scelta vale solo per PF1 va marcata come **specifica**; quando è strutturale va marcata
come **generale**. Aggiornare questo file ogni volta che emerge una nuova lezione rilevante per lo
scaling — non solo i bug, ma anche le assunzioni smentite dai dati.

> Regola di metodo trasversale: **non hardcodare nulla che sia specifico di PF1** nel codice
> (soglie, liste di parole, range di pagine). Tutto ciò che è documento-specifico vive nella
> configurazione; il codice resta documento-agnostico. Le decisioni vanno guidate dai dati, e le
> assunzioni vanno verificate prima di costruirci sopra.

---

## L1 — Gerarchia degli heading: semantica, non cieca sul numero di `#`

- **Contesto:** costruzione dell'albero di navigazione (D1) a partire dal markdown per-pagina.
- **Sintomo:** usando la profondità dei `#` come livello gerarchico, l'albero si spezzava: il
  titolo-documento ripetuto e i livelli `#` incoerenti tra pagine producevano nodi-radice falsi e
  righi staccati dalla loro sezione (caso "Rigo RP6" finito fuori dalla SEZIONE I).
- **Correzione:** la gerarchia si ricostruisce dai **marcatori strutturali reali** riconosciuti dal
  testo dell'heading (QUADRO / SEZIONE / Rigo / codice) e dal loro livello canonico, ignorando il
  numero di `#`. Builder deterministico, niente LLM (`serving/nodes.py`).
- **Principio (generale):** la profondità tipografica (`#`, indentazioni, font) prodotta da un LLM
  in conversione è **rumorosa e non affidabile come segnale gerarchico**. Va derivata la struttura
  dalla **semantica dei marcatori del dominio**. Per altri documenti i marcatori cambiano (es. SC
  ha quadri RF/RG/RS; IVA ha quadri VE/VF/VJ…): il set di pattern strutturali deve essere
  **configurabile per famiglia di modello**, non cablato su QUADRO/SEZIONE/Rigo.

### L1.a — Header di pagina ripetuti creano nodi fantasma
- **Sintomo:** il titolo del quadro ("QUADRO RP — Oneri e spese") è ripetuto come running-header su
  ogni pagina → 14 nodi-quadro invece di 1, albero spezzato a ogni pagina.
- **Correzione:** deduplica per **chiave canonica**: per il quadro la chiave è il codice (`RP`) →
  una sola occorrenza; le ripetizioni sono mobilio di pagina, non nodi.
- **Principio (generale):** i running-header/footer ripetuti vanno deduplicati per identità
  semantica, non per stringa esatta (il primo heading del quadro può differire dalle ripetizioni,
  es. "9. QUADRO RP – …" vs "QUADRO RP — …").

### L1.b — Prosa resa come heading "ruba" la struttura
- **Sintomo:** una frase introduttiva ("Sezione III A: righi da RP41 a RP47, nella quale vanno
  indicate:") era stata renderizzata come heading e, deduplicata, sottraeva la chiave alla sezione
  reale, facendola sparire dall'albero.
- **Correzione:** scartare come non-strutturali gli heading quadro/sezione che **terminano con
  `:`** (sono lead-in di prosa; i titoli reali non finiscono con due punti).
- **Principio (generale):** servono euristiche leggere per distinguere *titolo* da *prosa
  promossa a heading*. Da monitorare su altri documenti: potrebbero servire segnali aggiuntivi
  (lunghezza, presenza di verbi, posizione rispetto ai figli).

### L1.c — Pattern strutturali ancorati all'inizio
- **Sintomo:** un rigo ("Rigo RP49 … della sezione III A del Quadro RP") veniva classificato come
  quadro perché conteneva "Quadro RP" a metà frase.
- **Correzione:** ancorare i pattern di quadro/sezione/codice all'**inizio** dell'heading
  (ammettendo un numero d'ordine iniziale tipo "9."); i riferimenti incrociati in mezzo alla frase
  non devono attivarli.
- **Principio (generale):** i marcatori strutturali sono affidabili **in posizione iniziale**; le
  stesse parole in mezzo al testo sono riferimenti, non struttura.

---

## L2 — Verificare le assunzioni di layout sui dati, non a priori

- **Contesto:** routing della conversione (Rotta A text-layer vs Rotta B VLM).
- **Sintomo/scoperta:** l'assunzione "PF1 è a 2 colonne → serve il VLM" era **errata**: 0 pagine
  multi-colonna su 183. La Rotta A (estrazione testo + ricostruzione LLM) eguaglia il VLM su tutte
  le classi, incluse le `table_heavy`, senza rischio di allucinazione di trascrizione.
- **Principio (generale):** prima di scegliere la rotta costosa, **misurare il layout reale** del
  documento (metriche deterministiche: colonne, densità tabellare, presenza di text-layer). Il VLM
  va tenuto come **escalation reattiva**, non come default. Ogni nuovo documento può avere un mix
  di layout diverso: il routing deve restare data-driven e per-pagina.

---

## L3 — De-ifenazione: la sillabazione corrompe i controlli

- **Contesto:** gate checksum sulla conversione (parole critiche, overlap).
- **Sintomo:** falsi positivi "needs_human" (p.71, p.170): il soft-hyphen (`\xad`) della
  sillabazione spezzava parole ("esclusi-vamente", "non-ché") creando frammenti spuri che il gate
  leggeva come parole critiche perse.
- **Correzione:** de-ifenare il testo PDF prima dei controlli (`checks.dehyphenate`, rimozione di
  `\xad` + eventuale spazio/newline).
- **Principio (generale):** normalizzare gli artefatti tipografici del PDF (soft-hyphen,
  legature, spaziature anomale) **prima** di qualsiasi confronto testuale. Vale per qualunque PDF
  sillabato, non solo PF1.

---

## L4 — Rilevazione ripetizioni: diversità di riga, non n-grammi

- **Contesto:** controllo anti-loop sull'output del modello.
- **Sintomo:** il check a n-grammi segnalava come "ripetizione" tabelle legittime (p.073/117/181),
  perché le righe di tabella condividono molti n-grammi.
- **Correzione:** misurare la **diversità di riga** (rapporto righe uniche/totali, attivo da ≥12
  righe) invece del conteggio di n-grammi.
- **Principio (generale):** i documenti fiscali sono densi di tabelle ripetitive *legittime*: i
  controlli anti-degenerazione devono tollerare la ripetitività tabellare ed essere tarati su
  campioni noti-buoni prima di entrare in produzione.

---

## L5 — Densità numerica non separa i fallimenti del modello economico

- **Contesto:** ipotesi di pre-routing "pagine molto numeriche → modello forte".
- **Scoperta:** i dati la smentiscono (p.070 con 49 numeri = OK con Haiku; p.157 con 30 numeri =
  FAIL). La densità non discrimina i casi in cui il modello economico perde numeri.
- **Correzione:** ipotesi **abbandonata**; ci si affida al gate checksum reattivo + escalation.
- **Principio (generale):** non introdurre euristiche di pre-routing senza evidenza che separino
  davvero i casi. Meglio un **gate reattivo misurabile** che un pre-routing predittivo non
  validato. Le proposte vanno scartate onestamente quando i dati non le supportano.

---

## L6 — Non-determinismo del modello → idempotenza e ripresa

- **Contesto:** run di conversione a batch, anche con interruzioni.
- **Sintomi:** (a) stesso input → output diverso tra run; (b) batch parziali interrotti
  rischiavano di ri-addebitare token; (c) errori 529 (overloaded) intermittenti.
- **Correzioni:** persistenza per-pagina (md + riga `conversions`) → **ripresa dall'ultima pagina**;
  `skip_existing` per idempotenza; `try/except` per-pagina; `max_retries` sul client LLM.
- **Principio (generale):** una pipeline multi-documento (centinaia di pagine × molti documenti)
  **deve** essere idempotente, ripartibile e resiliente ai fallimenti transitori, con persistenza
  granulare. Mai assumere che un run vada a buon fine in un colpo solo.

---

## L7 — Costo: stimare prima di spendere, correggere onestamente

- **Contesto:** stima del costo del run completo.
- **Sintomo:** prima stima (~\$2.5–5) basata implicitamente su Haiku-first; il default scelto era
  Opus-first (~\$15–20). Stima corretta **prima** di lanciare.
- **Principio (generale):** ogni stima di costo deve esplicitare la configurazione modello su cui
  si basa; ledger token/€ sempre attivo (FR-T2). Su scala multi-documento gli errori di stima si
  moltiplicano: validare la stima su un mini-campione prima del run completo.

---

## Indice rapido dei principi generali (checklist per la pipeline futura)

1. Pattern strutturali del dominio **configurabili per famiglia** di documento (non hardcoded).
2. Gerarchia da **semantica dei marcatori**, non dal numero di `#`.
3. Deduplica running-header per **identità semantica**.
4. Routing di layout **data-driven e per-pagina**; rotta costosa solo in escalation.
5. **Normalizzare gli artefatti PDF** prima di ogni confronto testuale.
6. Controlli anti-degenerazione **tolleranti alle tabelle** e tarati su noti-buoni.
7. Nessun pre-routing predittivo senza evidenza di separazione.
8. **Idempotenza, ripresa, resilienza** ai transitori con persistenza granulare.
9. **Ledger costi** sempre attivo; stime esplicite sulla config e validate su campione.
