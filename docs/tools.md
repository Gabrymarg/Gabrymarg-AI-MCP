# Documentazione dei tool MCP

Generata automaticamente da `docs/genera_doc_tool.py` interrogando il server (`tools/list`).
Gli esempi sono stati eseguiti realmente via HTTP, come amministratore, su un database di prova (seed 42, orologio fissato a 2026-12-03T11:00). I ruoli autorizzati provengono da `backend/permessi.py` e sono verificati dal server a ogni chiamata.

| Tool | Effetti | Ruoli autorizzati | Parametri obbligatori |
|---|---|---|---|
| `mio_profilo` | lettura | ospite, cliente, sala, cucina, admin | - |
| `orari_apertura` | lettura | ospite, cliente, sala, cucina, admin | - |
| `cerca_menu` | lettura | ospite, cliente, sala, cucina, admin | - |
| `dettaglio_piatto` | lettura | ospite, cliente, sala, cucina, admin | - |
| `verifica_disponibilita` | lettura | ospite, cliente, sala, cucina, admin | data, ora, coperti |
| `orari_disponibili` | lettura | ospite, cliente, sala, cucina, admin | data, coperti |
| `trova_prenotazioni` | lettura | ospite, cliente, sala, admin | - |
| `crea_prenotazione` | scrittura | ospite, cliente, sala, admin | data, ora, coperti |
| `modifica_prenotazione` | scrittura | ospite, cliente, sala, admin | id_prenotazione |
| `cancella_prenotazione` | scrittura distruttiva | ospite, cliente, sala, admin | id_prenotazione |
| `prenotazioni_del_giorno` | lettura | sala, admin | data |
| `crea_ordine_asporto` | scrittura | ospite, cliente, sala, admin | righe, ora_ritiro |
| `stato_ordine` | lettura | ospite, cliente, sala, cucina, admin | id_ordine |
| `ordini_da_preparare` | lettura | sala, cucina, admin | - |
| `aggiorna_stato_ordine` | scrittura | sala, cucina, admin | id_ordine, nuovo_stato |
| `aggiorna_scorta` | scrittura | admin | ingrediente, quantita |
| `imposta_disponibilita_piatto` | scrittura | admin | nome, disponibile |

## `mio_profilo`

Restituisce il ruolo e il nome dell'utente con cui si sta parlando e i tool che può usare.
Il ruolo deriva dall'accesso effettuato, non da quanto dichiarato nella conversazione.

**Effetti sui dati:** Sola lettura (`readOnlyHint: true`): nessun effetto sui dati, non richiede conferma.

**Ruoli autorizzati:** ospite, cliente, sala, cucina, admin.

**Schema dei parametri di ingresso:**

```json
{
  "type": "object",
  "properties": {},
  "title": "mio_profiloArguments"
}
```

**Schema di uscita:**

```json
{
  "properties": {
    "ruolo": {
      "description": "ospite | cliente | sala | cucina | admin",
      "title": "Ruolo",
      "type": "string"
    },
    "descrizione_ruolo": {
      "title": "Descrizione Ruolo",
      "type": "string"
    },
    "nome": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Nome dell'utente autenticato (assente per gli ospiti).",
      "title": "Nome"
    },
    "tool_consentiti": {
      "items": {
        "type": "string"
      },
      "title": "Tool Consentiti",
      "type": "array"
    }
  },
  "required": [
    "ruolo",
    "descrizione_ruolo",
    "tool_consentiti"
  ],
  "title": "Profilo",
  "type": "object"
}
```

**Esempio di invocazione:**

```json
{
  "name": "mio_profilo",
  "arguments": {}
}
```

**Risultato:**

```json
{
  "ruolo": "admin",
  "descrizione_ruolo": "Amministratore",
  "nome": "Amministratore",
  "tool_consentiti": [
    "aggiorna_scorta",
    "aggiorna_stato_ordine",
    "cancella_prenotazione",
    "cerca_menu",
    "crea_ordine_asporto",
    "crea_prenotazione",
    "dettaglio_piatto",
    "imposta_disponibilita_piatto",
    "mio_profilo",
    "modifica_prenotazione",
    "orari_apertura",
    "orari_disponibili",
    "ordini_da_preparare",
    "prenotazioni_del_giorno",
    "stato_ordine",
    "trova_prenotazioni",
    "verifica_disponibilita"
  ]
}
```

## `orari_apertura`

Restituisce la data e l'ora attuali e gli orari di apertura del ristorante per ogni giorno della settimana.
Usare per domande sugli orari o per sapere che giorno è oggi.

**Effetti sui dati:** Sola lettura (`readOnlyHint: true`): nessun effetto sui dati, non richiede conferma.

**Ruoli autorizzati:** ospite, cliente, sala, cucina, admin.

**Schema dei parametri di ingresso:**

```json
{
  "type": "object",
  "properties": {},
  "title": "orari_aperturaArguments"
}
```

**Schema di uscita:**

```json
{
  "properties": {
    "oggi": {
      "description": "Data e ora attuali (AAAA-MM-GGTHH:MM).",
      "title": "Oggi",
      "type": "string"
    },
    "settimana": {
      "description": "Orari per ogni giorno della settimana.",
      "items": {
        "type": "string"
      },
      "title": "Settimana",
      "type": "array"
    }
  },
  "required": [
    "oggi",
    "settimana"
  ],
  "title": "OrariApertura",
  "type": "object"
}
```

**Esempio di invocazione:**

```json
{
  "name": "orari_apertura",
  "arguments": {}
}
```

**Risultato:**

```json
{
  "oggi": "2026-12-03T11:00",
  "settimana": [
    "lunedì il ristorante è chiuso",
    "martedì: pranzo 12:00-15:00, cena 19:00-23:30",
    "mercoledì: pranzo 12:00-15:00, cena 19:00-23:30",
    "giovedì: pranzo 12:00-15:00, cena 19:00-23:30",
    "venerdì: pranzo 12:00-15:00, cena 19:00-23:30",
    "sabato: pranzo 12:00-15:00, cena 19:00-23:30",
    "domenica: pranzo 12:00-15:00, cena 19:00-23:30"
  ]
}
```

## `cerca_menu`

Cerca i piatti del menu con filtri opzionali. Senza filtri restituisce l'intero menu.
Ogni piatto riporta prezzo, allergeni e disponibilità.

**Effetti sui dati:** Sola lettura (`readOnlyHint: true`): nessun effetto sui dati, non richiede conferma.

**Ruoli autorizzati:** ospite, cliente, sala, cucina, admin.

**Schema dei parametri di ingresso:**

