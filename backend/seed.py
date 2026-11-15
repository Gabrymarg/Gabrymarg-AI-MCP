"""Crea e popola la base dati con dati sintetici realistici.

Uso:  python -m backend.seed [--db percorso] [--seed 42]

Il seed è riproducibile: stessi parametri + stesso RISTO_ADESSO = stesso database.
Nessun dato personale reale: nomi e telefoni sono generati con Faker (it_IT).

Oltre ai dati casuali, inserisce alcuni dati "di riferimento" usati dagli scenari di test
(vedi DATI_RIFERIMENTO): una serata al completo, un piatto esaurito, un ingrediente
in esaurimento, una prenotazione e un ordine con dati noti.
"""

from __future__ import annotations

import argparse
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

from faker import Faker

from backend import clock, ordini, permessi, prenotazioni, utenti
from backend.db import connetti, crea_schema, percorso_db
from backend.errori import ErroreDominio

ALLERGENI = [
    ("glutine", "Cereali contenenti glutine"),
    ("crostacei", "Crostacei e prodotti derivati"),
    ("uova", "Uova e prodotti derivati"),
    ("pesce", "Pesce e prodotti derivati"),
    ("arachidi", "Arachidi e prodotti derivati"),
    ("soia", "Soia e prodotti derivati"),
    ("latte", "Latte e prodotti derivati (incluso lattosio)"),
    ("frutta_a_guscio", "Frutta a guscio"),
    ("sedano", "Sedano e prodotti derivati"),
    ("senape", "Senape e prodotti derivati"),
    ("sesamo", "Semi di sesamo e prodotti derivati"),
    ("solfiti", "Anidride solforosa e solfiti"),
    ("lupini", "Lupini e prodotti derivati"),
    ("molluschi", "Molluschi e prodotti derivati"),
]

CATEGORIE = ["Antipasti", "Primi", "Secondi", "Contorni", "Dolci", "Bevande"]

# nome: (unità, quantità disponibile, scorta minima)
INGREDIENTI = {
    "farina 00": ("g", 20000, 3000), "pasta di semola": ("g", 15000, 3000), "uova": ("pz", 240, 40),
    "latte": ("ml", 10000, 2000), "burro": ("g", 4000, 800), "parmigiano": ("g", 6000, 1000),
    "pecorino": ("g", 4000, 800), "mozzarella": ("g", 6000, 1000), "pomodoro pelato": ("g", 15000, 3000),
    "basilico": ("g", 500, 100), "olio extravergine": ("ml", 12000, 2000), "aglio": ("g", 1000, 200),
    "guanciale": ("g", 3000, 600), "pepe nero": ("g", 500, 100), "funghi porcini": ("g", 2000, 400),
    "riso carnaroli": ("g", 8000, 1500), "zafferano": ("g", 50, 10), "tartufo nero": ("g", 25, 50),
    "branzino": ("pz", 0, 6), "salmone": ("g", 3000, 600), "gamberi": ("g", 2500, 500),
    "calamari": ("g", 3000, 600), "cozze": ("g", 4000, 800), "vongole": ("g", 3000, 600),
    "acciughe": ("g", 800, 200), "manzo": ("g", 9000, 2000), "pollo": ("g", 5000, 1000),
    "vitello": ("g", 4000, 800), "tofu": ("g", 2000, 400), "salsa di soia": ("ml", 500, 100),
    "patate": ("g", 12000, 2000), "zucchine": ("g", 4000, 800), "melanzane": ("g", 5000, 1000),
    "peperoni": ("g", 3000, 600), "insalata": ("g", 2500, 500), "spinaci": ("g", 3000, 600),
    "carote": ("g", 3000, 600), "cipolla": ("g", 4000, 800), "sedano": ("g", 1000, 200),
    "ceci": ("g", 3000, 600), "lupini": ("g", 800, 200), "pane": ("g", 6000, 1000),
    "prosciutto crudo": ("g", 3000, 600), "salame": ("g", 2000, 400), "ricotta": ("g", 3000, 600),
    "mascarpone": ("g", 3000, 600), "savoiardi": ("pz", 300, 60), "caffè": ("ml", 3000, 500),
    "cacao": ("g", 1000, 200), "cioccolato fondente": ("g", 2000, 400), "panna": ("ml", 5000, 1000),
    "frutti di bosco": ("g", 1500, 300), "nocciole": ("g", 1500, 300), "pistacchi": ("g", 800, 200),
    "arachidi": ("g", 800, 200), "zucchero": ("g", 5000, 1000), "limone": ("pz", 100, 20),
    "senape": ("g", 300, 50), "sesamo": ("g", 300, 50), "vino bianco": ("ml", 6000, 1000),
    "vino rosso (bottiglia)": ("pz", 60, 12), "birra artigianale": ("pz", 120, 24),
    "acqua minerale": ("pz", 200, 48),
}

