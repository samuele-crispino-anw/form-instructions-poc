# Nota integrativa ai Requisiti PoC ISTRUZIONI — Esiti ricognizione stato dell'arte (giugno 2026\)

**Da leggere insieme a:** `PoC-Istruzioni_Requisiti_v1.md` (che resta il documento **autoritativo**: gli aggiornamenti di questa nota sono già recepiti in FR-D2 e §10). **Scopo di questa nota:** dare all'implementatore il **razionale, gli esempi e i dettagli attuativi** dietro quegli aggiornamenti, frutto di una ricognizione mirata sullo stato dell'arte (3 quesiti, fonti secondarie — le cifre citate sono indicative e non verificate sui paper originali: usarle come calibrazione, non come verità).

---

## 1\. Esito ricognizione: parsing PDF→Markdown (conferma FR-B2 \+ 2 contingenze)

**Quadro emerso:** consenso 2025-26 che i **vision LLM hanno il miglior reading order su layout multi-colonna e gerarchia liste**; LlamaParse eccelle sulle **tabelle complesse**; Docling è la migliore opzione locale/open.

**Cosa significa per l'implementazione:**

- La scelta VLM page-as-image (FR-B1/B2) è confermata: nessun cambio.  
- **Contingenza tabelle (trigger preciso):** il PF1 ha pochissime tabelle delineate (rilevata \~1 nel campione analizzato). SE in Fase 1 una pagina con tabella vera risulta trascritta male dal VLM (verifica nello spot-check) → passata dedicata **solo su quelle pagine** con LlamaParse o Docling, e merge nel markdown. Non costruire nulla in anticipo: è una riparazione puntuale.  
- **Docling come "terzo testimone" (opzionale):** sulle pagine flaggate `needs_review` dal checksum VLM-vs-layer-PDF, una terza estrazione locale (Docling) permette una logica 2-su-3 che riduce il carico di revisione umana. Mezz'ora di integrazione, a discrezione: se le pagine flaggate sono \<10, non ne vale la pena — meglio l'occhio umano.

## 2\. Esito ricognizione: nessun benchmark di QA fiscale italiano esiste

**Quadro emerso:** esistono risorse legali italiane generiche (JuriFindIT per statutory retrieval, ITALIAN-LEGAL-BERT come encoder di dominio), ma **nessun dataset/benchmark pubblico su QA fiscale o documenti dell'Agenzia delle Entrate**.

**Cosa significa per l'implementazione:**

