# Report scenari - modello `groq:openai/gpt-oss-20b`

Scenari superati: **1/1**. Token totali: 7892 input + 271 output = 8163 (media 8163 per scenario). Tempo totale: 2 s.

| ID | Scenario | Utente | Tipo | Esito | Tool invocati | Iter. | Token in | Token out | Tempo (s) |
|---|---|---|---|---|---|---|---|---|---|
| R01 | Il cliente vede le proprie prenotazioni | giulia | normale | SUPERATO | trova_prenotazioni | 2 | 7892 | 271 | 2.1 |

## R01 - Il cliente vede le proprie prenotazioni (SUPERATO)

**Richiesta:** "Quali prenotazioni ho?"

**Esito atteso:** Elenca solo la prenotazione di Giulia (n. 86, venerdì 11 dicembre alle 20:30), senza chiedere nome o telefono.

**Esito ottenuto:** "Ecco la tua prenotazione attiva:

- **Data**: 2026‑12‑11  
- **Ora**: 20:30  
- **Coperti**: 2  
- **Note**: Anniversario  
- **Tavolo**: T1 (Sala interna)

Se hai bisogno di modificare o cancellare questa prenotazione, fammi sapere!"

Utente: giulia. Arresto: risposta_finale; conferme richieste: 0; scritture eseguite: nessuna.

Estratto del log (`log\R01_20261115-110656_a8095ee3.jsonl`):

```
[turno 1] utente: Quali prenotazioni ho?
  it.1 modello (3866+125 token, 387 ms) -> tool_calls: trova_prenotazioni({"data": null, "nome": null, "telefono": null})
  it.1 trova_prenotazioni -> ok {"numero_risultati": 1, "prenotazioni": [{"id_prenotazione": 86, "data": "2026-12-11", "ora": "20:30", "coperti": 2, "nome_cliente": "Giulia Ferri", "telefono":
  it.2 modello (4026+146 token, 361 ms) -> testo: 'Ecco la tua prenotazione attiva:\n\n- **Data**: 2026‑12‑11  \n- **Ora**: 20:30  \n- **Coperti**: 2  \n- **Note**: Anniversario  \n- **Tavolo**: T1 (Sala interna)\n\nSe '
  fine turno: risposta_finale (8163 token, 763 ms)
```
