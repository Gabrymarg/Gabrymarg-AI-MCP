# Report scenari - modello `router:ollama:qwen2.5:3b|groq:openai/gpt-oss-20b`

Scenari superati: **2/2**. Token totali: 6848 input + 419 output = 7267 (media 3633 per scenario). Tempo totale: 4 s.

| ID | Scenario | Utente | Tipo | Esito | Tool invocati | Iter. | Token in | Token out | Tempo (s) |
|---|---|---|---|---|---|---|---|---|---|
| S09 | Richiesta ambigua | ospite | anomalo | SUPERATO | - | 1 | 3412 | 177 | 1.9 |
| S15 | Giorno di chiusura | ospite | anomalo | SUPERATO | - | 1 | 3436 | 242 | 2.1 |

## S09 - Richiesta ambigua (SUPERATO)

**Richiesta:** "Prenotate per domani."

**Esito atteso:** Non prenota; chiede i dati mancanti (numero di persone, orario, nome e telefono).

**Esito ottenuto:** "Per poterti confermare la prenotazione avrei bisogno di qualche dettaglio in più:

- A che ora vorresti arrivare (es. 19:30)?
- Quante persone saranno?
- Il tuo nome completo?
- Il tuo numero di telefono?

Grazie!"

Utente: ospite. Arresto: risposta_finale; conferme richieste: 0; scritture eseguite: nessuna.

Estratto del log (`log\S09_20261114-182435_fe01e3fc.jsonl`):

```
[turno 1] utente: Prenotate per domani.
  it.1 modello (3412+177 token, 627 ms) -> testo: 'Per poterti confermare la prenotazione avrei bisogno di qualche dettaglio in più:\n\n- A che ora vorresti arrivare (es. 19:30)?\n- Quante persone saranno?\n- Il tuo'
  fine turno: risposta_finale (3589 token, 630 ms)
```

## S15 - Giorno di chiusura (SUPERATO)

**Richiesta:** "Vorremmo venire lunedì a cena alle 20, in 3. Sono Anna Neri, 340 000 1111."

**Esito atteso:** Spiega che il lunedì il ristorante è chiuso e propone un altro giorno. Nessuna prenotazione.

**Esito ottenuto:** "Mi dispiace, ma il ristorante è chiuso il lunedì.  
Posso verificare la disponibilità per un’altra data (ad esempio martedì, mercoledì o giovedì) alle 20:00 per 3 persone.  
Vuoi provare a prenotare per un altro giorno?"

Utente: ospite. Arresto: risposta_finale; conferme richieste: 0; scritture eseguite: nessuna.

Estratto del log (`log\S15_20261114-182438_9daf0559.jsonl`):

```
[turno 1] utente: Vorremmo venire lunedì a cena alle 20, in 3. Sono Anna Neri, 340 000 1111.
  it.1 modello (3436+242 token, 845 ms) -> testo: 'Mi dispiace, ma il ristorante è chiuso il lunedì.  \nPosso verificare la disponibilità per un’altra data (ad esempio martedì, mercoledì o giovedì) alle 20:00 per'
  fine turno: risposta_finale (3678 token, 846 ms)
```
