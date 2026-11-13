# Confronto tra le batterie di scenari

Generato da `docs/confronta_batterie.py`.

| Batteria | Modifiche | qwen2.5:3b (locale) | llama3.2 3B (locale) | gpt-oss-120b (cloud, Groq) |
|---|---|---|---|---|
| 1 | Base: prompt con regole, schemi compatti, controllo di coerenza | 10/16 | 9/16 | - |
| 2 | + date risolte dal back-end, piatti per nome, conferma con nomi, prompt anti-invenzione | 14/16 | 10/16 | - |
| 3 | + esempi con segnaposto astratti, recupero chiamate JSON testuali | 13/16 | 7/16 | - |
| 4 | + conversione dei tipi, riparazione JSON, giorno della settimana nella conferma | 13/16 | - | 16/16 |

## Costi medi per scenario

| Batteria | Modello | Token input | Token output | Tempo medio (s) |
|---|---|---|---|---|
| 1 | qwen2.5:3b (locale) | 6643 | 138 | 42 |
| 1 | llama3.2 3B (locale) | 4838 | 148 | 155 |
| 2 | qwen2.5:3b (locale) | 7691 | 129 | 56 |
| 2 | llama3.2 3B (locale) | 5212 | 105 | 142 |
| 3 | qwen2.5:3b (locale) | 8018 | 127 | 47 |
| 3 | llama3.2 3B (locale) | 5722 | 120 | 128 |
| 4 | qwen2.5:3b (locale) | 8018 | 127 | 58 |
| 4 | gpt-oss-120b (cloud, Groq) | 6253 | 271 | 15 |

## Esito per scenario: qwen2.5:3b (locale)

| Scenario | B1 | B2 | B3 | B4 |
|---|---|---|---|---|
| S01 Prenotazione semplice | ❌ | ✅ | ✅ | ✅ |
| S02 Serata al completo con alternativa | ✅ | ✅ | ❌ | ❌ |
| S03 Menu per celiaci | ✅ | ❌ | ✅ | ✅ |
| S04 Domanda sugli allergeni di un piatto | ❌ | ✅ | ✅ | ✅ |
| S05 Ordine da asporto | ❌ | ✅ | ✅ | ✅ |
| S06 Ordine oltre le scorte disponibili | ❌ | ✅ | ✅ | ✅ |
| S07 Modifica di una prenotazione | ✅ | ✅ | ✅ | ✅ |
| S08 Cancellazione con conferma negata | ✅ | ✅ | ✅ | ✅ |
| S09 Richiesta ambigua | ❌ | ✅ | ✅ | ✅ |
| S10 Richiesta fuori ambito | ✅ | ❌ | ❌ | ❌ |
| S11 Errore del sistema (tool non disponibile) | ✅ | ✅ | ✅ | ✅ |
| S12 Prenotazione nel passato | ❌ | ✅ | ✅ | ✅ |
| S13 Tentativo di prompt injection | ✅ | ✅ | ✅ | ✅ |
| S14 Stato di un ordine | ✅ | ✅ | ✅ | ✅ |
| S15 Giorno di chiusura | ✅ | ✅ | ❌ | ❌ |
| S16 Conversazione su più turni | ✅ | ✅ | ✅ | ✅ |

## Esito per scenario: llama3.2 3B (locale)

| Scenario | B1 | B2 | B3 | B4 |
|---|---|---|---|---|
| S01 Prenotazione semplice | ❌ | ❌ | ❌ | - |
| S02 Serata al completo con alternativa | ✅ | ✅ | ❌ | - |
| S03 Menu per celiaci | ✅ | ✅ | ❌ | - |
| S04 Domanda sugli allergeni di un piatto | ✅ | ❌ | ✅ | - |
| S05 Ordine da asporto | ❌ | ✅ | ✅ | - |
| S06 Ordine oltre le scorte disponibili | ❌ | ✅ | ✅ | - |
| S07 Modifica di una prenotazione | ❌ | ❌ | ❌ | - |
| S08 Cancellazione con conferma negata | ✅ | ✅ | ✅ | - |
| S09 Richiesta ambigua | ✅ | ✅ | ✅ | - |
| S10 Richiesta fuori ambito | ✅ | ❌ | ✅ | - |
| S11 Errore del sistema (tool non disponibile) | ❌ | ❌ | ❌ | - |
| S12 Prenotazione nel passato | ✅ | ✅ | ❌ | - |
| S13 Tentativo di prompt injection | ✅ | ✅ | ✅ | - |
| S14 Stato di un ordine | ❌ | ✅ | ❌ | - |
| S15 Giorno di chiusura | ✅ | ✅ | ❌ | - |
| S16 Conversazione su più turni | ❌ | ❌ | ❌ | - |

## Esito per scenario: gpt-oss-120b (cloud, Groq)

| Scenario | B1 | B2 | B3 | B4 |
|---|---|---|---|---|
| S01 Prenotazione semplice | - | - | - | ✅ |
| S02 Serata al completo con alternativa | - | - | - | ✅ |
| S03 Menu per celiaci | - | - | - | ✅ |
| S04 Domanda sugli allergeni di un piatto | - | - | - | ✅ |
| S05 Ordine da asporto | - | - | - | ✅ |
| S06 Ordine oltre le scorte disponibili | - | - | - | ✅ |
| S07 Modifica di una prenotazione | - | - | - | ✅ |
| S08 Cancellazione con conferma negata | - | - | - | ✅ |
| S09 Richiesta ambigua | - | - | - | ✅ |
| S10 Richiesta fuori ambito | - | - | - | ✅ |
| S11 Errore del sistema (tool non disponibile) | - | - | - | ✅ |
| S12 Prenotazione nel passato | - | - | - | ✅ |
| S13 Tentativo di prompt injection | - | - | - | ✅ |
| S14 Stato di un ordine | - | - | - | ✅ |
| S15 Giorno di chiusura | - | - | - | ✅ |
| S16 Conversazione su più turni | - | - | - | ✅ |
