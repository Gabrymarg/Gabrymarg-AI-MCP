# Osteria del Borgo: agente AI con server MCP e harness agentico

Project Work, CdS Informatica per le Aziende Digitali (L-31), traccia PW 26:
*Integrazione di AI agent nel sistema informativo di un'impresa*.

Un assistente virtuale per un ristorante (fittizio) che, in linguaggio naturale:
- consulta il menu e gli allergeni;
- verifica la disponibilità dei tavoli, crea, modifica e cancella le prenotazioni;
- registra gli ordini da asporto controllando le scorte;
- comunica lo stato di un ordine.

Il modello linguistico gira **in locale** con Ollama. Il ciclo agentico è scritto da zero, senza framework agentici.

## Architettura

```
 utente ──► harness (CLI) ──► LLMProvider ──► Ollama (qwen2.5:3b / llama3.2)
              │  ciclo agentico, validazione, conferme, log JSONL
              ▼
          client MCP ══ stdio ══► server MCP (10 tool) ──► back-end ──► SQLite
```

| Cartella | Contenuto |
|---|---|
| `backend/` | Schema SQL, servizi di dominio (prenotazioni, menu, ordini), seed con dati sintetici |
| `mcp_server/` | Server MCP (SDK ufficiale `mcp` 2.x, `MCPServer`) con schemi Pydantic e annotazioni |
| `harness/` | Ciclo agentico (`agent.py`), astrazione dal modello (`llm/`), client MCP, conferme, logger, CLI |
| `scenarios/` | 16 scenari di test (`scenari.yaml`), runner e risultati |
| `tests/` | Test automatici (pytest): back-end e ciclo agentico con modello fittizio |
| `docs/` | Documentazione dei tool, diagrammi UML/ER |

## Requisiti