```json
{
  "type": "object",
  "properties": {
    "testo": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Parola da cercare nel nome o nella descrizione (es. 'carbonara').",
      "title": "Testo"
    },
    "categoria": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Antipasti, Primi, Secondi, Contorni, Dolci o Bevande.",
      "title": "Categoria"
    },
    "escludi_allergeni": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Allergeni da escludere, es. ['glutine', 'latte']. Codici: glutine, crostacei, uova, pesce, arachidi, soia, latte, frutta_a_guscio, sedano, senape, sesamo, solfiti, lupini, molluschi.",
      "title": "Escludi Allergeni"
    },
    "solo_vegetariani": {
      "default": false,
      "description": "True per mostrare solo piatti vegetariani.",
      "title": "Solo Vegetariani",
      "type": "boolean"
    },
    "solo_asporto": {
      "default": false,
      "description": "True per mostrare solo piatti ordinabili da asporto.",
      "title": "Solo Asporto",
      "type": "boolean"
    }
  },
  "title": "cerca_menuArguments"
}
```

**Schema di uscita:**

```json
{
  "$defs": {
    "Piatto": {
      "properties": {
        "id_articolo": {
          "title": "Id Articolo",
          "type": "integer"
        },
        "nome": {
          "title": "Nome",
          "type": "string"
        },
        "categoria": {
          "title": "Categoria",
          "type": "string"
        },
        "prezzo": {
          "description": "Prezzo in euro.",
          "title": "Prezzo",
          "type": "number"
        },
        "allergeni": {
          "description": "Codici degli allergeni presenti.",
          "items": {
            "type": "string"
          },
          "title": "Allergeni",
          "type": "array"
        },
        "vegetariano": {
          "title": "Vegetariano",
          "type": "boolean"
        },
        "asporto": {
          "description": "True se ordinabile da asporto.",
          "title": "Asporto",
          "type": "boolean"
        },
        "esaurito": {
          "description": "True se oggi non è più disponibile.",
          "title": "Esaurito",
          "type": "boolean"
        }
      },
      "required": [
        "id_articolo",
        "nome",
        "categoria",
        "prezzo",
        "allergeni",
        "vegetariano",
        "asporto",
        "esaurito"
      ],
      "title": "Piatto",
      "type": "object"
    }
  },
  "properties": {
    "numero_risultati": {
      "title": "Numero Risultati",
      "type": "integer"
    },
    "piatti": {
      "items": {
        "$ref": "#/$defs/Piatto"
      },
      "title": "Piatti",
      "type": "array"
    }
  },
  "required": [
    "numero_risultati",
    "piatti"
  ],
  "title": "RisultatoMenu",
  "type": "object"
}
```

**Esempio di invocazione:**

```json
{
  "name": "cerca_menu",
  "arguments": {
    "categoria": "Secondi",
    "escludi_allergeni": [
      "glutine",
      "latte"
    ]
  }
}
```

**Risultato:**

```json
{
  "numero_risultati": 3,
  "piatti": [
    {
      "id_articolo": 23,
      "nome": "Branzino al forno con patate",
      "categoria": "Secondi",
      "prezzo": 20.0,
      "allergeni": [
        "pesce"
      ],
      "vegetariano": false,
      "asporto": false,
      "esaurito": true
    },
    {
      "id_articolo": 24,
      "nome": "Pollo alla cacciatora",
      "categoria": "Secondi",
      "prezzo": 15.0,
      "allergeni": [
        "solfiti"
      ],
      "vegetariano": false,
      "asporto": true,
      "esaurito": false
    },
    {
      "id_articolo": 30,
      "nome": "Tofu grigliato con verdure",
      "categoria": "Secondi",
      "prezzo": 14.0,
      "allergeni": [
        "soia"
      ],
      "vegetariano": true,
      "asporto": true,
      "esaurito": false
    }
  ]
}
```

## `dettaglio_piatto`

Restituisce descrizione, ingredienti, ALLERGENI e porzioni ancora disponibili di un piatto.
Indicare il piatto per nome: non indovinare gli id. Usare sempre per domande su allergeni o ingredienti.

**Effetti sui dati:** Sola lettura (`readOnlyHint: true`): nessun effetto sui dati, non richiede conferma.

**Ruoli autorizzati:** ospite, cliente, sala, cucina, admin.

**Schema dei parametri di ingresso:**

```json
{
  "type": "object",
  "properties": {
    "nome": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Nome del piatto come lo dice il cliente (es. 'tiramisù', 'carbonara').",
      "title": "Nome"
    },
    "id_articolo": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "In alternativa al nome: id restituito da cerca_menu.",
      "title": "Id Articolo"
    }
  },
  "title": "dettaglio_piattoArguments"
}
```

**Schema di uscita:**

```json
{
  "properties": {
    "id_articolo": {
      "title": "Id Articolo",
      "type": "integer"
    },
    "nome": {
      "title": "Nome",
      "type": "string"
    },
    "categoria": {
      "title": "Categoria",
      "type": "string"
    },
    "descrizione": {
      "title": "Descrizione",
      "type": "string"
    },
    "prezzo": {
      "title": "Prezzo",
      "type": "number"
    },
    "ingredienti": {
      "items": {
        "type": "string"
      },
      "title": "Ingredienti",
      "type": "array"
    },
    "allergeni": {
      "items": {
        "type": "string"
      },
      "title": "Allergeni",
      "type": "array"
    },
    "vegetariano": {
      "title": "Vegetariano",
      "type": "boolean"
    },
    "asporto": {
      "title": "Asporto",
      "type": "boolean"
    },
    "porzioni_disponibili": {
      "description": "Porzioni ancora preparabili con le scorte attuali (0 = esaurito).",
      "title": "Porzioni Disponibili",
      "type": "integer"
    }
  },
  "required": [
    "id_articolo",
    "nome",
    "categoria",
    "descrizione",
    "prezzo",
    "ingredienti",
    "allergeni",
    "vegetariano",
    "asporto",
    "porzioni_disponibili"
  ],
  "title": "DettaglioPiatto",
  "type": "object"
}
```

**Esempio di invocazione:**

```json
{
  "name": "dettaglio_piatto",
  "arguments": {
    "nome": "tagliolini al tartufo"
  }
}
```

**Risultato:**

```json
{
  "id_articolo": 13,
  "nome": "Tagliolini al tartufo nero",
  "categoria": "Primi",
  "descrizione": "Pasta fresca all'uovo, burro, parmigiano e tartufo nero.",
  "prezzo": 22.0,
  "ingredienti": [
    "farina 00",
    "burro",
    "parmigiano",
    "tartufo nero",
    "uova"
  ],
  "allergeni": [
    "glutine",
    "latte",
    "uova"
  ],
  "vegetariano": true,
  "asporto": true,
  "porzioni_disponibili": 2
}
```

## `verifica_disponibilita`

Verifica se c'è un tavolo libero per data, ora e numero di persone indicati.
Se non c'è posto propone orari alternativi nello stesso turno. Non registra nulla.

**Effetti sui dati:** Sola lettura (`readOnlyHint: true`): nessun effetto sui dati, non richiede conferma.

**Ruoli autorizzati:** ospite, cliente, sala, cucina, admin.

**Schema dei parametri di ingresso:**

