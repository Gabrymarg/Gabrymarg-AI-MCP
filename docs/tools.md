# Documentazione dei tool MCP

Generata automaticamente da `docs/genera_doc_tool.py` interrogando il server (`tools/list`).
Gli esempi sono stati eseguiti realmente su un database di prova (seed 42, orologio fissato a 2026-12-03T11:00).

| Tool | Effetti | Parametri obbligatori |
|---|---|---|
| `orari_apertura` | lettura | - |
| `cerca_menu` | lettura | - |
| `dettaglio_piatto` | lettura | - |
| `verifica_disponibilita` | lettura | data, ora, coperti |
| `trova_prenotazioni` | lettura | - |
| `crea_prenotazione` | scrittura | data, ora, coperti, nome_cliente, telefono |
| `modifica_prenotazione` | scrittura | id_prenotazione, telefono |
| `cancella_prenotazione` | scrittura distruttiva | id_prenotazione, telefono |
| `crea_ordine_asporto` | scrittura | nome_cliente, telefono, righe, ora_ritiro |
| `stato_ordine` | lettura | id_ordine, telefono |

## `orari_apertura`

Restituisce la data e l'ora attuali e gli orari di apertura del ristorante per ogni giorno della settimana.
Usare per domande sugli orari o per sapere che giorno è oggi.

**Effetti sui dati:** Sola lettura (`readOnlyHint: true`): nessun effetto sui dati, non richiede conferma.

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
    "id_articolo": 13
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

## `trova_prenotazioni`

Cerca le prenotazioni attive (da oggi in poi). Indicare almeno uno tra nome, telefono e data.

**Effetti sui dati:** Sola lettura (`readOnlyHint: true`): nessun effetto sui dati, non richiede conferma.

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
Controlla da sola la disponibilità: se il cliente ha già dato data, ora, persone, nome e telefono
si può chiamare direttamente. Richiede nome e telefono reali forniti dal cliente: non inventarli.

**Effetti sui dati:** **Scrittura** (`readOnlyHint: false`): modifica la base dati; l'harness chiede conferma all'utente.

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
      "description": "Nome e cognome del cliente.",
      "minLength": 1,
      "title": "Nome Cliente",
      "type": "string"
    },
    "telefono": {
      "description": "Telefono del cliente.",
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
      "default": null,
      "description": "Richieste particolari (es. seggiolone).",
      "title": "Note"
    }
  },
  "required": [
    "data",
    "ora",
    "coperti",
    "nome_cliente",
    "telefono"
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
      "description": "Telefono usato per la prenotazione (verifica dell'identità).",
      "title": "Telefono",
      "type": "string"
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
    "id_prenotazione",
    "telefono"
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
    "telefono": "3331234567",
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
      "description": "Telefono usato per la prenotazione (verifica dell'identità).",
      "title": "Telefono",
      "type": "string"
    }
  },
  "required": [
    "id_prenotazione",
    "telefono"
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
    "id_prenotazione": 86,
    "telefono": "3331234567"
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

## `crea_ordine_asporto`

Registra un ordine da asporto e scala le scorte degli ingredienti. SCRIVE sui dati.
Indicare i piatti per NOME (non serve cercare prima gli id). Fallisce, senza registrare nulla,
se un piatto non esiste o è ambiguo, non è da asporto, le scorte non bastano o l'orario non è valido.

**Effetti sui dati:** **Scrittura** (`readOnlyHint: false`): modifica la base dati; l'harness chiede conferma all'utente.

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
    "nome_cliente": {
      "description": "Nome del cliente.",
      "minLength": 1,
      "title": "Nome Cliente",
      "type": "string"
    },
    "telefono": {
      "description": "Telefono del cliente.",
      "title": "Telefono",
      "type": "string"
    },
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
    "nome_cliente",
    "telefono",
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
        "id_articolo": 10,
        "quantita": 2
      },
      {
        "id_articolo": 35,
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
      "description": "Telefono usato per l'ordine (verifica dell'identità).",
      "title": "Telefono",
      "type": "string"
    }
  },
  "required": [
    "id_ordine",
    "telefono"
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
    "id_ordine": 1,
    "telefono": "347 111 2233"
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