- Python 3.11 o superiore (sviluppato con 3.12)
- [Ollama](https://ollama.com) con un modello che supporti il *tool calling*

## Installazione

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
ollama pull qwen2.5:3b
python -m backend.seed            # crea data/risto.db con dati sintetici
```

## Esecuzione

```bash
python -m harness.cli                         # chat nel terminale
python -m harness.cli --modello llama3.2      # stesso codice, altro modello
python -m harness.cli --verboso               # mostra anche i risultati dei tool
```

**Modello in cloud (Groq, piano gratuito).** Copiare `.env.example` in `.env` (escluso da git), inserire la propria `GROQ_API_KEY` e poi:

```bash
python -m harness.cli --provider groq --modello openai/gpt-oss-120b
```

Comandi in chat: `/nuova` (nuova conversazione), `/token` (token consumati), `/esci`.
Prima di ogni operazione che modifica i dati l'assistente mostra un riepilogo e chiede `Confermi? [s/N]`.

Il server MCP si può ispezionare anche da solo, ad esempio con MCP Inspector:
`npx @modelcontextprotocol/inspector .venv\Scripts\python -m mcp_server.server`.

### Test

```bash
python -m pytest                                        # 98 test, non serve Ollama
python scenarios/run_scenarios.py --modello qwen2.5:3b  # 16 scenari con il modello reale
```

Il runner crea per ogni scenario un database nuovo con l'orologio fissato al 2026-12-03 11:00, così i risultati sono riproducibili. Scrive `report.md`, `risultati.json` e i log JSONL in `scenarios/risultati/<modello>/` (non versionata). I risultati ufficiali delle quattro batterie sono archiviati in `docs/iterazioni/`.

I diagrammi UML ed ER sono in `docs/diagrammi/` (sorgenti PlantUML e PNG; `python docs/diagrammi/genera_png.py` li rigenera).

## Configurazione (variabili d'ambiente)

| Variabile | Predefinito | Significato |
|---|---|---|
| `RISTO_LLM_PROVIDER` | `ollama` | `ollama` (API nativa), `groq` (cloud) oppure `openai` (qualsiasi endpoint compatibile) |
| `GROQ_API_KEY` | - | Chiave Groq, da mettere nel file `.env` |
| `RISTO_MODELLO` | `qwen2.5:3b` | Nome del modello |
| `RISTO_OPENAI_BASE_URL` / `RISTO_OPENAI_API_KEY` | `http://localhost:11434/v1` | Solo per il provider `openai` |
| `RISTO_MAX_ITERAZIONI` | `8` | Iterazioni massime del ciclo per ogni messaggio |
| `RISTO_MAX_ERRORI` | `3` | Errori consecutivi dei tool prima dell'arresto |
| `RISTO_TIMEOUT_TOOL` | `15` | Timeout di una chiamata a un tool (secondi) |
| `RISTO_LOG_DIR` | `logs/` | Cartella dei log JSONL |
| `RISTO_DB` | `data/risto.db` | Database SQLite |
| `RISTO_ADESSO` | ora di sistema | Fissa l'orologio (es. `2026-12-03T11:00`), per demo e test |
| `RISTO_GUASTI` | *(vuoto)* | Tool che falliscono di proposito, per simulare guasti nei test |
| `RISTO_GUARDRAIL` | `1` | `0` disattiva il controllo di coerenza (utile per confronti) |

## Caratteristiche dell'harness

- **Ciclo agentico** con condizioni di arresto esplicite: risposta finale, numero massimo di iterazioni, chiamata ripetuta (loop), troppi errori consecutivi, errore del modello.
- **Gestione degli errori:** tool inesistenti, argomenti non conformi al JSON Schema (validati *prima* di chiamare il server), errori di dominio, guasti e timeout. Ogni errore torna al modello come JSON strutturato, così il modello può correggersi.
- **Human-in-the-loop:** quali tool richiedono conferma non è scritto nel codice dell'harness. Lo decide l'annotazione MCP `readOnlyHint` dichiarata dal server; un tool senza annotazione viene trattato come scrittura.
- **Controllo di coerenza:** se la risposta finale afferma un'operazione (es. "ho prenotato") ma nel turno nessun tool di scrittura è andato a buon fine, l'harness non la consegna e rimanda il modello indietro con un avviso, una volta per turno. Si disattiva con `RISTO_GUARDRAIL=0`.
- **Piatti indicati per nome:** il back-end risolve il nome ("2 carbonare", "il tiramisù") nel piatto corretto, quindi il modello non deve indovinare gli id. Nella prima batteria di test questo era la causa di risposte errate sugli allergeni.
- **Date in linguaggio naturale:** "domani", "sabato", "24 dicembre" e "12/12" vengono convertite dal back-end, non dal modello.
- **Schemi compatti per il modello:** gli schemi inviati al LLM sono semplificati (−28% di caratteri); la validazione usa lo schema completo del server.
- **Log JSONL:** registra ogni passo (richieste e risposte del modello, tool, parametri, risultati, conferme, token, durate).
- **Indipendenza dal modello:** il ciclo usa solo l'interfaccia `LLMProvider`. Ci sono un provider Ollama nativo, uno per endpoint compatibili OpenAI e un `MockProvider` per i test.

## Risultati

16 scenari (7 normali, 9 anomali), quattro iterazioni di miglioramento:

| Batteria | qwen2.5:3b (locale) | llama3.2 3B (locale) | gpt-oss-120b (Groq, cloud) |
|---|---|---|---|
| 1 - versione base | 10/16 | 9/16 | - |
| 2 - date e piatti risolti dal back-end | 14/16 | 10/16 | - |
| 3 - esempi astratti, recupero JSON | 13/16 | 7/16 | - |
| 4 - conversione tipi, riparazione JSON | 13/16 | - | **16/16** |

- **Nessuna scrittura senza conferma del cliente** in 128 conversazioni. Le 28 chiamate con argomenti non validi sono state fermate dalla validazione prima del server.
- **Costi medi per scenario:** qwen in locale ~8.100 token e ~58 s; gpt-oss-120b su Groq ~6.500 token e ~15 s (circa 0,001 $ a listino).
- Report, log JSONL e confronti: `docs/iterazioni/`, `docs/confronto_batterie.md`, `docs/indicatori_sicurezza.py`.

## Dati

Tutti i dati sono sintetici: menu inventato, nomi e telefoni generati con Faker (`it_IT`, seed 42). Non sono usati dati personali reali né dati aziendali riservati.

## Uso di assistenti AI

Durante lo sviluppo è stato usato Claude Code (Anthropic) come assistente alla programmazione e alla stesura della documentazione. Le scelte progettuali, la revisione del codice e la verifica dei risultati sono dell'autore.