```json
{
  "type": "object",
  "properties": {
    "data": {
      "description": "Data AAAA-MM-GG, oppure direttamente le parole dell'utente: 'oggi', 'domani', 'dopodomani', il nome del giorno (es. 'sabato') o giorno e mese (es. '24 dicembre'): il sistema le converte nella data corretta.",
      "title": "Data",
      "type": "string"
    },
    "ora": {
      "description": "Ora nel formato HH:MM.",
      "title": "Ora",
      "type": "string"
    },
    "coperti": {
      "description": "Numero di persone.",
      "minimum": 1,
      "title": "Coperti",
      "type": "integer"
    }
  },
  "required": [
    "data",
    "ora",
    "coperti"
  ],
  "title": "verifica_disponibilitaArguments"
}
```

**Schema di uscita:**

```json
{
  "properties": {
    "data": {
      "title": "Data",
      "type": "string"
    },
    "ora": {
      "title": "Ora",
      "type": "string"
    },
    "coperti": {
      "title": "Coperti",
      "type": "integer"
    },
    "disponibile": {
      "title": "Disponibile",
      "type": "boolean"
    },
    "turno": {
      "description": "'pranzo' o 'cena'.",
      "title": "Turno",
      "type": "string"
    },
    "sala": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Sala indicativa, se disponibile.",
      "title": "Sala"
    },
    "orari_alternativi": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Altri orari liberi nello stesso turno, se l'orario richiesto non è disponibile.",
      "title": "Orari Alternativi"
    }
  },
  "required": [
    "data",
    "ora",
    "coperti",
    "disponibile",
    "turno"
  ],
  "title": "Disponibilita",
  "type": "object"
}
```

**Esempio di invocazione:**

```json
{
  "name": "verifica_disponibilita",
  "arguments": {
    "data": "sabato",
    "ora": "20:30",
    "coperti": 4
  }
}
```

**Risultato:**

```json
{
  "data": "2026-12-05",
  "ora": "20:30",
  "coperti": 4,
  "disponibile": false,
  "turno": "cena",
  "sala": null,
  "orari_alternativi": [
    "22:00"
  ]
}
```

## `orari_disponibili`

Elenca TUTTI gli orari della giornata (pranzo e cena, ogni 30 minuti) in cui c'è un tavolo libero
per il numero di persone indicato. Usare quando il cliente chiede quali orari sono disponibili o
vuole alternative, invece di provare un orario alla volta. Non registra nulla.

**Effetti sui dati:** Sola lettura (`readOnlyHint: true`): nessun effetto sui dati, non richiede conferma.

**Ruoli autorizzati:** ospite, cliente, sala, cucina, admin.

**Schema dei parametri di ingresso:**

```json
{
  "type": "object",
  "properties": {
    "data": {
      "description": "Data AAAA-MM-GG, oppure direttamente le parole dell'utente: 'oggi', 'domani', 'dopodomani', il nome del giorno (es. 'sabato') o giorno e mese (es. '24 dicembre'): il sistema le converte nella data corretta.",
      "title": "Data",
      "type": "string"
    },
    "coperti": {
      "description": "Numero di persone.",
      "minimum": 1,
      "title": "Coperti",
      "type": "integer"
    }
  },
  "required": [
    "data",
    "coperti"
  ],
  "title": "orari_disponibiliArguments"
}
```

**Schema di uscita:**

```json
{
  "properties": {
    "data": {
      "title": "Data",
      "type": "string"
    },
    "coperti": {
      "title": "Coperti",
      "type": "integer"
    },
    "chiuso": {
      "description": "True se il ristorante quel giorno è chiuso.",
      "title": "Chiuso",
      "type": "boolean"
    },
    "turni": {
      "additionalProperties": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "description": "Per ogni turno ('pranzo', 'cena') gli orari HH:MM con tavolo libero.",
      "title": "Turni",
      "type": "object"
    },
    "messaggio": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Messaggio"
    }
  },
  "required": [
    "data",
    "coperti",
    "chiuso",
    "turni"
  ],
  "title": "OrariDisponibili",
  "type": "object"
}
```

**Esempio di invocazione:**

```json
{
  "name": "orari_disponibili",
  "arguments": {
    "data": "sabato",
    "coperti": 4
  }
}
```

**Risultato:**

```json
{
  "data": "2026-12-05",
  "coperti": 4,
  "chiuso": false,
  "turni": {
    "pranzo": [
      "12:00",
      "12:30",
      "13:00",
      "13:30"
    ],
    "cena": [
      "22:00"
    ]
  },
  "messaggio": null
}
```

## `trova_prenotazioni`

Cerca le prenotazioni attive (da oggi in poi). Un cliente registrato vede solo le proprie, anche senza filtri;
negli altri casi indicare almeno uno tra nome, telefono e data.

**Effetti sui dati:** Sola lettura (`readOnlyHint: true`): nessun effetto sui dati, non richiede conferma.

**Ruoli autorizzati:** ospite, cliente, sala, admin.

**Schema dei parametri di ingresso:**

```json
{
  "type": "object",
  "properties": {
    "nome": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Nome (anche parziale) del cliente.",
      "title": "Nome"
    },
    "telefono": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Telefono del cliente.",
      "title": "Telefono"
    },
    "data": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Data AAAA-MM-GG, oppure direttamente le parole dell'utente: 'oggi', 'domani', 'dopodomani', il nome del giorno (es. 'sabato') o giorno e mese (es. '24 dicembre'): il sistema le converte nella data corretta.",
      "title": "Data"
    }
  },
  "title": "trova_prenotazioniArguments"
}
```

**Schema di uscita:**

```json
{
  "$defs": {
    "Prenotazione": {
      "properties": {
        "id_prenotazione": {
          "title": "Id Prenotazione",
          "type": "integer"
        },
        "data": {
          "title": "Data",
          "type": "string"
        },
        "ora": {
          "title": "Ora",
          "type": "string"
        },
        "coperti": {
          "title": "Coperti",
          "type": "integer"
        },
        "nome_cliente": {
          "title": "Nome Cliente",
          "type": "string"
        },
        "telefono": {
          "title": "Telefono",
          "type": "string"
        },
        "note": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Note"
        },
        "stato": {
          "title": "Stato",
          "type": "string"
        },
        "tavolo": {
          "title": "Tavolo",
          "type": "string"
        },
        "sala": {
          "title": "Sala",
          "type": "string"
        }
      },
      "required": [
        "id_prenotazione",
        "data",
        "ora",
        "coperti",
        "nome_cliente",
        "telefono",
        "note",
        "stato",
        "tavolo",
        "sala"
      ],
      "title": "Prenotazione",
      "type": "object"
    }
  },
  "properties": {
    "numero_risultati": {
      "title": "Numero Risultati",
      "type": "integer"
    },
    "prenotazioni": {
      "items": {
        "$ref": "#/$defs/Prenotazione"
      },
      "title": "Prenotazioni",
      "type": "array"
    }
  },
  "required": [
    "numero_risultati",
    "prenotazioni"
  ],
  "title": "ElencoPrenotazioni",
  "type": "object"
}
```

