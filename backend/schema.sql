-- Schema della base dati di "Osteria del Borgo" (ristorante fittizio).
-- Semplificazione dello schema di un gestionale per la ristorazione:
-- sala (tavoli, orari, prenotazioni), menu (categorie, piatti, allergeni, ricette)
-- e asporto (ordini, righe, scorte degli ingredienti).

PRAGMA foreign_keys = ON;

CREATE TABLE TAVOLI (
    id_tavolo   INTEGER PRIMARY KEY,
    nome        TEXT    NOT NULL UNIQUE,
    n_posti     INTEGER NOT NULL CHECK (n_posti > 0),
    sala        TEXT    NOT NULL
);

-- giorno_settimana: 0 = lunedì ... 6 = domenica (come datetime.weekday()).
-- Un giorno senza righe è un giorno di chiusura.
CREATE TABLE ORARI_APERTURA (
    giorno_settimana INTEGER NOT NULL CHECK (giorno_settimana BETWEEN 0 AND 6),
    turno            TEXT    NOT NULL CHECK (turno IN ('pranzo', 'cena')),
    apertura         TEXT    NOT NULL,   -- HH:MM
    chiusura         TEXT    NOT NULL,   -- HH:MM
    PRIMARY KEY (giorno_settimana, turno)
);

CREATE TABLE PRENOTAZIONI (
    id_prenotazione INTEGER PRIMARY KEY,
    data            TEXT    NOT NULL,    -- YYYY-MM-DD
    ora             TEXT    NOT NULL,    -- HH:MM
    coperti         INTEGER NOT NULL CHECK (coperti > 0),
    nome_cliente    TEXT    NOT NULL,
    telefono        TEXT    NOT NULL,
    note            TEXT,
    stato           TEXT    NOT NULL DEFAULT 'confermata'
                    CHECK (stato IN ('confermata', 'cancellata', 'completata')),
    id_tavolo       INTEGER NOT NULL REFERENCES TAVOLI(id_tavolo),
    fonte           TEXT    NOT NULL DEFAULT 'telefono'
                    CHECK (fonte IN ('telefono', 'sito', 'agente')),
    creata_il       TEXT    NOT NULL,    -- ISO 8601
    modificata_il   TEXT
);
CREATE INDEX idx_prenotazioni_data ON PRENOTAZIONI(data, stato);
CREATE INDEX idx_prenotazioni_telefono ON PRENOTAZIONI(telefono);

CREATE TABLE CATEGORIE (
    id_categoria INTEGER PRIMARY KEY,
    nome         TEXT    NOT NULL UNIQUE,
    ordine       INTEGER NOT NULL
);

CREATE TABLE ARTICOLI (
    id_articolo        INTEGER PRIMARY KEY,
    nome               TEXT    NOT NULL UNIQUE,
    descrizione        TEXT    NOT NULL,
    prezzo             REAL    NOT NULL CHECK (prezzo >= 0),
    id_categoria       INTEGER NOT NULL REFERENCES CATEGORIE(id_categoria),
    vegetariano        INTEGER NOT NULL DEFAULT 0 CHECK (vegetariano IN (0, 1)),
    disponibile_asporto INTEGER NOT NULL DEFAULT 1 CHECK (disponibile_asporto IN (0, 1)),
    attivo             INTEGER NOT NULL DEFAULT 1 CHECK (attivo IN (0, 1))
);

-- I 14 allergeni del Reg. UE 1169/2011.
CREATE TABLE ALLERGENI (
    id_allergene INTEGER PRIMARY KEY,
    codice       TEXT NOT NULL UNIQUE,   -- es. 'glutine', 'latte'
    nome         TEXT NOT NULL
);

CREATE TABLE ARTICOLI_ALLERGENI (
    id_articolo  INTEGER NOT NULL REFERENCES ARTICOLI(id_articolo),
    id_allergene INTEGER NOT NULL REFERENCES ALLERGENI(id_allergene),
    PRIMARY KEY (id_articolo, id_allergene)
);

CREATE TABLE INGREDIENTI (
    id_ingrediente       INTEGER PRIMARY KEY,
    nome                 TEXT NOT NULL UNIQUE,
    unita_misura         TEXT NOT NULL CHECK (unita_misura IN ('g', 'ml', 'pz')),
    quantita_disponibile REAL NOT NULL CHECK (quantita_disponibile >= 0),
    scorta_minima        REAL NOT NULL DEFAULT 0
);

-- Ricetta: quantità di ingrediente per una porzione del piatto.
CREATE TABLE ARTICOLI_INGREDIENTI (
    id_articolo    INTEGER NOT NULL REFERENCES ARTICOLI(id_articolo),
    id_ingrediente INTEGER NOT NULL REFERENCES INGREDIENTI(id_ingrediente),
    quantita       REAL    NOT NULL CHECK (quantita > 0),
    PRIMARY KEY (id_articolo, id_ingrediente)
);

CREATE TABLE ORDINI (
    id_ordine     INTEGER PRIMARY KEY,
    nome_cliente  TEXT NOT NULL,
    telefono      TEXT NOT NULL,
    tipo_servizio TEXT NOT NULL DEFAULT 'asporto' CHECK (tipo_servizio IN ('asporto')),
    data_ritiro   TEXT NOT NULL,   -- YYYY-MM-DD
    ora_ritiro    TEXT NOT NULL,   -- HH:MM
    stato         TEXT NOT NULL DEFAULT 'ricevuto'
                  CHECK (stato IN ('ricevuto', 'in_preparazione', 'pronto', 'ritirato', 'annullato')),
    totale        REAL NOT NULL CHECK (totale >= 0),
    note          TEXT,
    fonte         TEXT NOT NULL DEFAULT 'telefono' CHECK (fonte IN ('telefono', 'sito', 'agente')),
    creato_il     TEXT NOT NULL
);

CREATE TABLE ORDINI_RIGHE (
    id_riga         INTEGER PRIMARY KEY,
    id_ordine       INTEGER NOT NULL REFERENCES ORDINI(id_ordine),
    id_articolo     INTEGER NOT NULL REFERENCES ARTICOLI(id_articolo),
    quantita        INTEGER NOT NULL CHECK (quantita > 0),
    prezzo_unitario REAL    NOT NULL,
    note            TEXT
);
