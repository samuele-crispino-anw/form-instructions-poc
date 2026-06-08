# NOTA — Costruzione del layer di indicizzazione e retrieval gerarchico (sopra il markdown completato)

**Stato:** i 183 markdown del PF1 sono pronti. Questo è lo step successivo: costruire
sopra di essi un **albero di navigazione con riassunti scope-aware** + il **retrieval
ibrido**. Integra la spec PoC-Istruzioni (FR-B4 router, FR-D ontologia) — non la
sostituisce, la arricchisce.
**Disciplina di scope:** fare prima una **fetta verticale sul solo quadro RP** (il più
complesso), validarla sul golden set, POI generalizzare al resto. Non costruire tutto
prima di aver misurato.

## Principi guida (non derogabili)

1. **Scheletro dalla STRUTTURA, non da finestre arbitrarie.** L'albero dei nodi
   (quadro→sezione→rigo→codice) si deriva dagli heading/eId del markdown, in modo
   deterministico. NON ricostruire la gerarchia con passate LLM a 10 pagine: la
   struttura esiste già ed è esatta. L'LLM serve solo a *generare i riassunti per nodo*.
2. **I riassunti sono etichette di NAVIGAZIONE, non fatti.** I valori precisi (codici,
   percentuali, franchigie) restano nell'ontologia/DB strutturato (FR-D), con grounding.
   Il riassunto serve a *scegliere il ramo*, non a rispondere coi numeri.
3. **Governance = pinning con ambito = stessa informazione degli archi `governato_da`.**
   Una regola che governa più voci va espressa due volte, da un'unica fonte: come arco
   nel grafo (per la completezza) E come flag pinnato nel riassunto del nodo padre
   (per la navigazione).

## Deliverable

### D1 — Albero dei nodi (dalla struttura)
Da heading/eId del markdown → nodi quadro/sezione/rigo/codice, con pagine e ancore.

### D2 — Riassunto scope-aware per nodo (LLM, una passata per nodo)
Ogni nodo porta una scheda strutturata, NON prosa libera:
```
NODO: <id>  (pagine X-Y)
contenuto: cosa tratta, casi particolari inclusi (orientato a "cosa c'è dentro")
keywords: termini formali + colloquiali (riusa/estende gli alias)
⚑ regole_governanti (pin):
   - <regola> → ambito: <righi/sezione su cui vale>
istruzione_navigatore: per domande nell'ambito, includere SEMPRE i nodi pinnati,
   indipendentemente dal punteggio di rilevanza.
```
Il riassunto deve **evidenziare esplicitamente le regole iniziali/globali** (es.
franchigia, rateazione) col loro **ambito**, così quel ramo non viene mai potato per
domande in ambito → mitiga il "morte per riassunto".

### D3 — Indice keyword accanto ai riassunti (rete di salvataggio)
Mantenere l'indice keyword come layer parallelo: un match keyword può "salvare" un ramo
che il riassunto avesse sottovalutato. Non sostituisce i riassunti, li affianca.

### D4 — Retrieval ibrido a due velocità
- **Scorciatoia deterministica** (alias/keyword) per le domande comuni → salta la
  navigazione, va dritto al nodo.
- **Discesa navigazionale POCO PROFONDA** (1-2 hop, NON una chiamata LLM per livello;
  dare all'LLM un blocco di albero per volta) per le domande ambigue/complesse.
- **Contesto finale** = pagine-foglia rilevanti + **nodi governanti pinnati per ambito**
  + fatti strutturati dal DB. Obiettivo dimensione: ~5-8 pagine (vedi budget contesto),
  mai il quadro intero come default.
- **Guardia latenza:** discesa piatta + cache dell'albero. Loggare ogni hop.

## Tracciabilità ed eval (requisiti trasversali, invariati)

- **Answer trace** estesa: per ogni risposta, il percorso di navigazione (nodi visitati,
  perché scelti, nodi pinnati inclusi), oltre a citazioni e fatti DB.
- **Ledger:** ogni chiamata LLM (riassunti = `summary:build`; navigazione =
  `retrieval:nav`) con token/costo.
- **Eval di completezza (decisivo):** il golden set deve includere (a) domande la cui
  risposta corretta richiede una **regola governante sparsa** (es. i 20.000€ → rateazione;
  franchigia) — testano che il pinning funzioni e il ramo non venga potato; (b) domande
  con **stessa keyword in più sezioni** — testano la disambiguazione top-down. Se una di
  queste fallisce → riassunto/pin da correggere.

## Rischi da presidiare esplicitamente

1. **Potatura per riassunto incompleto** → mitigato da D2 (pin con ambito) + D3 (keyword
   rescue) + eval di completezza.
2. **Ambito parziale (il punto critico):** una regola che governa *alcuni* righi e non
   tutti (es. franchigia → solo spese sanitarie, non tutto RP). NON pinnare "per tutto il
   quadro" (sovra-inclusione). L'ambito del pin richiede giudizio di attribuzione →
   **spot-check umano sui tag di ambito**, non solo sui valori.
3. **Riassunti che invadono i fatti:** vietato far rispondere coi numeri dal riassunto;
   i numeri vengono dal DB con grounding.

## Done quando

- Albero + riassunti scope-aware per il quadro RP completi; lint strutturale verde.
- Retrieval ibrido funzionante su RP; ogni risposta con trace di navigazione + costi.
- Golden set RP (incl. casi completezza e disambiguazione) superato; report con
  accuratezza, completezza, latenza e costo medio/query.
- Stop-point umano: validazione dei tag di ambito (pin) prima di generalizzare agli
  altri quadri/modelli.