**Esempio di invocazione:**

```json
{
  "name": "trova_prenotazioni",
  "arguments": {
    "telefono": "333 1234567"
  }
}
```

**Risultato:**

```json
{
  "numero_risultati": 1,
  "prenotazioni": [
    {
      "id_prenotazione": 86,
      "data": "2026-12-11",
      "ora": "20:30",
      "coperti": 2,
      "nome_cliente": "Giulia Ferri",
      "telefono": "3331234567",
      "note": "Anniversario",
      "stato": "confermata",
      "tavolo": "T1",
      "sala": "Sala interna"
    }
  ]
}
```

## `crea_prenotazione`

Registra una nuova prenotazione e assegna un tavolo. SCRIVE sui dati.
Controlla da sola la disponibilità. Per un ospite servono nome e telefono reali forniti dal cliente
(non inventarli); per un cliente registrato si usano i dati del suo profilo.

**Effetti sui dati:** **Scrittura** (`readOnlyHint: false`): modifica la base dati; l'harness chiede conferma all'utente.

**Ruoli autorizzati:** ospite, cliente, sala, admin.

**Schema dei parametri di ingresso:**

```json
{
  "type": "object",
  "properties": {
    "data": {
      "description": "Data AAAA-MM-GG, oppure direttamente le parole dell'utente: 'oggi', 'domani', 'dopodomani', il nome del giorno (es. 'sabato') o giorno e mese (es. '24 dicembre'): il sistema le converte nella data corretta.",
      "title": "Data",
      "type": "string"
    },
    "ora": {
      "description": "Ora nel formato HH:MM.",
      "title": "Ora",
      "type": "string"
    },
    "coperti": {
      "description": "Numero di persone.",
      "minimum": 1,
      "title": "Coperti",
      "type": "integer"
    },
    "nome_cliente": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Nome e cognome del cliente (non serve per i clienti registrati).",
      "title": "Nome Cliente"
    },
    "telefono": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Telefono del cliente (non serve per i clienti registrati).",
      "title": "Telefono"
    },
    "note": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Richieste particolari (es. seggiolone).",
      "title": "Note"
    }
  },
  "required": [
    "data",
    "ora",
    "coperti"
  ],
  "title": "crea_prenotazioneArguments"
}
```

**Schema di uscita:**

```json
{
  "properties": {
    "id_prenotazione": {
      "title": "Id Prenotazione",
      "type": "integer"
    },
    "data": {
      "title": "Data",
      "type": "string"
    },
    "ora": {
      "title": "Ora",
      "type": "string"
    },
    "coperti": {
      "title": "Coperti",
      "type": "integer"
    },
    "nome_cliente": {
      "title": "Nome Cliente",
      "type": "string"
    },
    "telefono": {
      "title": "Telefono",
      "type": "string"
    },
    "note": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Note"
    },
    "stato": {
      "title": "Stato",
      "type": "string"
    },
    "tavolo": {
      "title": "Tavolo",
      "type": "string"
    },
    "sala": {
      "title": "Sala",
      "type": "string"
    }
  },
  "required": [
    "id_prenotazione",
    "data",
    "ora",
    "coperti",
    "nome_cliente",
    "telefono",
    "note",
    "stato",
    "tavolo",
    "sala"
  ],
  "title": "Prenotazione",
  "type": "object"
}
```

**Esempio di invocazione:**

```json
{
  "name": "crea_prenotazione",
  "arguments": {
    "data": "domani",
    "ora": "20:30",
    "coperti": 2,
    "nome_cliente": "Marco Gallo",
    "telefono": "340 555 1234",
    "note": "Tavolo tranquillo"
  }
}
```

**Risultato:**

```json
{
  "id_prenotazione": 185,
  "data": "2026-12-04",
  "ora": "20:30",
  "coperti": 2,
  "nome_cliente": "Marco Gallo",
  "telefono": "3405551234",
  "note": "Tavolo tranquillo",
  "stato": "confermata",
  "tavolo": "T2",
  "sala": "Sala interna"
}
```

## `modifica_prenotazione`

Modifica data, ora, coperti o note di una prenotazione esistente. SCRIVE sui dati.
Indicare solo i campi da cambiare. Se non c'è posto la prenotazione resta invariata.

**Effetti sui dati:** **Scrittura** (`readOnlyHint: false`): modifica la base dati; l'harness chiede conferma all'utente.

**Ruoli autorizzati:** ospite, cliente, sala, admin.

**Schema dei parametri di ingresso:**

```json
{
  "type": "object",
  "properties": {
    "id_prenotazione": {
      "description": "Numero della prenotazione.",
      "title": "Id Prenotazione",
      "type": "integer"
    },
    "telefono": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Telefono usato per la prenotazione o l'ordine (verifica dell'identità). Non serve per i clienti registrati né per il personale.",
      "title": "Telefono"
    },
    "data": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Nuova data. Data AAAA-MM-GG, oppure direttamente le parole dell'utente: 'oggi', 'domani', 'dopodomani', il nome del giorno (es. 'sabato') o giorno e mese (es. '24 dicembre'): il sistema le converte nella data corretta.",
      "title": "Data"
    },
    "ora": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Nuova ora HH:MM.",
      "title": "Ora"
    },
    "coperti": {
      "anyOf": [
        {
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Nuovo numero di persone.",
      "title": "Coperti"
    },
    "note": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Nuove note.",
      "title": "Note"
    }
  },
  "required": [
    "id_prenotazione"
  ],
  "title": "modifica_prenotazioneArguments"
}
```

**Schema di uscita:**

```json
{
  "properties": {
    "id_prenotazione": {
      "title": "Id Prenotazione",
      "type": "integer"
    },
    "data": {
      "title": "Data",
      "type": "string"
    },
    "ora": {
      "title": "Ora",
      "type": "string"
    },
    "coperti": {
      "title": "Coperti",
      "type": "integer"
    },
    "nome_cliente": {
      "title": "Nome Cliente",
      "type": "string"
    },
    "telefono": {
      "title": "Telefono",
      "type": "string"
    },
    "note": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Note"
    },
    "stato": {
      "title": "Stato",
      "type": "string"
    },
    "tavolo": {
      "title": "Tavolo",
      "type": "string"
    },
    "sala": {
      "title": "Sala",
      "type": "string"
    }
  },
  "required": [
    "id_prenotazione",
    "data",
    "ora",
    "coperti",
    "nome_cliente",
    "telefono",
    "note",
    "stato",
    "tavolo",
    "sala"
  ],
  "title": "Prenotazione",
  "type": "object"
}
```

**Esempio di invocazione:**

```json
{
  "name": "modifica_prenotazione",
  "arguments": {
    "id_prenotazione": 86,
    "ora": "21:00",
    "coperti": 4
  }
}
```

**Risultato:**

