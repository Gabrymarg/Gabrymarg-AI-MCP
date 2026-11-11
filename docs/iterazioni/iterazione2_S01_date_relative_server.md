# Report scenari - modello `ollama:qwen2.5:3b`

Scenari superati: **0/1**. Token totali: 5836 input + 91 output = 5927 (media 5927 per scenario). Tempo totale: 201 s.

| ID | Scenario | Tipo | Esito | Tool invocati | Iter. | Token in | Token out | Tempo (s) |
|---|---|---|---|---|---|---|---|---|
| S01 | Prenotazione semplice | normale | NON SUPERATO | verifica_disponibilita | 2 | 5836 | 91 | 201.1 |

## S01 - Prenotazione semplice (NON SUPERATO)

**Richiesta:** "Buongiorno, vorrei prenotare un tavolo per 2 persone domani sera alle 20:30. Sono Marco Gallo, telefono 340 555 1234."

**Esito atteso:** Verifica la disponibilità, chiede conferma, registra la prenotazione per venerdì 2026-12-04 alle 20:30 e comunica il numero.

**Esito ottenuto:** "Mi dispiace, non c'è un tavolo libero per domani sera alle 20:30. Posso provarci alle 22:00 invece?"

Arresto: risposta_finale; conferme richieste: 0; scritture eseguite: nessuna.

**Controlli falliti:**
- tool atteso non invocato: crea_prenotazione
- database: atteso 1, trovato 0 (SELECT COUNT(*) FROM PRENOTAZIONI WHERE nome_cliente LIKE '%Gallo%' AND data='2026-12-04' AND ora='20:30' AND coperti=2)

Estratto del log (`log\S01_20261111-211704_90f09856.jsonl`):

```
[turno 1] utente: Buongiorno, vorrei prenotare un tavolo per 2 persone domani sera alle 20:30. Sono Marco Gallo, telefono 340 555 1234.
  it.1 modello (2848+50 token, 176468 ms) -> tool_calls: verifica_disponibilita({"data": "2026-12-05", "ora": "20:30", "coperti": 2})
  it.1 verifica_disponibilita -> ok {"data": "2026-12-05", "ora": "20:30", "coperti": 2, "disponibile": false, "turno": "cena", "sala": null, "orari_alternativi": ["22:00"]}
  it.2 modello (2988+41 token, 22045 ms) -> testo: "Mi dispiace, non c'è un tavolo libero per domani sera alle 20:30. Posso provarci alle 22:00 invece?"
  fine turno: risposta_finale (5927 token, 198574 ms)
```
