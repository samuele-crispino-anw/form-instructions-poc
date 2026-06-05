# Scoperte, evidenze e supporto alla decisione — strategia modello + escalation

**Scopo:** consolidare tutte le analisi svolte in risposta a `PoC-Nota_raffinamento_strategia.md`
e fornire gli elementi per decidere la **strategia modello/escalation** della pipeline di
conversione (C2).
**Stato:** completati A3, A4, B, C1 + spike completo (10/10). Restano C2 (orchestratore con
escalation), D (governance), e il run completo (dopo questa decisione).

---

## 1. TL;DR

1. L'assunzione "PF1 a 2 colonne" era **errata**: **0** pagine multi-colonna su 183.
2. La **Rotta A (text-layer + LLM, no vision)** eguaglia la Rotta B (VLM) **su tutte le classi**,
   incluse le `table_heavy` — e senza rischio di allucinazione di trascrizione.
3. La regola di routing predittiva instrada **183/183 pagine alla Rotta A** (0 al VLM): su PF1 il
   VLM non serve come pre-routing, solo come **escalation reattiva**.
4. **Haiku** sulla Rotta A costa **~7x meno** di Opus con qualità testuale identica, **ma perde
   qualche numero** (1 pagina su 3 nel mini-campione) → da solo non è sicuro, **lo è col gate
   checksum** che ri-lavora le pagine che calano.
5. **La decisione** è: quale modello di default per la Rotta A e come escalare. Il nodo è il
   **tasso di escalation reale** di Haiku, oggi stimato su soli 3 punti.

**Raccomandazione (dettagli in §6):** strategia **graduata** (Haiku→Opus→VLM→umano), **previa
misura del tasso di escalation di Haiku su ~15 pagine** per togliere l'incertezza. In alternativa,
se si preferisce prevedibilità assoluta, la strategia **sicura** (Opus) a ~$16 sul documento.

---

## 2. Scoperte con evidenze

### §2 — Analisi layout (tutte le 183 pagine, `data/.../layout_analysis.csv`)
| Classe | Pagine | % |
|---|---|---|
| single_column | 166 | 90,7% |
| multi_column | 0 | 0,0% |
| table_heavy | 16 | 8,7% |
| anomalous | 1 (p.1) | 0,5% |

Evidenze di validazione (non è un artefatto di soglia):
- single_column: mediana larghezza riga **0,79** (120/166 sopra 0,70), gutter_ratio mediano **1,86**
  (molte parole attraversano il centro = colonna piena);
- `table_heavy` p.73: **270** linee+rettangoli, righe cortissime (vere griglie tabellari);
- `anomalous` = solo p.1 (testo-fantasma "REDDITI SC 2023", 323 parole → non è vuota).

### §3 — Spike A vs B per-classe (10/10 pagine, stesso modello Opus 4.8)
| Classe | pag | overlap A | overlap B | numeri A | numeri B | $/pag A | $/pag B |
|---|---|---|---|---|---|---|---|
| single_column | 5 | 0,96 | 0,96 | 1,00 | 0,95 | 0,088 | 0,089 |
| table_heavy | 4 | 0,95 | 0,95 | 0,97 | 0,96 | 0,077 | 0,082 |
| anomalous | 1 | 1,00 | 0,99 | 1,00 | 1,00 | 0,038 | 0,050 |

Costo spike ~$1,65. Ispezione visiva p.73: **entrambe** ricostruiscono la tabella; la Rotta A
cattura anche l'intro delle sezioni. → **A non è inferiore a B su nessuna classe.**

### §3-bis (A3) — Rotta A: Opus vs Haiku (single_column), il dato economico
| pag | overlap Opus | overlap Haiku | numeri Opus | numeri Haiku | $ Opus | $ Haiku |
|---|---|---|---|---|---|---|
| 6 | 0,94 | 0,94 | 1,00 | **0,86** | 0,072 | 0,010 |
| 62 | 0,97 | 0,97 | 0,98 | 0,98 | 0,082 | 0,012 |
| 146 | 0,96 | 0,95 | 1,00 | **0,96** | 0,072 | 0,011 |

→ Haiku: **~7x più economico**, overlap identico, **cala sui numeri su 1 pagina su 3** (p.6: 0,86).

### A4 — pre-check font
Dimensione font **piatta** (~10pt ovunque) → l'indizio "size" è inerte. Il **grassetto** marca i
titoli ("Righi da RP1 a RP5") ma è usato anche per enfasi inline → indizio **rumoroso**. La
struttura la porta l'LLM combinando bold + pattern testuali ("QUADRO/Rigo"); lo spike conferma
heading corretti. Nessun pattern PF1 hardcoded.

### B — regola di routing (deterministica, da config)
Regola derivata dai fallimenti **misurati** (B1): default Rotta A; →VLM solo dove il text-layer è
inutile (pagine quasi-vuote). `table_heavy` **non** forzate a VLM (la Rotta A le gestisce).
**Risultato su PF1: 183/183 → Rotta A, 0 → VLM.** Soglie in `config/settings.toml [routing]`.

### C1 — checksum tarato (affidabilità del gate di escalation)
- Artefatti noti rimossi dal **riferimento** prima del confronto (la corretta omissione del
  testo-fantasma non conta più come "numero mancante" — risolve il falso positivo di p.1).
- Gerarchia heading e copertura **declassate a warning** non bloccanti (rumorose su questo corpus).
- Bloccanti (= innescano escalation): vuoto/rifiuto, overlap basso, **numeri mancanti**,
  ripetizione, artefatto presente nel markdown.