```json
{
  "id_prenotazione": 86,
  "data": "2026-12-11",
  "ora": "21:00",
  "coperti": 4,
  "nome_cliente": "Giulia Ferri",
  "telefono": "3331234567",
  "note": "Anniversario",
  "stato": "confermata",
  "tavolo": "T7",
  "sala": "Sala interna"
}
```

## `cancella_prenotazione`

Cancella una prenotazione esistente. SCRIVE sui dati e non è annullabile.

**Effetti sui dati:** **Scrittura** (`readOnlyHint: false`): modifica la base dati; l'harness chiede conferma all'utente. **Distruttivo** (`destructiveHint: true`): l'operazione non è annullabile.

**Ruoli autorizzati:** ospite, cliente, sala, admin.

**Schema dei parametri di ingresso:**

```json
{
  "type": "object",
  "properties": {
    "id_prenotazione": {
      "description": "Numero della prenotazione.",
      "title": "Id Prenotazione",
      "type": "integer"
    },
    "telefono": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Telefono usato per la prenotazione o l'ordine (verifica dell'identità). Non serve per i clienti registrati né per il personale.",
      "title": "Telefono"
    }
  },
  "required": [
    "id_prenotazione"
  ],
  "title": "cancella_prenotazioneArguments"
}
```

**Schema di uscita:**

```json
{
  "properties": {
    "id_prenotazione": {
      "title": "Id Prenotazione",
      "type": "integer"
    },
    "data": {
      "title": "Data",
      "type": "string"
    },
    "ora": {
      "title": "Ora",
      "type": "string"
    },
    "coperti": {
      "title": "Coperti",
      "type": "integer"
    },
    "nome_cliente": {
      "title": "Nome Cliente",
      "type": "string"
    },
    "telefono": {
      "title": "Telefono",
      "type": "string"
    },
    "note": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Note"
    },
    "stato": {
      "title": "Stato",
      "type": "string"
    },
    "tavolo": {
      "title": "Tavolo",
      "type": "string"
    },
    "sala": {
      "title": "Sala",
      "type": "string"
    }
  },
  "required": [
    "id_prenotazione",
    "data",
    "ora",
    "coperti",
    "nome_cliente",
    "telefono",
    "note",
    "stato",
    "tavolo",
    "sala"
  ],
  "title": "Prenotazione",
  "type": "object"
}
```

**Esempio di invocazione:**

```json
{
  "name": "cancella_prenotazione",
  "arguments": {
    "id_prenotazione": 86
  }
}
```

**Risultato:**

```json
{
  "id_prenotazione": 86,
  "data": "2026-12-11",
  "ora": "21:00",
  "coperti": 4,
  "nome_cliente": "Giulia Ferri",
  "telefono": "3331234567",
  "note": "Anniversario",
  "stato": "cancellata",
  "tavolo": "T7",
  "sala": "Sala interna"
}
```

## `prenotazioni_del_giorno`

Quadro della sala per una data: tutte le prenotazioni attive con tavolo e coperti per turno.
Riservato al personale di sala e all'amministratore.

**Effetti sui dati:** Sola lettura (`readOnlyHint: true`): nessun effetto sui dati, non richiede conferma.

**Ruoli autorizzati:** sala, admin.

**Schema dei parametri di ingresso:**

```json
{
  "type": "object",
  "properties": {
    "data": {
      "description": "Data AAAA-MM-GG, oppure direttamente le parole dell'utente: 'oggi', 'domani', 'dopodomani', il nome del giorno (es. 'sabato') o giorno e mese (es. '24 dicembre'): il sistema le converte nella data corretta.",
      "title": "Data",
      "type": "string"
    }
  },
  "required": [
    "data"
  ],
  "title": "prenotazioni_del_giornoArguments"
}
```

**Schema di uscita:**

```json
{
  "$defs": {
    "Prenotazione": {
      "properties": {
        "id_prenotazione": {
          "title": "Id Prenotazione",
          "type": "integer"
        },
        "data": {
          "title": "Data",
          "type": "string"
        },
        "ora": {
          "title": "Ora",
          "type": "string"
        },
        "coperti": {
          "title": "Coperti",
          "type": "integer"
        },
        "nome_cliente": {
          "title": "Nome Cliente",
          "type": "string"
        },
        "telefono": {
          "title": "Telefono",
          "type": "string"
        },
        "note": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Note"
        },
        "stato": {
          "title": "Stato",
          "type": "string"
        },
        "tavolo": {
          "title": "Tavolo",
          "type": "string"
        },
        "sala": {
          "title": "Sala",
          "type": "string"
        }
      },
      "required": [
        "id_prenotazione",
        "data",
        "ora",
        "coperti",
        "nome_cliente",
        "telefono",
        "note",
        "stato",
        "tavolo",
        "sala"
      ],
      "title": "Prenotazione",
      "type": "object"
    }
  },
  "properties": {
    "data": {
      "title": "Data",
      "type": "string"
    },
    "numero_prenotazioni": {
      "title": "Numero Prenotazioni",
      "type": "integer"
    },
    "coperti_pranzo": {
      "title": "Coperti Pranzo",
      "type": "integer"
    },
    "coperti_cena": {
      "title": "Coperti Cena",
      "type": "integer"
    },
    "prenotazioni": {
      "items": {
        "$ref": "#/$defs/Prenotazione"
      },
      "title": "Prenotazioni",
      "type": "array"
    }
  },
  "required": [
    "data",
    "numero_prenotazioni",
    "coperti_pranzo",
    "coperti_cena",
    "prenotazioni"
  ],
  "title": "QuadroSala",
  "type": "object"
}
```

**Esempio di invocazione:**

```json
{
  "name": "prenotazioni_del_giorno",
  "arguments": {
    "data": "domani"
  }
}
```

**Risultato:**

```json
{
  "data": "2026-12-04",
  "numero_prenotazioni": 3,
  "coperti_pranzo": 0,
  "coperti_cena": 9,
  "prenotazioni": [
    {
      "id_prenotazione": 185,
      "data": "2026-12-04",
      "ora": "20:30",
      "coperti": 2,
      "nome_cliente": "Marco Gallo",
      "telefono": "3405551234",
      "note": "Tavolo tranquillo",
      "stato": "confermata",
      "tavolo": "T2",
      "sala": "Sala interna"
    },
    {
      "id_prenotazione": 88,
      "data": "2026-12-04",
      "ora": "20:30",
      "coperti": 5,
      "nome_cliente": "Sandro Tedesco",
      "telefono": "3578091343",
      "note": "Compleanno",
      "stato": "confermata",
      "tavolo": "V3",
      "sala": "Veranda"
    },
    {
      "id_prenotazione": 87,
      "data": "2026-12-04",
      "ora": "21:30",
      "coperti": 2,
      "nome_cliente": "Luca Bettoni",
      "telefono": "3262174596",
      "note": "Compleanno",
      "stato": "confermata",
      "tavolo": "T1",
      "sala": "Sala interna"
    }
  ]
}
```

## `crea_ordine_asporto`

