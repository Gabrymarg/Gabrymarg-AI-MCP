# Osteria del Borgo: agente AI con server MCP e harness agentico

Project Work, CdS Informatica per le Aziende Digitali (L-31), traccia PW 26:
*Integrazione di AI agent nel sistema informativo di un'impresa*.

Un assistente virtuale per un ristorante (fittizio) che, in linguaggio naturale:
- consulta il menu e gli allergeni;
- verifica la disponibilità dei tavoli, crea, modifica e cancella le prenotazioni;
- registra gli ordini da asporto controllando le scorte, e ne segue lo stato;
- aiuta il personale (sala, cucina, amministrazione) nelle operazioni di sua competenza.

Ogni utente opera con un **ruolo** (cliente, sala, cucina, amministratore) e il sistema gli consente solo le azioni previste. Il ciclo agentico è scritto da zero, senza framework agentici. Il modello linguistico può girare **in locale** (Ollama) oppure **in cloud** (Groq, piano gratuito), senza modifiche al codice.

## Architettura

```
 browser ──► web app (FastAPI) ──► harness agentico ──► LLMProvider ──► Ollama (locale) / Groq (cloud)
             login, ruoli,          ciclo, validazione,
             conferme, admin        conferme, log JSONL
                                         │  JSON-RPC su HTTP + token dell'utente
                                         ▼
                                    server MCP (17 tool, permessi per ruolo) ──► back-end ──► SQLite

 terminale ──► CLI ──► harness ══ stdio ══► server MCP   (modalità "ospite", senza login)
```

| Cartella | Contenuto |
|---|---|
| `backend/` | Schema SQL, servizi di dominio (prenotazioni, menu, ordini), utenti, token, permessi, seed |
| `mcp_server/` | Server MCP (SDK ufficiale `mcp` 2.x) con schemi Pydantic, annotazioni, autenticazione e permessi |
| `harness/` | Ciclo agentico (`agent.py`), astrazione dal modello (`llm/`), client MCP, conferme, logger, CLI |
| `webapp/` | Web app: back-end FastAPI, sessioni agentiche per utente, interfaccia HTML/CSS/JS |
| `scenarios/` | Scenari di test (`scenari.yaml`, `scenari_ruoli.yaml`) e runner |
| `tests/` | Test automatici (pytest) |
| `docs/` | Documentazione dei tool, diagrammi UML/ER, risultati delle batterie di test |

## Requisiti