# (nome, categoria, prezzo, descrizione, vegetariano, asporto, allergeni, ricetta {ingrediente: quantità})
PIATTI = [
    ("Tagliere dell'Osteria", "Antipasti", 14.0, "Prosciutto crudo, salame nostrano e pecorino con pane casereccio.",
     0, 1, ["glutine", "latte"], {"prosciutto crudo": 60, "salame": 50, "pecorino": 40, "pane": 50}),
    ("Bruschette al pomodoro", "Antipasti", 6.0, "Pane tostato con pomodoro, aglio, basilico e olio extravergine.",
     1, 1, ["glutine"], {"pane": 80, "pomodoro pelato": 80, "basilico": 3, "aglio": 3, "olio extravergine": 10}),
    ("Caprese", "Antipasti", 9.0, "Mozzarella fiordilatte, pomodoro e basilico.",
     1, 1, ["latte"], {"mozzarella": 125, "pomodoro pelato": 120, "basilico": 3, "olio extravergine": 10}),
    ("Sauté di cozze e vongole", "Antipasti", 13.0, "Cozze e vongole saltate con aglio, vino bianco e crostini.",
     0, 0, ["molluschi", "glutine", "solfiti"], {"cozze": 250, "vongole": 150, "aglio": 5, "vino bianco": 30, "pane": 40}),
    ("Flan di spinaci su crema di parmigiano", "Antipasti", 9.0, "Sformatino di spinaci con fonduta di parmigiano.",
     1, 1, ["uova", "latte"], {"spinaci": 100, "uova": 1, "panna": 50, "parmigiano": 30}),
    ("Hummus di ceci al sesamo", "Antipasti", 8.0, "Crema di ceci con tahina, limone e pane croccante.",
     1, 1, ["sesamo", "glutine"], {"ceci": 120, "sesamo": 15, "limone": 0.25, "olio extravergine": 10, "pane": 40}),
    ("Alici marinate", "Antipasti", 10.0, "Alici fresche marinate al limone.",
     0, 1, ["pesce"], {"acciughe": 100, "limone": 0.5, "olio extravergine": 10}),
    ("Carpaccio di salmone", "Antipasti", 12.0, "Salmone affumicato con citronette alla senape.",
     0, 1, ["pesce", "senape"], {"salmone": 100, "limone": 0.5, "olio extravergine": 10, "senape": 5}),
    ("Lupini e olive marinate", "Antipasti", 4.0, "Lupini e olive marinate alle erbe.",
     1, 1, ["lupini"], {"lupini": 80, "olio extravergine": 5}),
    ("Spaghetti alla carbonara", "Primi", 12.0, "Guanciale croccante, tuorlo d'uovo, pecorino romano e pepe.",
     0, 1, ["glutine", "uova", "latte"], {"pasta di semola": 100, "guanciale": 50, "uova": 1, "pecorino": 25, "pepe nero": 1}),
    ("Bucatini all'amatriciana", "Primi", 12.0, "Guanciale, pomodoro e pecorino romano.",
     0, 1, ["glutine", "latte"], {"pasta di semola": 100, "guanciale": 50, "pomodoro pelato": 100, "pecorino": 20}),
    ("Tonnarelli cacio e pepe", "Primi", 11.0, "Pecorino romano e pepe nero macinato al momento.",
     1, 1, ["glutine", "latte"], {"pasta di semola": 100, "pecorino": 50, "pepe nero": 2}),
    ("Tagliolini al tartufo nero", "Primi", 22.0, "Pasta fresca all'uovo, burro, parmigiano e tartufo nero.",
     1, 1, ["glutine", "uova", "latte"], {"farina 00": 80, "uova": 1, "burro": 20, "parmigiano": 15, "tartufo nero": 10}),
    ("Risotto ai funghi porcini", "Primi", 15.0, "Riso carnaroli mantecato con porcini.",
     1, 0, ["latte", "solfiti"], {"riso carnaroli": 90, "funghi porcini": 80, "burro": 15, "parmigiano": 20, "vino bianco": 20, "cipolla": 20}),
    ("Risotto alla milanese", "Primi", 13.0, "Riso carnaroli allo zafferano.",
     1, 0, ["latte", "solfiti"], {"riso carnaroli": 90, "zafferano": 0.2, "burro": 20, "parmigiano": 20, "cipolla": 20, "vino bianco": 20}),
    ("Spaghetti alle vongole", "Primi", 15.0, "Vongole veraci, aglio, prezzemolo e vino bianco.",
     0, 1, ["glutine", "molluschi", "solfiti"], {"pasta di semola": 100, "vongole": 200, "aglio": 5, "vino bianco": 20, "olio extravergine": 15}),
    ("Linguine gamberi e zucchine", "Primi", 16.0, "Gamberi, zucchine e un tocco di limone.",
     0, 1, ["glutine", "crostacei"], {"pasta di semola": 100, "gamberi": 100, "zucchine": 80, "aglio": 3}),
    ("Lasagne alla bolognese", "Primi", 13.0, "Sfoglia all'uovo, ragù di manzo e besciamella.",
     0, 1, ["glutine", "uova", "latte", "sedano"],
     {"farina 00": 60, "uova": 1, "manzo": 80, "pomodoro pelato": 80, "latte": 80, "burro": 15, "parmigiano": 20, "sedano": 10, "carote": 10, "cipolla": 10}),
    ("Gnocchi al pomodoro e basilico", "Primi", 10.0, "Gnocchi di patate fatti in casa.",
     1, 1, ["glutine"], {"patate": 200, "farina 00": 50, "pomodoro pelato": 100, "basilico": 3}),
    ("Pasta e ceci", "Primi", 10.0, "Minestra cremosa di ceci con pasta corta.",
     1, 1, ["glutine", "sedano"], {"pasta di semola": 70, "ceci": 100, "sedano": 10, "carote": 10, "cipolla": 10, "olio extravergine": 10}),
    ("Ravioli ricotta e spinaci", "Primi", 13.0, "Ravioli fatti a mano con burro e salvia.",
     1, 1, ["glutine", "uova", "latte"], {"farina 00": 80, "uova": 1, "ricotta": 60, "spinaci": 50, "burro": 20, "parmigiano": 15}),
    ("Tagliata di manzo con rucola", "Secondi", 22.0, "Controfiletto alla griglia con rucola e scaglie di parmigiano.",
     0, 1, ["latte"], {"manzo": 250, "insalata": 40, "parmigiano": 15, "olio extravergine": 10}),
    ("Branzino al forno con patate", "Secondi", 20.0, "Branzino intero al forno con patate e limone.",
     0, 0, ["pesce"], {"branzino": 1, "patate": 150, "olio extravergine": 15, "limone": 0.5}),
    ("Pollo alla cacciatora", "Secondi", 15.0, "Pollo stufato con pomodoro, cipolla e vino bianco.",
     0, 1, ["solfiti"], {"pollo": 300, "pomodoro pelato": 100, "cipolla": 30, "vino bianco": 30}),
    ("Saltimbocca alla romana", "Secondi", 17.0, "Fettine di vitello con prosciutto crudo e salvia.",
     0, 1, ["latte", "glutine", "solfiti"], {"vitello": 180, "prosciutto crudo": 30, "burro": 20, "vino bianco": 30, "farina 00": 10}),
    ("Frittura di calamari e gamberi", "Secondi", 18.0, "Frittura leggera di calamari e gamberi.",
     0, 0, ["molluschi", "crostacei", "glutine"], {"calamari": 150, "gamberi": 100, "farina 00": 40}),
    ("Salmone in crosta di pistacchi", "Secondi", 19.0, "Trancio di salmone in crosta di pistacchi e pane.",
     0, 1, ["pesce", "frutta_a_guscio", "glutine"], {"salmone": 180, "pistacchi": 25, "pane": 15}),
    ("Parmigiana di melanzane", "Secondi", 13.0, "Melanzane fritte, pomodoro, mozzarella e parmigiano.",
     1, 1, ["latte", "glutine", "uova"],
     {"melanzane": 250, "pomodoro pelato": 120, "mozzarella": 80, "parmigiano": 25, "basilico": 3, "farina 00": 20, "uova": 1}),
    ("Polpette al sugo", "Secondi", 14.0, "Polpette di manzo al sugo di pomodoro.",
     0, 1, ["glutine", "uova", "latte"], {"manzo": 180, "pane": 30, "uova": 1, "parmigiano": 15, "pomodoro pelato": 120}),
    ("Tofu grigliato con verdure", "Secondi", 14.0, "Tofu marinato alla soia con verdure di stagione (piatto vegano).",
     1, 1, ["soia"], {"tofu": 150, "salsa di soia": 15, "zucchine": 80, "peperoni": 80}),
    ("Patate al forno", "Contorni", 5.0, "Patate al forno con rosmarino.",
     1, 1, [], {"patate": 200, "olio extravergine": 10}),
    ("Verdure grigliate", "Contorni", 6.0, "Zucchine, melanzane e peperoni alla griglia.",
     1, 1, [], {"zucchine": 80, "melanzane": 80, "peperoni": 80, "olio extravergine": 10}),
    ("Insalata mista", "Contorni", 5.0, "Insalata, carote e pomodoro.",
     1, 1, [], {"insalata": 80, "carote": 30, "pomodoro pelato": 40, "olio extravergine": 10}),
    ("Spinaci saltati", "Contorni", 5.0, "Spinaci saltati in padella con aglio.",
     1, 1, [], {"spinaci": 150, "aglio": 3, "olio extravergine": 10}),
    ("Tiramisù", "Dolci", 7.0, "Savoiardi, caffè, crema al mascarpone e cacao.",
     1, 1, ["latte", "uova", "glutine"], {"mascarpone": 80, "uova": 1, "savoiardi": 4, "caffè": 40, "cacao": 3, "zucchero": 20}),
    ("Panna cotta ai frutti di bosco", "Dolci", 6.0, "Panna cotta con coulis di frutti di bosco.",
     1, 1, ["latte"], {"panna": 120, "latte": 20, "frutti di bosco": 30, "zucchero": 20}),
    ("Torta al cioccolato senza glutine", "Dolci", 7.0, "Torta morbida al cioccolato fondente, senza farina.",
     1, 1, ["latte", "uova"], {"cioccolato fondente": 60, "burro": 30, "uova": 1, "cacao": 5, "zucchero": 30}),
    ("Cannolo siciliano", "Dolci", 6.0, "Cialda croccante con ricotta, gocce di cioccolato e pistacchi.",
     1, 1, ["latte", "glutine", "frutta_a_guscio"], {"ricotta": 80, "farina 00": 30, "pistacchi": 10, "cioccolato fondente": 10, "zucchero": 20}),
    ("Semifreddo alla nocciola", "Dolci", 7.0, "Semifreddo con granella di nocciole tostate.",
     1, 1, ["frutta_a_guscio", "uova", "latte"], {"panna": 80, "nocciole": 30, "uova": 1, "zucchero": 25}),
    ("Croccante di arachidi", "Dolci", 5.0, "Croccante artigianale di arachidi e zucchero caramellato.",
     1, 1, ["arachidi"], {"arachidi": 40, "zucchero": 40}),
    ("Sorbetto al limone", "Dolci", 4.0, "Sorbetto al limone (vegano).",
     1, 0, [], {"limone": 1, "zucchero": 40}),
    ("Acqua minerale 75cl", "Bevande", 2.5, "Naturale o frizzante.",
     1, 1, [], {"acqua minerale": 1}),
    ("Vino rosso della casa (bottiglia)", "Bevande", 18.0, "Rosso di produzione locale, 75cl.",
     1, 1, ["solfiti"], {"vino rosso (bottiglia)": 1}),
    ("Calice di vino bianco", "Bevande", 5.0, "Bianco della casa al calice.",
     1, 0, ["solfiti"], {"vino bianco": 150}),
    ("Birra artigianale 33cl", "Bevande", 5.0, "Birra chiara artigianale.",
     1, 1, ["glutine"], {"birra artigianale": 1}),
]