Registra un ordine da asporto e scala le scorte degli ingredienti. SCRIVE sui dati.
Indicare i piatti per NOME (non serve cercare prima gli id). Fallisce, senza registrare nulla,
se un piatto non esiste o è ambiguo, non è da asporto, le scorte non bastano o l'orario non è valido.

**Effetti sui dati:** **Scrittura** (`readOnlyHint: false`): modifica la base dati; l'harness chiede conferma all'utente.

**Ruoli autorizzati:** ospite, cliente, sala, admin.

**Schema dei parametri di ingresso:**

```json
{
  "type": "object",
  "$defs": {
    "RigaOrdineIn": {
      "properties": {
        "nome": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Nome del piatto come lo dice il cliente (es. 'carbonara', 'tiramisù').",
          "title": "Nome"
        },
        "id_articolo": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "In alternativa al nome: id restituito da cerca_menu.",
          "title": "Id Articolo"
        },
        "quantita": {
          "default": 1,
          "description": "Numero di porzioni.",
          "maximum": 20,
          "minimum": 1,
          "title": "Quantita",
          "type": "integer"
        },
        "note": {
          "anyOf": [
            {
              "maxLength": 120,
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Richieste particolari sul piatto.",
          "title": "Note"
        }
      },
      "title": "RigaOrdineIn",
      "type": "object"
    }
  },
  "properties": {
    "righe": {
      "description": "Piatti ordinati, indicati per nome (es. [{'nome': 'carbonara', 'quantita': 2}]).",
      "items": {
        "$ref": "#/$defs/RigaOrdineIn"
      },
      "minItems": 1,
      "title": "Righe",
      "type": "array"
    },
    "ora_ritiro": {
      "description": "Ora di ritiro HH:MM.",
      "title": "Ora Ritiro",
      "type": "string"
    },
    "nome_cliente": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Nome del cliente (non serve per i clienti registrati).",
      "title": "Nome Cliente"
    },
    "telefono": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Telefono del cliente (non serve per i clienti registrati).",
      "title": "Telefono"
    },
    "data_ritiro": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Data di ritiro; se assente, oggi. Data AAAA-MM-GG, oppure direttamente le parole dell'utente: 'oggi', 'domani', 'dopodomani', il nome del giorno (es. 'sabato') o giorno e mese (es. '24 dicembre'): il sistema le converte nella data corretta.",
      "title": "Data Ritiro"
    },
    "note": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Note sull'ordine.",
      "title": "Note"
    }
  },
  "required": [
    "righe",
    "ora_ritiro"
  ],
  "title": "crea_ordine_asportoArguments"
}
```

**Schema di uscita:**

```json
{
  "$defs": {
    "RigaOrdine": {
      "properties": {
        "id_articolo": {
          "title": "Id Articolo",
          "type": "integer"
        },
        "nome": {
          "title": "Nome",
          "type": "string"
        },
        "quantita": {
          "title": "Quantita",
          "type": "integer"
        },
        "prezzo_unitario": {
          "title": "Prezzo Unitario",
          "type": "number"
        },
        "note": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Note"
        }
      },
      "required": [
        "id_articolo",
        "nome",
        "quantita",
        "prezzo_unitario",
        "note"
      ],
      "title": "RigaOrdine",
      "type": "object"
    }
  },
  "properties": {
    "id_ordine": {
      "title": "Id Ordine",
      "type": "integer"
    },
    "nome_cliente": {
      "title": "Nome Cliente",
      "type": "string"
    },
    "data_ritiro": {
      "title": "Data Ritiro",
      "type": "string"
    },
    "ora_ritiro": {
      "title": "Ora Ritiro",
      "type": "string"
    },
    "stato": {
      "description": "ricevuto | in_preparazione | pronto | ritirato | annullato",
      "title": "Stato",
      "type": "string"
    },
    "totale": {
      "title": "Totale",
      "type": "number"
    },
    "note": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Note"
    },
    "righe": {
      "items": {
        "$ref": "#/$defs/RigaOrdine"
      },
      "title": "Righe",
      "type": "array"
    }
  },
  "required": [
    "id_ordine",
    "nome_cliente",
    "data_ritiro",
    "ora_ritiro",
    "stato",
    "totale",
    "note",
    "righe"
  ],
  "title": "Ordine",
  "type": "object"
}
```

**Esempio di invocazione:**

```json
{
  "name": "crea_ordine_asporto",
  "arguments": {
    "nome_cliente": "Paolo Riva",
    "telefono": "320 987 6543",
    "ora_ritiro": "20:30",
    "righe": [
      {
        "nome": "carbonara",
        "quantita": 2
      },
      {
        "nome": "tiramisù",
        "quantita": 1
      }
    ]
  }
}
```

**Risultato:**

```json
{
  "id_ordine": 2,
  "nome_cliente": "Paolo Riva",
  "data_ritiro": "2026-12-03",
  "ora_ritiro": "20:30",
  "stato": "ricevuto",
  "totale": 31.0,
  "note": null,
  "righe": [
    {
      "id_articolo": 10,
      "nome": "Spaghetti alla carbonara",
      "quantita": 2,
      "prezzo_unitario": 12.0,
      "note": null
    },
    {
      "id_articolo": 35,
      "nome": "Tiramisù",
      "quantita": 1,
      "prezzo_unitario": 7.0,
      "note": null
    }
  ]
}
```

## `stato_ordine`

Restituisce stato, orario di ritiro e contenuto di un ordine da asporto.

**Effetti sui dati:** Sola lettura (`readOnlyHint: true`): nessun effetto sui dati, non richiede conferma.

**Ruoli autorizzati:** ospite, cliente, sala, cucina, admin.

**Schema dei parametri di ingresso:**

```json
{
  "type": "object",
  "properties": {
    "id_ordine": {
      "description": "Numero dell'ordine.",
      "title": "Id Ordine",
      "type": "integer"
    },
    "telefono": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Telefono usato per la prenotazione o l'ordine (verifica dell'identità). Non serve per i clienti registrati né per il personale.",
      "title": "Telefono"
    }
  },
  "required": [
    "id_ordine"
  ],
  "title": "stato_ordineArguments"
}
```

**Schema di uscita:**