- Il **golden set (FR-E1) è per necessità in-house** e va trattato come **asset proprietario**: versionato in git, con provenance per ogni caso (chi l'ha scritto/validato, quando, su quale edizione del documento), pensato per crescere oltre la PoC. Non è un file di test usa-e-getta: è uno dei deliverable di maggior valore.  
- Il pattern "**domande sintetiche generate sopra domande esperte**" (usato per alias e retrieval, FR-D2) ha un precedente accademico su larga scala nel legale italiano (JuriFindIT: \~169k sintetiche sopra \~895 esperte — *riferimento da verificare prima di citarlo esternamente*). Procedere con fiducia sul pattern; marcare sempre le sintetiche come `synthetic` per non inquinare le metriche.

## 3\. Esito ricognizione (il più importante): JSON valido ≠ valori corretti

**Quadro emerso:** i benchmark 2026 sull'estrazione strutturata mostrano modelli frontier con **validità JSON quasi perfetta ma accuratezza dei valori-foglia \~83% nel caso migliore** (testo). Tradotto: **\~10-17% dei valori può essere sbagliato dentro record formalmente impeccabili.**

### 3.1 L'esempio che l'implementatore deve tenere a mente

```json
{"rigo": "RP1", "codice": 1,
 "vincoli": {"franchigia_eur": 192.11},     ← il testo dice 129,11: cifre trasposte
 "fonte": {"sezione": "RP", "pagina": 54}}
```

Schema: ✓ valido. Tipi: ✓ giusti. Valore: ✗ **falso**. La validazione di schema non può accorgersene. Su un quadro con centinaia di valori-foglia, senza contromisure \= decine di numeri sbagliati invisibili.

### 3.2 La contromisura: validazione a tre livelli (dettaglio attuativo di FR-D2)

1. **Sintattica** — parse, schema, tipi. (Prende: campo mancante, tipo errato.)  
2. **Semantica** — regole di dominio: range plausibili (franchigia ≥ 0, percentuali ≤ 100), codici univoci per rigo, pagine esistenti nel documento, coerenza cross-campo.  
3. **Source-grounding** *(la più importante)* — per **ogni valore-foglia** (codici, importi, percentuali): verifica **deterministica, senza LLM**, che il valore compaia letteralmente nel testo della sezione markdown citata come fonte.

**Algoritmo di grounding (sketch):**

```
per ogni leaf (campo numerico/codice) del record:
    varianti = normalizza(valore)        # 129.11 → {"129,11","129.11","€129,11","euro 129,11"}
    sezione  = carica_md(record.fonte.sezione)
    if nessuna variante in sezione → flag(record, campo, "not_grounded")
```

Normalizzazioni minime richieste: virgola/punto decimale, simbolo €/"euro", separatori delle migliaia, percentuali ("19%", "19 per cento").

**Caveat dei valori derivati:** un valore legittimamente *trasformato* (es. importo storico in lire canonicalizzato in euro) non matcherà mai → finisce **flaggato in coda umana**, non viene né accettato né scartato in automatico. Principio: *nessun valore non verificabile ha un percorso silenzioso verso il DB*.

### 3.3 Repair loop per-campo (dettaglio attuativo)

Su grounding/validazione fallita di un campo, **non rigenerare il record intero** (costa di più e i campi giusti potrebbero cambiare). Prompt di riparazione chirurgico:

```
Nel testo seguente [sezione RP], qual è esattamente la franchigia per le
spese sanitarie del rigo RP1? Rispondi SOLO con il numero, esattamente
come appare nel testo.
```

→ rivalida solo quel campo. **Max 2 tentativi**, poi coda umana. Ogni riparazione loggata (campo, tentativi, esito) nel ledger.

### 3.4 Metriche di compilazione da aggiungere al report (integrano FR-E/FR-T2)

La compilazione (FR-D2) deve produrre, oltre al DB, queste metriche:

- `% leaf groundati al primo colpo` · `% riparati (1°/2° tentativo)` · `% in coda umana` — per tipo di campo (importi vs codici vs percentuali);  
- esito dello spot-check umano **incrociato col grounding** (lo spot-check verifica anche che il validatore stia funzionando: se l'umano trova un errore che il grounding non ha flaggato → bug del validatore, priorità massima);  
- costo di compilazione totale dal ledger (già previsto da FR-T2).

### 3.5 La catena di fiducia completa (il quadro per chi implementa)

| Anello | Verifica | Riferimento |
| :---- | :---- | :---- |
| PDF → Markdown | trascrizione VLM vs layer testuale PDF (checksum) | FR-B2 |
| Markdown → DB | **source-grounding** di ogni valore-foglia | FR-D2 (questa nota §3.2) |
| DB → Risposta | ogni numero in risposta deve coincidere con un risultato di `lookup` | FR-D4 |

Proprietà finale del sistema: **un numero sbagliato non ha un percorso silenzioso per arrivare all'utente** — se un anello fallisce, il valore viene flaggato, mai servito. È il requisito che rende il sistema proponibile a professionisti con responsabilità legale.

---

## 4\. Checklist attuativa (riassunto operativo per l'implementazione)

- [ ] Normalizzatore numerico **condiviso** tra grounding (FR-D2) e verifica risposte (FR-D4) — stessa funzione, un solo posto.  
- [ ] Modulo `grounding_validator` con report per-campo; tabella `flags` nel DB.  
- [ ] Template dei repair prompt versionati; logging riparazioni nel ledger.  
- [ ] Metriche di compilazione (§3.4) nel report finale.  
- [ ] Trigger contingenza tabelle documentato in Fase 1 (quali pagine, quale esito VLM).  
- [ ] Golden set con provenance per caso; sintetiche marcate `synthetic`.  
- [ ] (Opzionale) Docling come terzo testimone se pagine flaggate \>10.