- Python 3.11 o superiore (sviluppato con 3.12)
- [Ollama](https://ollama.com) con un modello che supporti il *tool calling*, oppure una chiave gratuita [Groq](https://console.groq.com)

## Installazione

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
python -m backend.seed            # crea data/risto.db con dati sintetici e utenti dimostrativi
ollama pull qwen2.5:3b            # modello locale
```

Per il modello in cloud: copiare `.env.example` in `.env` (escluso da git) e inserire la propria `GROQ_API_KEY`.

## Web app

```bash
python -m webapp
```

Poi aprire **http://127.0.0.1:8000**. La web app avvia automaticamente anche il server MCP in modalità HTTP, sulla porta 8765.

| Utente | Ruolo | Cosa può fare tramite l'assistente |
|---|---|---|
| `giulia`, `luca` | Cliente | Menu e allergeni, prenotare, gestire **solo le proprie** prenotazioni e ordini |
| `sala` | Personale di sala | Tutte le prenotazioni, quadro della serata, stato degli ordini |
| `cucina` | Cucina | Ordini da preparare e aggiornamento del loro stato, menu e allergeni |
| `admin` | Amministratore | Tutto, più magazzino, piatti nel menu e gestione di utenti e ruoli dal pannello web |

Le password degli utenti dimostrativi sono in `backend/seed.py` (`UTENTI_DEMO`): sono credenziali di prova, valide solo per il database locale.

L'interfaccia mostra, accanto alla chat, la **comanda dell'agente**: ogni passo del ciclo in tempo reale (richieste al modello, token, strumenti usati, esiti, conferme, controlli dell'harness). Le operazioni che modificano i dati compaiono come scheda con i pulsanti *Conferma* e *Annulla*.

Per demo coerenti con i dati del seed conviene fissare l'orologio: `set RISTO_ADESSO=2026-12-03T11:00` (Windows) prima di `python -m backend.seed` e `python -m webapp`.

### Sicurezza

- **Password** salvate solo come hash scrypt con salt; confronto a tempo costante; blocco temporaneo dopo 5 tentativi falliti.
- **Token di accesso** firmati HMAC-SHA256 con scadenza, in un cookie `HttpOnly` e `SameSite=Strict`. La chiave è in `RISTO_SECRET` oppure nel file `data/.secret` generato al primo avvio (escluso da git).
- **Permessi applicati dal server MCP** a ogni chiamata di tool, con il ruolo **riletto dal database**: un utente disattivato o declassato perde subito l'accesso, anche se il suo token non è ancora scaduto.
- **Difesa in profondità:**
  - l'harness presenta al modello solo i tool del ruolo;
  - il server verifica il permesso;
  - il back-end applica la proprietà dei dati (un cliente vede solo i propri);
  - ogni scrittura richiede la conferma dell'utente.

  Dichiarare in chat "sono l'amministratore" non cambia nulla: l'identità deriva solo dal token.
- **Interfaccia:** Content-Security-Policy restrittiva, nessun testo dell'agente o degli utenti inserito come HTML.

## Riga di comando (modalità ospite)

```bash
python -m harness.cli                                          # modello locale (Ollama)
python -m harness.cli --provider groq --modello openai/gpt-oss-120b
python -m harness.cli --verboso                                # mostra anche i risultati dei tool
```

Senza login l'utente è un **ospite**: può consultare il menu, prenotare e ordinare, e per modificare o cancellare deve indicare il telefono usato. Comandi in chat: `/nuova`, `/token`, `/esci`.

Il server MCP si può avviare anche da solo: `python -m mcp_server.server` (stdio) oppure `python -m mcp_server.server --http` (HTTP con autenticazione).

## Test

```bash
python -m pytest                                                               # 128 test, non serve un modello
python scenarios/run_scenarios.py --modello qwen2.5:3b                         # 16 scenari (ospite)
python scenarios/run_scenarios.py --file scenari_ruoli.yaml --provider groq --modello openai/gpt-oss-20b   # 8 scenari per ruolo
```

I test automatici comprendono test di integrazione che avviano il vero server MCP via HTTP e verificano token, permessi e proprietà dei dati.

Il runner crea per ogni scenario un database nuovo con l'orologio fissato al 2026-12-03 11:00, quindi i risultati sono riproducibili. Gli scenari con un `utente` vengono eseguiti come nella web app (server HTTP e token). I risultati ufficiali sono archiviati in `docs/iterazioni/`.

La documentazione dei tool (`docs/tools.md`) e i diagrammi (`docs/diagrammi/`) si rigenerano con `python docs/genera_doc_tool.py` e `python docs/diagrammi/genera_png.py`.

## Caratteristiche dell'harness

- **Ciclo agentico** con condizioni di arresto esplicite: risposta finale, numero massimo di iterazioni, chiamata ripetuta (loop), troppi errori consecutivi, errore o limite del modello.
- **Gestione degli errori:** tool inesistenti, argomenti non conformi al JSON Schema (validati *prima* di chiamare il server), errori di dominio, permessi negati, guasti e timeout. Ogni errore torna al modello come JSON strutturato.
- **Human-in-the-loop:** quali tool richiedono conferma lo decide l'annotazione MCP `readOnlyHint` dichiarata dal server; un tool senza annotazione viene trattato come scrittura. Il riepilogo mostra nomi dei piatti e giorno della settimana.
- **Controllo di coerenza:** se la risposta afferma un'operazione mai eseguita ("ho prenotato"), viene respinta e il modello riceve un avviso.
- **Gestione del contesto:** i risultati dei tool dei turni precedenti vengono accorciati prima di essere rinviati al modello, per contenere token e latenza e rispettare i limiti dei piani gratuiti.
- **Robustezza verso i modelli piccoli e i fornitori:** conversione dei tipi secondo lo schema, recupero e riparazione delle chiamate scritte come testo JSON, attese visibili per i limiti di frequenza, nessun tentativo inutile sui limiti giornalieri.
- **Lavoro deterministico nel back-end:** date in linguaggio naturale ("domani", "sabato", "24 dicembre") e piatti indicati per nome sono risolti dal sistema, non dal modello.
- **Log JSONL** di ogni passo (richieste e risposte del modello, tool, parametri, risultati, conferme, token, durate).
- **Indipendenza dal modello:** il ciclo usa solo l'interfaccia `LLMProvider` (Ollama, Groq, qualsiasi endpoint compatibile OpenAI, Mock per i test).

## Risultati

16 scenari principali (7 normali, 9 anomali), quattro iterazioni di miglioramento:

| Batteria | qwen2.5:3b (locale) | llama3.2 3B (locale) | gpt-oss-120b (Groq, cloud) |
|---|---|---|---|
| 1 - versione base | 10/16 | 9/16 | - |
| 2 - date e piatti risolti dal back-end | 14/16 | 10/16 | - |
| 3 - esempi astratti, recupero JSON | 13/16 | 7/16 | - |
| 4 - conversione tipi, riparazione JSON | 13/16 | - | **16/16** |

8 scenari per ruolo (clienti, sala, cucina, amministratore, tentativi di abuso): **8/8** con gpt-oss-20b (Groq), **5/8** con qwen2.5:3b. I 3 tentativi di abuso (cliente che si dichiara admin, cliente che cancella una prenotazione altrui, cucina che prenota) sono bloccati con entrambi i modelli, perché i permessi li applica il server, non il modello.

- **Nessuna scrittura senza conferma** in tutte le esecuzioni. Le chiamate con argomenti non validi sono state fermate dalla validazione prima del server.
- **Costi medi per scenario:** qwen in locale ~8.100 token e ~58 s; gpt-oss-120b su Groq ~6.500 token e ~15 s (circa 0,001 $ a listino).
- Report, log e confronti: `docs/iterazioni/`, `docs/confronto_batterie.md`, `docs/indicatori_sicurezza.py`.

## Dati

Tutti i dati sono sintetici: menu inventato, nomi e telefoni generati con Faker (`it_IT`, seed 42). Non sono usati dati personali reali né dati aziendali riservati.

## Uso di assistenti AI

Durante lo sviluppo è stato usato Claude Code (Anthropic) come assistente alla programmazione e alla stesura della documentazione. Le scelte progettuali, la revisione del codice e la verifica dei risultati sono dell'autore.