```json
{
  "$defs": {
    "RigaOrdine": {
      "properties": {
        "id_articolo": {
          "title": "Id Articolo",
          "type": "integer"
        },
        "nome": {
          "title": "Nome",
          "type": "string"
        },
        "quantita": {
          "title": "Quantita",
          "type": "integer"
        },
        "prezzo_unitario": {
          "title": "Prezzo Unitario",
          "type": "number"
        },
        "note": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Note"
        }
      },
      "required": [
        "id_articolo",
        "nome",
        "quantita",
        "prezzo_unitario",
        "note"
      ],
      "title": "RigaOrdine",
      "type": "object"
    }
  },
  "properties": {
    "id_ordine": {
      "title": "Id Ordine",
      "type": "integer"
    },
    "nome_cliente": {
      "title": "Nome Cliente",
      "type": "string"
    },
    "data_ritiro": {
      "title": "Data Ritiro",
      "type": "string"
    },
    "ora_ritiro": {
      "title": "Ora Ritiro",
      "type": "string"
    },
    "stato": {
      "description": "ricevuto | in_preparazione | pronto | ritirato | annullato",
      "title": "Stato",
      "type": "string"
    },
    "totale": {
      "title": "Totale",
      "type": "number"
    },
    "note": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Note"
    },
    "righe": {
      "items": {
        "$ref": "#/$defs/RigaOrdine"
      },
      "title": "Righe",
      "type": "array"
    }
  },
  "required": [
    "id_ordine",
    "nome_cliente",
    "data_ritiro",
    "ora_ritiro",
    "stato",
    "totale",
    "note",
    "righe"
  ],
  "title": "Ordine",
  "type": "object"
}
```

**Esempio di invocazione:**

```json
{
  "name": "stato_ordine",
  "arguments": {
    "id_ordine": 1
  }
}
```

**Risultato:**

```json
{
  "id_ordine": 1,
  "nome_cliente": "Luca Bianchi",
  "data_ritiro": "2026-12-03",
  "ora_ritiro": "20:00",
  "stato": "in_preparazione",
  "totale": 40.0,
  "note": null,
  "righe": [
    {
      "id_articolo": 18,
      "nome": "Lasagne alla bolognese",
      "quantita": 2,
      "prezzo_unitario": 13.0,
      "note": null
    },
    {
      "id_articolo": 35,
      "nome": "Tiramisù",
      "quantita": 2,
      "prezzo_unitario": 7.0,
      "note": null
    }
  ]
}
```

## `ordini_da_preparare`

Elenco degli ordini da asporto ancora da evadere (ricevuti, in preparazione, pronti), in ordine di ritiro.
Riservato a cucina, sala e amministratore.

**Effetti sui dati:** Sola lettura (`readOnlyHint: true`): nessun effetto sui dati, non richiede conferma.

**Ruoli autorizzati:** sala, cucina, admin.

**Schema dei parametri di ingresso:**

```json
{
  "type": "object",
  "properties": {
    "data": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Data di ritiro; se assente, oggi. Data AAAA-MM-GG, oppure direttamente le parole dell'utente: 'oggi', 'domani', 'dopodomani', il nome del giorno (es. 'sabato') o giorno e mese (es. '24 dicembre'): il sistema le converte nella data corretta.",
      "title": "Data"
    }
  },
  "title": "ordini_da_preparareArguments"
}
```

**Schema di uscita:**

```json
{
  "$defs": {
    "Ordine": {
      "properties": {
        "id_ordine": {
          "title": "Id Ordine",
          "type": "integer"
        },
        "nome_cliente": {
          "title": "Nome Cliente",
          "type": "string"
        },
        "data_ritiro": {
          "title": "Data Ritiro",
          "type": "string"
        },
        "ora_ritiro": {
          "title": "Ora Ritiro",
          "type": "string"
        },
        "stato": {
          "description": "ricevuto | in_preparazione | pronto | ritirato | annullato",
          "title": "Stato",
          "type": "string"
        },
        "totale": {
          "title": "Totale",
          "type": "number"
        },
        "note": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Note"
        },
        "righe": {
          "items": {
            "$ref": "#/$defs/RigaOrdine"
          },
          "title": "Righe",
          "type": "array"
        }
      },
      "required": [
        "id_ordine",
        "nome_cliente",
        "data_ritiro",
        "ora_ritiro",
        "stato",
        "totale",
        "note",
        "righe"
      ],
      "title": "Ordine",
      "type": "object"
    },
    "RigaOrdine": {
      "properties": {
        "id_articolo": {
          "title": "Id Articolo",
          "type": "integer"
        },
        "nome": {
          "title": "Nome",
          "type": "string"
        },
        "quantita": {
          "title": "Quantita",
          "type": "integer"
        },
        "prezzo_unitario": {
          "title": "Prezzo Unitario",
          "type": "number"
        },
        "note": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Note"
        }
      },
      "required": [
        "id_articolo",
        "nome",
        "quantita",
        "prezzo_unitario",
        "note"
      ],
      "title": "RigaOrdine",
      "type": "object"
    }
  },
  "properties": {
    "data": {
      "title": "Data",
      "type": "string"
    },
    "numero_ordini": {
      "title": "Numero Ordini",
      "type": "integer"
    },
    "ordini": {
      "items": {
        "$ref": "#/$defs/Ordine"
      },
      "title": "Ordini",
      "type": "array"
    }
  },
  "required": [
    "data",
    "numero_ordini",
    "ordini"
  ],
  "title": "ElencoOrdini",
  "type": "object"
}
```

**Esempio di invocazione:**

```json
{
  "name": "ordini_da_preparare",
  "arguments": {}
}
```

**Risultato:**

```json
{
  "data": "2026-12-03",
  "numero_ordini": 2,
  "ordini": [
    {
      "id_ordine": 1,
      "nome_cliente": "Luca Bianchi",
      "data_ritiro": "2026-12-03",
      "ora_ritiro": "20:00",
      "stato": "in_preparazione",
      "totale": 40.0,
      "note": null,
      "righe": [
        {
          "id_articolo": 18,
          "nome": "Lasagne alla bolognese",
          "quantita": 2,
          "prezzo_unitario": 13.0,
          "note": null
        },
        {
          "id_articolo": 35,
          "nome": "Tiramisù",
          "quantita": 2,
          "prezzo_unitario": 7.0,
          "note": null
        }
      ]
    },
    {
      "id_ordine": 2,
      "nome_cliente": "Paolo Riva",
      "data_ritiro": "2026-12-03",
      "ora_ritiro": "20:30",
      "stato": "ricevuto",
      "totale": 31.0,
      "note": null,
      "righe": [
        {
          "id_articolo": 10,
          "nome": "Spaghetti alla carbonara",
          "quantita": 2,
          "prezzo_unitario": 12.0,
          "note": null
        },
        {
          "id_articolo": 35,
          "nome": "Tiramisù",
          "quantita": 1,
          "prezzo_unitario": 7.0,
          "note": null
        }
      ]
    }
  ]
}
```

## `aggiorna_stato_ordine`

Aggiorna lo stato di un ordine da asporto (es. da 'in_preparazione' a 'pronto'). SCRIVE sui dati.
Sono ammesse solo le transizioni coerenti. Riservato a cucina, sala e amministratore.

**Effetti sui dati:** **Scrittura** (`readOnlyHint: false`): modifica la base dati; l'harness chiede conferma all'utente.

**Ruoli autorizzati:** sala, cucina, admin.

**Schema dei parametri di ingresso:**