# (nome, posti, sala)
TAVOLI = (
    [(f"T{i}", 2, "Sala interna") for i in range(1, 7)]
    + [(f"T{i}", 4, "Sala interna") for i in range(7, 11)]
    + [(f"V{i}", 4, "Veranda") for i in range(1, 3)]
    + [("V3", 6, "Veranda"), ("V4", 6, "Veranda"), ("S1", 10, "Saletta privata")]
)

# Lunedì chiuso; da martedì a domenica pranzo e cena.
ORARI = [(g, "pranzo", "12:00", "15:00") for g in range(1, 7)] + [(g, "cena", "19:00", "23:30") for g in range(1, 7)]

# Utenti dimostrativi della web app (credenziali di prova, solo per l'ambiente locale).
# (username, password, ruolo, nome, telefono)
UTENTI_DEMO = [
    ("admin", "Admin-Borgo-2026", "admin", "Amministratore", None),
    ("sala", "Sala-Borgo-2026", "sala", "Marta (sala)", None),
    ("cucina", "Cucina-Borgo-2026", "cucina", "Chef Paolo", None),
    ("giulia", "Giulia-Borgo-2026", "cliente", "Giulia Ferri", "3331234567"),
    ("luca", "Luca-Borgo-2026", "cliente", "Luca Bianchi", "3471112233"),
]

