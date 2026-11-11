# Report scenari - modello `ollama:qwen2.5:3b`

Scenari superati: **0/1**. Token totali: 5200 input + 95 output = 5295 (media 5295 per scenario). Tempo totale: 158 s.

| ID | Scenario | Tipo | Esito | Tool invocati | Iter. | Token in | Token out | Tempo (s) |
|---|---|---|---|---|---|---|---|---|
| S01 | Prenotazione semplice | normale | NON SUPERATO | verifica_disponibilita | 2 | 5200 | 95 | 157.7 |

## S01 - Prenotazione semplice (NON SUPERATO)

**Richiesta:** "Buongiorno, vorrei prenotare un tavolo per 2 persone domani sera alle 20:30. Sono Marco Gallo, telefono 340 555 1234."

**Esito atteso:** Verifica la disponibilità, chiede conferma, registra la prenotazione per venerdì 2026-12-04 alle 20:30 e comunica il numero.

**Esito ottenuto:** "Mi dispiace, non ci sono posti disponibili per quella prenotazione. Ci sono orari alternativi disponibili: 22:00. Potresti preferire uno di questi?"

Arresto: risposta_finale; conferme richieste: 0; scritture eseguite: nessuna.

**Controlli falliti:**
- tool atteso non invocato: crea_prenotazione
- database: atteso 1, trovato 0 (SELECT COUNT(*) FROM PRENOTAZIONI WHERE nome_cliente LIKE '%Gallo%' AND data='2026-12-04' AND ora='20:30' AND coperti=2)

Estratto del log (`log\S01_20261111-211135_3c6c3c37.jsonl`):

```
[turno 1] utente: Buongiorno, vorrei prenotare un tavolo per 2 persone domani sera alle 20:30. Sono Marco Gallo, telefono 340 555 1234.
  it.1 modello (2530+50 token, 139166 ms) -> tool_calls: verifica_disponibilita({"ora": "20:30", "coperti": 2, "data": "2026-12-05"})
  it.1 verifica_disponibilita -> ok {"data": "2026-12-05", "ora": "20:30", "coperti": 2, "disponibile": false, "turno": "cena", "sala": null, "orari_alternativi": ["22:00"]}
  it.2 modello (2670+45 token, 17273 ms) -> testo: 'Mi dispiace, non ci sono posti disponibili per quella prenotazione. Ci sono orari alternativi disponibili: 22:00. Potresti preferire uno di questi?'
  fine turno: risposta_finale (5295 token, 156482 ms)
```