```json
{
  "type": "object",
  "properties": {
    "id_ordine": {
      "description": "Numero dell'ordine.",
      "title": "Id Ordine",
      "type": "integer"
    },
    "nuovo_stato": {
      "description": "Nuovo stato: in_preparazione, pronto, ritirato o annullato.",
      "enum": [
        "in_preparazione",
        "pronto",
        "ritirato",
        "annullato"
      ],
      "title": "Nuovo Stato",
      "type": "string"
    }
  },
  "required": [
    "id_ordine",
    "nuovo_stato"
  ],
  "title": "aggiorna_stato_ordineArguments"
}
```

**Schema di uscita:**

```json
{
  "$defs": {
    "RigaOrdine": {
      "properties": {
        "id_articolo": {
          "title": "Id Articolo",
          "type": "integer"
        },
        "nome": {
          "title": "Nome",
          "type": "string"
        },
        "quantita": {
          "title": "Quantita",
          "type": "integer"
        },
        "prezzo_unitario": {
          "title": "Prezzo Unitario",
          "type": "number"
        },
        "note": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Note"
        }
      },
      "required": [
        "id_articolo",
        "nome",
        "quantita",
        "prezzo_unitario",
        "note"
      ],
      "title": "RigaOrdine",
      "type": "object"
    }
  },
  "properties": {
    "id_ordine": {
      "title": "Id Ordine",
      "type": "integer"
    },
    "nome_cliente": {
      "title": "Nome Cliente",
      "type": "string"
    },
    "data_ritiro": {
      "title": "Data Ritiro",
      "type": "string"
    },
    "ora_ritiro": {
      "title": "Ora Ritiro",
      "type": "string"
    },
    "stato": {
      "description": "ricevuto | in_preparazione | pronto | ritirato | annullato",
      "title": "Stato",
      "type": "string"
    },
    "totale": {
      "title": "Totale",
      "type": "number"
    },
    "note": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Note"
    },
    "righe": {
      "items": {
        "$ref": "#/$defs/RigaOrdine"
      },
      "title": "Righe",
      "type": "array"
    }
  },
  "required": [
    "id_ordine",
    "nome_cliente",
    "data_ritiro",
    "ora_ritiro",
    "stato",
    "totale",
    "note",
    "righe"
  ],
  "title": "Ordine",
  "type": "object"
}
```

**Esempio di invocazione:**

```json
{
  "name": "aggiorna_stato_ordine",
  "arguments": {
    "id_ordine": 1,
    "nuovo_stato": "pronto"
  }
}
```

**Risultato:**

```json
{
  "id_ordine": 1,
  "nome_cliente": "Luca Bianchi",
  "data_ritiro": "2026-12-03",
  "ora_ritiro": "20:00",
  "stato": "pronto",
  "totale": 40.0,
  "note": null,
  "righe": [
    {
      "id_articolo": 18,
      "nome": "Lasagne alla bolognese",
      "quantita": 2,
      "prezzo_unitario": 13.0,
      "note": null
    },
    {
      "id_articolo": 35,
      "nome": "Tiramisù",
      "quantita": 2,
      "prezzo_unitario": 7.0,
      "note": null
    }
  ]
}
```

## `aggiorna_scorta`

Aggiorna la giacenza di un ingrediente in magazzino. SCRIVE sui dati. Riservato all'amministratore.

**Effetti sui dati:** **Scrittura** (`readOnlyHint: false`): modifica la base dati; l'harness chiede conferma all'utente.

**Ruoli autorizzati:** admin.

**Schema dei parametri di ingresso:**

```json
{
  "type": "object",
  "properties": {
    "ingrediente": {
      "description": "Nome dell'ingrediente (es. 'tartufo nero').",
      "title": "Ingrediente",
      "type": "string"
    },
    "quantita": {
      "description": "Quantità nell'unità di misura dell'ingrediente (g, ml, pz).",
      "minimum": 0,
      "title": "Quantita",
      "type": "number"
    },
    "modalita": {
      "default": "aggiungi",
      "description": "'aggiungi' per un carico di merce, 'imposta' per correggere la giacenza dopo un inventario.",
      "enum": [
        "aggiungi",
        "imposta"
      ],
      "title": "Modalita",
      "type": "string"
    }
  },
  "required": [
    "ingrediente",
    "quantita"
  ],
  "title": "aggiorna_scortaArguments"
}
```

**Schema di uscita:**

```json
{
  "properties": {
    "ingrediente": {
      "title": "Ingrediente",
      "type": "string"
    },
    "unita_misura": {
      "title": "Unita Misura",
      "type": "string"
    },
    "quantita_precedente": {
      "title": "Quantita Precedente",
      "type": "number"
    },
    "quantita_attuale": {
      "title": "Quantita Attuale",
      "type": "number"
    },
    "sotto_scorta_minima": {
      "title": "Sotto Scorta Minima",
      "type": "boolean"
    }
  },
  "required": [
    "ingrediente",
    "unita_misura",
    "quantita_precedente",
    "quantita_attuale",
    "sotto_scorta_minima"
  ],
  "title": "EsitoScorta",
  "type": "object"
}
```

**Esempio di invocazione:**

```json
{
  "name": "aggiorna_scorta",
  "arguments": {
    "ingrediente": "tartufo nero",
    "quantita": 200,
    "modalita": "aggiungi"
  }
}
```

**Risultato:**

```json
{
  "ingrediente": "tartufo nero",
  "unita_misura": "g",
  "quantita_precedente": 25.0,
  "quantita_attuale": 225.0,
  "sotto_scorta_minima": false
}
```

## `imposta_disponibilita_piatto`

Toglie o rimette un piatto nel menu. SCRIVE sui dati. Riservato all'amministratore.

**Effetti sui dati:** **Scrittura** (`readOnlyHint: false`): modifica la base dati; l'harness chiede conferma all'utente.

**Ruoli autorizzati:** admin.

**Schema dei parametri di ingresso:**

```json
{
  "type": "object",
  "properties": {
    "nome": {
      "description": "Nome del piatto.",
      "title": "Nome",
      "type": "string"
    },
    "disponibile": {
      "description": "True per rimetterlo nel menu, False per toglierlo.",
      "title": "Disponibile",
      "type": "boolean"
    }
  },
  "required": [
    "nome",
    "disponibile"
  ],
  "title": "imposta_disponibilita_piattoArguments"
}
```

**Schema di uscita:**

```json
{
  "properties": {
    "id_articolo": {
      "title": "Id Articolo",
      "type": "integer"
    },
    "nome": {
      "title": "Nome",
      "type": "string"
    },
    "nel_menu": {
      "title": "Nel Menu",
      "type": "boolean"
    }
  },
  "required": [
    "id_articolo",
    "nome",
    "nel_menu"
  ],
  "title": "DisponibilitaPiatto",
  "type": "object"
}
```

**Esempio di invocazione:**

```json
{
  "name": "imposta_disponibilita_piatto",
  "arguments": {
    "nome": "branzino al forno",
    "disponibile": false
  }
}
```

**Risultato:**

```json
{
  "id_articolo": 23,
  "nome": "Branzino al forno con patate",
  "nel_menu": false
}
```