### Caveat metodologici (onestà sui limiti)
- `token-overlap` è **insensibile all'ordine** → da solo non prova la fedeltà d'ordine sulle
  tabelle; mitigato dall'ispezione visiva (p.73 ok).
- Il riferimento è il text-layer, quindi **favorisce A per costruzione**; che B (fonte indipendente)
  resti a 0,94-0,96 indica comunque buon accordo.
- Il "numero mancante" residuo può essere un **numero di pagina** del footer (non un codice):
  fonte di falsi positivi nel gate → da rifinire (vedi §6).
- La cella Haiku (A3) è su **3 pagine**: il tasso di escalation reale è ancora incerto.

---

## 3. La domanda di decisione
Quale **modello di default per la Rotta A** e quale **catena di escalation**? Il meccanismo di
escalation (C2) si costruisce comunque (è la rete di sicurezza generica per ogni documento); qui si
decide solo il **default in config**.

## 4. Le tre strategie a confronto
Proiezioni sul documento intero (183 pagine). Costo/pagina dalle misure reali dello spike/A3.

| Strategia | Default Rotta A | Escalation | Costo doc stimato | Escalation attesa | Rischio |
|---|---|---|---|---|---|
| **Graduata** | Haiku (~$0,011/pag) | Haiku→Opus-testo→VLM→umano | **~$3,5-7** (dipende dal tasso) | media/alta (si attiva) | basso *se* il gate è ben tarato |
| **Sicura** | Opus (~$0,087/pag) | →VLM solo se fallisce | **~$15-16** | quasi nulla | minimo (ma nessun risparmio, escalation non dimostrata) |
| **Ibrida-misurata** | Haiku, **dopo** misura su ~15 pagine | come graduata | $3,5-7 + ~$0,17 di misura | nota, non stimata | il più basso (decisione sui numeri) |

Dettaglio costi:
- **Sicura (Opus):** media pesata per classe = (166×0,088 + 16×0,077 + 1×0,038)/183 ≈ **$0,087/pag**
  → ~**$15,9** sul documento. Escalation ~0 (Opus-A non ha fallito in nessuna pagina dello spike).
- **Graduata (Haiku):** base ~$2,0 (183×$0,011). Ogni pagina escalata aggiunge ~$0,08 (Opus-testo).
  Con tasso di escalation E: costo ≈ $2,0 + E×183×$0,08. E=10%→~$3,5; E=20%→~$4,9; E=33%→~$6,8.
  Anche nel caso pessimistico resta **2-4x più economica** della Sicura.

## 5. Trade-off chiave
- **La promessa di risparmio di Haiku è reale (~7x) ma condizionata** al fatto che i cali numerici
  siano (a) pochi e (b) intercettati dal gate. Oggi abbiamo 1/3 di cali su 3 pagine: troppo poco per
  fidarsi del numero, abbastanza per sapere che il gate **deve** esserci.
- **La strategia Sicura non dimostra l'escalation** (Opus-A non fallisce → la rete di sicurezza non
  si attiva mai). L'escalation resta predisposta per documenti futuri, ma su PF1 non la "collaudiamo".
- **Il gate ha falsi positivi residui** (numeri di pagina) che, con Haiku, causerebbero escalation
  inutili (costo). Vanno tolti prima di affidarsi alla strategia graduata (§6).

## 6. Raccomandazione e dettagli operativi
**Raccomandazione: strategia Graduata, ma de-rischiata in due mosse a basso costo:**

1. **Rifinire il gate** (gratis): escludere dal confronto numeri i **numeri di pagina** del footer
   (la pagina N non deve contare "N" come numero di contenuto). Riduce i falsi positivi → meno
   escalation inutili. *(modifica a `run_checks`/caller, niente chiamate)*
2. **Misurare il tasso di escalation di Haiku su ~15 pagine single_column** (~$0,17): otteniamo E
   reale e quindi il costo atteso del documento, prima di lanciare il run completo.

Poi, in base a E:
- **E basso (<~15%)** → Graduata con Haiku: massimo risparmio (~$3,5-4), gate a fare da rete.
- **E alto (>~30%)** → conviene la Sicura (Opus): le troppe ri-lavorazioni eroderebbero il risparmio
  e aggiungerebbero latenza; meglio pagare Opus una volta sola.

**Cosa cambia in pratica per ciascuna scelta (solo config):**
- Modelli Rotta A/B in `[models]` (`route_a`, `route_b`).
- Catena di escalation in `[routing]`/`[escalation]` (soglie del gate, ordine dei modelli).
- Il codice dell'orchestratore (C2) è lo stesso: cambia solo la config.

**Se vuoi evitare le due mosse** e avere subito prevedibilità: scegli la **Sicura** (Opus, ~$16,
correttezza massima) e teniamo Haiku come ottimizzazione futura quando avremo più dati.

---

## 7. Riepilogo costi sostenuti finora (dal ledger, FR-T2)
**Totale: $1,99 (€1,73), 29 chiamate.**
- VLM `conversion:*` (calibrazione 3 pagine con re-run + lato B dello spike + retry p.4): **~$1,17**
- Rotta A testo `spike:routeA` (10 spike + 3 Haiku A3 = 13 chiamate): **~$0,82**
- smoke: trascurabile.

Nota: i re-run pre-fix di p.1 (4 chiamate, ~$0,20) e p.75/p.180 (2 ciascuna) pesano sul lato VLM;
col fix di idempotenza non si ripeterebbero.
