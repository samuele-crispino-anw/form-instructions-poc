# Uso dell'indice del documento (p.2) rispetto ai requisiti — valutazione

**Scopo:** valutare se e come sfruttare l'indice del Fascicolo (pagina 2 del PF1) alla luce dei
requisiti già definiti (`PoC-Istruzioni_Requisiti_v1.md` + note strategiche), evidenziando cosa
cambierebbe rispetto all'approccio attuale e i pro/contro.
**Stato:** valutazione di design (nessuna implementazione). Decisione operativa rinviata alla
Fase 2 (router/serving), per non anticipare ottimizzazioni prima dell'evaluation.

---

## 1. Cosa fornisce l'indice di p.2

L'indice è l'elenco, scritto dal ministero, delle **sezioni/quadri del fascicolo con il relativo
intervallo di pagine** (es. "QUADRO RP — Oneri e spese ... pag. 54"). È una **fonte autorevole**
della struttura del documento: ~20 voci, compatte, con mappa **sezione → pagine**.

## 2. Dove si inserisce nei requisiti esistenti

| Requisito | Ruolo dell'indice |
|---|---|
| **FR-B4 (Router)** | I requisiti prevedono *esplicitamente* "classificatore LLM con in input **l'indice del fascicolo** + la domanda → top-1/2 sezioni". L'indice di p.2 **È** quel catalogo di ~20 sezioni. |
| **FR-B3 (markdown per quadro)** | Dà la mappa quadro→pagine per la **sezionatura** e per il campo `pagine: 54-78` del frontmatter. |
| **FR-D1 (ontologia)** | Fornisce la gerarchia di primo livello (modello → quadri/sezioni) su cui appendere righi/codici/vincoli. |
| **FR-T1 (tracciabilità) / FR-E2 (fedeltà citazioni)** | Permette un **cross-check**: la pagina citata in una risposta cade nella sezione attesa? |
| **FR-E1 (golden set)** | Aiuta a generare/etichettare le domande "procedurali/dove indicare" e a misurare l'accuratezza del router. |

**Conclusione del punto 2:** non è un'idea nuova rispetto ai requisiti — è un asset che i requisiti
*già presuppongono* (soprattutto FR-B4), ma che finora non avevamo materializzato.

## 3. Possibilità d'uso, cosa cambia e pro/contro

### Uso A — Catalogo del Router (FR-B4)
**Cosa cambia:** oggi il router non esiste ancora; quando lo costruiremo, l'indice diventa il
catalogo autorevole delle sezioni su cui classificare (al posto di un elenco ricavato a mano o
dagli heading `##`).
- **Pro:** catalogo autorevole e compatto (~20 voci, scala esatta che FR-B4 descrive); ancoraggio
  deterministico sezione→pagine; riusabile per ogni documento futuro.
- **Contro:** le etichette dell'indice sono in "lingua ministeriale", diverse dal lessico
  dell'utente ("farmacia", "ticket") → serve **comunque l'alias-table** (FR-B4) sopra l'indice;
  l'indice da solo non basta per il match colloquiale.

### Uso B — Sezionatura per-quadro e campo `pagine:` (FR-B3)
**Cosa cambia:** la sezionatura passerebbe da *derivata dagli heading* (`## QUADRO` nel markdown)
a *ancorata all'indice* (range pagine autorevoli), con gli heading come conferma.
- **Pro:** intervalli di pagina esatti dalla fonte; robusto se la rilevazione heading sbaglia o
  una pagina di continuazione non ha `##`; rende deterministico "quali pagine = quale quadro".
- **Contro:** i numeri di pagina dell'indice vanno **validati contro il contenuto** — possibili
  off-by-one, sotto-sezioni non elencate, e soprattutto **edizioni aggiornate infra-stagione**
  (trappola #6: il file è un "agg. 13/05/2026") in cui indice e contenuto potrebbero divergere.

### Uso C — Scheletro dell'ontologia (FR-D1)
**Cosa cambia:** l'indice fornisce la gerarchia modello→quadri come ossatura di partenza
dell'ontologia.
- **Pro:** struttura di primo livello pronta, niente da inferire.
- **Contro:** l'indice è **grossolano** (quadri/sezioni), non arriva a rigo/colonna/codice → il
  grosso del lavoro D1/D2 resta invariato; beneficio marginale.

### Uso D — Cross-check di citazioni e provenienza (FR-T1/FR-E2)
**Cosa cambia:** in fase di risposta, si può verificare che la pagina citata cada nella sezione
attesa dall'indice (un controllo in più sulla fedeltà delle citazioni).
- **Pro:** difesa aggiuntiva, coerente con la filosofia "due estrazioni indipendenti, divergenza →
  flag"; quasi gratis una volta che l'indice è strutturato.
- **Contro:** beneficio incrementale; non sostituisce i check esistenti.

## 4. Cosa cambierebbe a livello di pipeline (sintesi)

Introdurrebbe uno **"step 0-bis"**: estrazione dell'indice di p.2 in forma **strutturata**
(`sezione → range pagine`), come abbiamo fatto per l'identità in B.5 (structured output). Da lì:
- il **router** si ancora a un catalogo autorevole (FR-B4);
- la **sezionatura** diventa indice-driven con heading/layout come cross-check (FR-B3);
- nasce un **"indice macchina"** del documento, asset condiviso e generico per i documenti futuri.

Il punto chiave: l'indice **non sostituisce** gli approcci attuali (heading, layout-class,
alias-table), li **ancora a una fonte autorevole** e aggiunge un cross-check — la stessa logica a
doppia fonte che usiamo per il checksum.

## 5. Rischi / criticità

- **Indice ≠ verità assoluta:** infra-stagione può divergere dal contenuto (trappola #6); va
  trattato come *una* delle due fonti, non come oracolo. Mitigazione: cross-check indice vs heading
  → divergenza = flag.
- **Granularità:** copre quadri/sezioni, non righi → utilità piena per routing/sezionatura, scarsa
  per l'ontologia fine.
- **Lessico:** non risolve il match colloquiale → l'alias-table resta necessaria.
- **Rischio over-engineering:** costruirlo *prima* del router (che non esiste ancora) sarebbe
  ottimizzazione anticipata; va fatto quando serve davvero (Fase 2).

## 6. Raccomandazione

**Sfruttarlo, ma in Fase 2, come "step 0-bis" del router.** Concretamente:
1. estrarre p.2 in `sezione → {pagine, etichetta}` con structured output (riuso del pattern B.5),
   **validato per cross-check** contro gli heading `## QUADRO` del markdown (divergenze → flag);
2. usarlo per **(a)** ancorare il catalogo del router (FR-B4, sopra l'alias-table) e **(b)** guidare
   la sezionatura per-quadro e il campo `pagine:` del frontmatter (FR-B3);
3. tenerlo come **fonte di cross-check** per la fedeltà delle citazioni (FR-T1/E2).

**Non ora:** durante il run di conversione p.2 resta convertita come le altre pagine. L'estrazione
strutturata e l'aggancio al router si fanno quando arriveremo a FR-B4, mantenendo il principio
"prima l'evaluation, poi le ottimizzazioni". Soglie/etichette in config per tipo-documento.