# Dati noti usati dagli scenari di test.
DATI_RIFERIMENTO = {
    "cliente_prenotazione": {"nome": "Giulia Ferri", "telefono": "3331234567"},
    "cliente_ordine": {"nome": "Luca Bianchi", "telefono": "3471112233"},
    "serata_completa_ora": "20:00",
}


def prossimo_giorno(da: date, weekday: int, minimo_giorni: int = 1) -> date:
    d = da + timedelta(days=minimo_giorni)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


def popola(conn, seme: int = 42) -> dict:
    rnd = random.Random(seme)
    fake = Faker("it_IT")
    Faker.seed(seme)
    oggi = clock.adesso().date()

    conn.executemany("INSERT INTO ALLERGENI (codice, nome) VALUES (?, ?)", ALLERGENI)
    conn.executemany(
        "INSERT INTO CATEGORIE (nome, ordine) VALUES (?, ?)", [(c, i) for i, c in enumerate(CATEGORIE, 1)]
    )
    conn.executemany(
        "INSERT INTO INGREDIENTI (nome, unita_misura, quantita_disponibile, scorta_minima) VALUES (?, ?, ?, ?)",
        [(n, u, q, m) for n, (u, q, m) in INGREDIENTI.items()],
    )
    conn.executemany("INSERT INTO TAVOLI (nome, n_posti, sala) VALUES (?, ?, ?)", TAVOLI)
    conn.executemany(
        "INSERT INTO ORARI_APERTURA (giorno_settimana, turno, apertura, chiusura) VALUES (?, ?, ?, ?)", ORARI
    )

    id_cat = {r["nome"]: r["id_categoria"] for r in conn.execute("SELECT * FROM CATEGORIE")}
    id_all = {r["codice"]: r["id_allergene"] for r in conn.execute("SELECT * FROM ALLERGENI")}
    id_ing = {r["nome"]: r["id_ingrediente"] for r in conn.execute("SELECT * FROM INGREDIENTI")}
    for nome, cat, prezzo, descr, veg, asporto, allergeni, ricetta in PIATTI:
        cur = conn.execute(
            """INSERT INTO ARTICOLI (nome, descrizione, prezzo, id_categoria, vegetariano, disponibile_asporto)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (nome, descr, prezzo, id_cat[cat], veg, asporto),
        )
        conn.executemany(
            "INSERT INTO ARTICOLI_ALLERGENI VALUES (?, ?)", [(cur.lastrowid, id_all[a]) for a in allergeni]
        )
        conn.executemany(
            "INSERT INTO ARTICOLI_INGREDIENTI VALUES (?, ?, ?)",
            [(cur.lastrowid, id_ing[i], q) for i, q in ricetta.items()],
        )

    def telefono() -> str:
        return "3" + "".join(str(rnd.randint(0, 9)) for _ in range(9))

    # Storico: prenotazioni completate negli ultimi 14 giorni (inserite direttamente).
    n_tavoli = len(TAVOLI)
    for delta in range(14, 0, -1):
        giorno = oggi - timedelta(days=delta)
        if giorno.weekday() == 0:
            continue
        for _ in range(rnd.randint(3, 8)):
            conn.execute(
                """INSERT INTO PRENOTAZIONI (data, ora, coperti, nome_cliente, telefono, stato, id_tavolo, fonte, creata_il)
                   VALUES (?, ?, ?, ?, ?, 'completata', ?, ?, ?)""",
                (
                    giorno.isoformat(),
                    rnd.choice(["12:30", "13:00", "20:00", "20:30", "21:00"]),
                    rnd.randint(2, 4),
                    fake.name(),
                    telefono(),
                    rnd.randint(1, n_tavoli),
                    rnd.choice(["telefono", "sito"]),
                    (datetime.combine(giorno, time(10)) - timedelta(days=2)).isoformat(timespec="minutes"),
                ),
            )

    # Serata al completo: il prossimo sabato tutti i tavoli sono prenotati alle 20:00.
    sabato = prossimo_giorno(oggi, 5)
    for nome, posti, _ in TAVOLI:
        prenotazioni.crea_prenotazione(
            conn, sabato.isoformat(), DATI_RIFERIMENTO["serata_completa_ora"], posti,
            fake.name(), telefono(), fonte="telefono",
        )

    # Prenotazione di riferimento (modifica / cancellazione negli scenari).
    rif = DATI_RIFERIMENTO["cliente_prenotazione"]
    giorno_rif = prossimo_giorno(oggi, 4, minimo_giorni=2)  # un venerdì
    pren_rif = prenotazioni.crea_prenotazione(
        conn, giorno_rif.isoformat(), "20:30", 2, rif["nome"], rif["telefono"],
        note="Anniversario", fonte="sito",
    )

    # Prenotazioni future casuali (solo dove c'è posto).
    for delta in range(1, 31):
        giorno = oggi + timedelta(days=delta)
        if giorno.weekday() == 0 or giorno == sabato:
            continue
        for _ in range(rnd.randint(2, 7)):
            try:
                prenotazioni.crea_prenotazione(
                    conn,
                    giorno.isoformat(),
                    rnd.choice(["12:30", "13:00", "13:30", "19:30", "20:00", "20:30", "21:00", "21:30"]),
                    rnd.choice([2, 2, 2, 3, 4, 4, 5, 6]),
                    fake.name(),
                    telefono(),
                    note=rnd.choice([None, None, None, "Seggiolone", "Tavolo all'aperto se possibile", "Compleanno"]),
                    fonte=rnd.choice(["telefono", "sito"]),
                )
            except ErroreDominio:
                pass

    # Ordine di riferimento: oggi, in preparazione (se il ristorante oggi è aperto).
    ord_rif = None
    cli = DATI_RIFERIMENTO["cliente_ordine"]
    piatti = {r["nome"]: r["id_articolo"] for r in conn.execute("SELECT id_articolo, nome FROM ARTICOLI")}
    giorno_ord = oggi if oggi.weekday() != 0 else oggi + timedelta(days=1)
    try:
        ord_rif = ordini.crea_ordine_asporto(
            conn, cli["nome"], cli["telefono"],
            [{"id_articolo": piatti["Lasagne alla bolognese"], "quantita": 2},
             {"id_articolo": piatti["Tiramisù"], "quantita": 2}],
            ora_ritiro="20:00", data_ritiro=giorno_ord.isoformat(), fonte="telefono",
        )
        conn.execute("UPDATE ORDINI SET stato = 'in_preparazione' WHERE id_ordine = ?", (ord_rif["id_ordine"],))
    except ErroreDominio:
        pass

    # Utenti della web app; i clienti diventano proprietari delle prenotazioni e degli ordini col loro telefono.
    for username, password, ruolo, nome, tel in UTENTI_DEMO:
        u = utenti.crea_utente(conn, username, password, ruolo, nome, tel)
        if tel:
            conn.execute("UPDATE PRENOTAZIONI SET id_utente = ? WHERE telefono = ?", (u["id_utente"], tel))
            conn.execute("UPDATE ORDINI SET id_utente = ? WHERE telefono = ?", (u["id_utente"], tel))

    return {
        "oggi": oggi.isoformat(),
        "sabato_completo": sabato.isoformat(),
        "prenotazione_riferimento": pren_rif["id_prenotazione"],
        "ordine_riferimento": ord_rif["id_ordine"] if ord_rif else None,
    }


def crea_database(percorso: Path, seme: int = 42) -> dict:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    if percorso.exists():
        percorso.unlink()
    conn = connetti(percorso)
    try:
        crea_schema(conn)
        info = popola(conn, seme)
        permessi.crea_tabelle(conn)  # permessi dei ruoli: valori predefiniti, modificabili dall'admin
        conn.commit()
    finally:
        conn.close()
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea il database con dati sintetici.")
    parser.add_argument("--db", type=Path, default=None, help="percorso del file SQLite")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    percorso = args.db or percorso_db()
    info = crea_database(percorso, args.seed)
    conn = connetti(percorso)
    print(f"Database creato: {percorso}")
    for tabella in ["TAVOLI", "ARTICOLI", "INGREDIENTI", "PRENOTAZIONI", "ORDINI"]:
        print(f"  {tabella:<13} {conn.execute(f'SELECT COUNT(*) FROM {tabella}').fetchone()[0]:>4} righe")
    conn.close()
    print("Dati di riferimento:", info)


if __name__ == "__main__":
    main()
