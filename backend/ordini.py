"""Servizio ordini da asporto.

Regole di business:
- il ritiro deve avvenire durante un turno di apertura, almeno PREAVVISO_MIN minuti
  da adesso e non oltre MARGINE_FINALE_MIN minuti prima della chiusura;
- si ordinano solo piatti attivi e disponibili per l'asporto;
- le scorte degli ingredienti devono bastare per tutto l'ordine: in tal caso
  l'ordine viene registrato e le scorte scalate nella stessa transazione.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from backend import clock
from backend.errori import ErroreDominio
from backend.menu import porzioni_disponibili, trova_piatto
from backend.orari import descrizione_orari, turni_del_giorno
from backend.validazione import (
    nome_cliente,
    normalizza_telefono,
    parse_data,
    parse_ora,
    stesso_telefono,
    testo_breve,
)

PREAVVISO_MIN = 20
MARGINE_FINALE_MIN = 30
MAX_QUANTITA_RIGA = 20


def _riepilogo(conn: sqlite3.Connection, id_ordine: int) -> dict[str, Any]:
    o = conn.execute("SELECT * FROM ORDINI WHERE id_ordine = ?", (id_ordine,)).fetchone()
    righe = conn.execute(
        """SELECT r.id_articolo, a.nome, r.quantita, r.prezzo_unitario, r.note
           FROM ORDINI_RIGHE r JOIN ARTICOLI a ON a.id_articolo = r.id_articolo
           WHERE r.id_ordine = ? ORDER BY r.id_riga""",
        (id_ordine,),
    ).fetchall()
    return {
        "id_ordine": o["id_ordine"],
        "nome_cliente": o["nome_cliente"],
        "data_ritiro": o["data_ritiro"],
        "ora_ritiro": o["ora_ritiro"],
        "stato": o["stato"],
        "totale": round(o["totale"], 2),
        "note": o["note"],
        "righe": [
            {
                "id_articolo": r["id_articolo"],
                "nome": r["nome"],
                "quantita": r["quantita"],
                "prezzo_unitario": r["prezzo_unitario"],
                "note": r["note"],
            }
            for r in righe
        ],
    }


def _verifica_ritiro(conn: sqlite3.Connection, giorno: date, ora) -> None:
    momento = datetime.combine(giorno, ora)
    minimo = clock.adesso() + timedelta(minutes=PREAVVISO_MIN)
    if momento < minimo:
        raise ErroreDominio(
            "RITIRO_TROPPO_PRESTO",
            f"Il ritiro deve essere almeno {PREAVVISO_MIN} minuti da adesso (non prima delle {minimo:%H:%M} "
            f"del {minimo.date().isoformat()}).",
        )
    if giorno > clock.adesso().date() + timedelta(days=7):
        raise ErroreDominio("TROPPO_IN_ANTICIPO", "Gli ordini da asporto si accettano al massimo 7 giorni prima.")
    if not any(t.contiene(ora, MARGINE_FINALE_MIN) for t in turni_del_giorno(conn, giorno)):
        raise ErroreDominio(
            "FUORI_ORARIO",
            f"Ritiro alle {ora:%H:%M} del {giorno.isoformat()} non possibile ({descrizione_orari(conn, giorno)}).",
            {"orari": descrizione_orari(conn, giorno)},
        )


def crea_ordine_asporto(
    conn: sqlite3.Connection,
    nome: str,
    telefono: str,
    righe: list[dict[str, Any]],
    ora_ritiro: str,
    data_ritiro: str | None = None,
    note: str | None = None,
    fonte: str = "agente",
) -> dict[str, Any]:
    nome = nome_cliente(nome)
    tel = normalizza_telefono(telefono)
    note = testo_breve(note, "note", 300)
    giorno = parse_data(data_ritiro) if data_ritiro else clock.adesso().date()
    ora = parse_ora(ora_ritiro)
    _verifica_ritiro(conn, giorno, ora)
    if not righe:
        raise ErroreDominio("ORDINE_VUOTO", "L'ordine deve contenere almeno un piatto.")

    # Accorpa righe dello stesso piatto e valida quantità.
    quantita: dict[int, int] = defaultdict(int)
    note_righe: dict[int, str | None] = {}
    for riga in righe:
        q = int(riga.get("quantita") or 1)
        if not 1 <= q <= MAX_QUANTITA_RIGA:
            raise ErroreDominio("QUANTITA_NON_VALIDA", f"Quantità {q} non valida (da 1 a {MAX_QUANTITA_RIGA}).")
        # Il nome prevale sull'id: un id indicato dal modello potrebbe essere inventato.
        if riga.get("nome"):
            id_articolo = trova_piatto(conn, riga["nome"])
        elif riga.get("id_articolo") is not None:
            id_articolo = int(riga["id_articolo"])
        else:
            raise ErroreDominio("PIATTO_MANCANTE", "Ogni riga dell'ordine deve indicare il nome del piatto.")
        quantita[id_articolo] += q
        note_righe[id_articolo] = testo_breve(riga.get("note"), "note riga", 120)

    articoli: dict[int, sqlite3.Row] = {}
    for id_articolo in quantita:
        a = conn.execute("SELECT * FROM ARTICOLI WHERE id_articolo = ? AND attivo = 1", (id_articolo,)).fetchone()
        if a is None:
            raise ErroreDominio("PIATTO_INESISTENTE", f"Non esiste nessun piatto con id {id_articolo}.")
        if not a["disponibile_asporto"]:
            raise ErroreDominio("NON_DISPONIBILE_ASPORTO", f"'{a['nome']}' non è disponibile per l'asporto.")
        articoli[id_articolo] = a

    # Fabbisogno complessivo di ogni ingrediente.
    fabbisogno: dict[int, float] = defaultdict(float)
    for id_articolo, q in quantita.items():
        for ri in conn.execute(
            "SELECT id_ingrediente, quantita FROM ARTICOLI_INGREDIENTI WHERE id_articolo = ?", (id_articolo,)
        ):
            fabbisogno[ri["id_ingrediente"]] += ri["quantita"] * q
    mancanti = []
    for id_ing, serve in fabbisogno.items():
        disp = conn.execute(
            "SELECT quantita_disponibile FROM INGREDIENTI WHERE id_ingrediente = ?", (id_ing,)
        ).fetchone()[0]
        if disp < serve:
            mancanti.append(id_ing)
    if mancanti:
        piatti_bloccati = sorted(
            {
                articoli[ida]["nome"]
                for ida in quantita
                for (ing,) in conn.execute(
                    "SELECT id_ingrediente FROM ARTICOLI_INGREDIENTI WHERE id_articolo = ?", (ida,)
                )
                if ing in mancanti
            }
        )
        raise ErroreDominio(
            "SCORTE_INSUFFICIENTI",
            "Scorte insufficienti per: " + ", ".join(piatti_bloccati) + ". L'ordine non è stato registrato.",
            {
                "porzioni_disponibili": {
                    articoli[ida]["nome"]: porzioni_disponibili(conn, ida)
                    for ida in quantita
                    if articoli[ida]["nome"] in piatti_bloccati
                }
            },
        )

    totale = sum(articoli[ida]["prezzo"] * q for ida, q in quantita.items())
    cur = conn.execute(
        """INSERT INTO ORDINI (nome_cliente, telefono, data_ritiro, ora_ritiro, stato, totale, note, fonte, creato_il)
           VALUES (?, ?, ?, ?, 'ricevuto', ?, ?, ?, ?)""",
        (
            nome,
            tel,
            giorno.isoformat(),
            f"{ora:%H:%M}",
            round(totale, 2),
            note,
            fonte,
            clock.adesso().isoformat(timespec="minutes"),
        ),
    )
    id_ordine = cur.lastrowid
    for ida, q in quantita.items():
        conn.execute(
            "INSERT INTO ORDINI_RIGHE (id_ordine, id_articolo, quantita, prezzo_unitario, note) VALUES (?, ?, ?, ?, ?)",
            (id_ordine, ida, q, articoli[ida]["prezzo"], note_righe.get(ida)),
        )
    for id_ing, serve in fabbisogno.items():
        conn.execute(
            "UPDATE INGREDIENTI SET quantita_disponibile = quantita_disponibile - ? WHERE id_ingrediente = ?",
            (serve, id_ing),
        )
    return _riepilogo(conn, id_ordine)


def stato_ordine(conn: sqlite3.Connection, id_ordine: int, telefono: str) -> dict[str, Any]:
    o = conn.execute("SELECT telefono FROM ORDINI WHERE id_ordine = ?", (id_ordine,)).fetchone()
    if o is None or not stesso_telefono(o["telefono"], telefono):
        raise ErroreDominio(
            "ORDINE_INESISTENTE", f"Non esiste nessun ordine numero {id_ordine} associato a questo telefono."
        )
    return _riepilogo(conn, id_ordine)
