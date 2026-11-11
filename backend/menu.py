"""Servizio menu: ricerca dei piatti, allergeni e disponibilità in base alle scorte."""

from __future__ import annotations

import math
import sqlite3
import unicodedata
from typing import Any

from backend.errori import ErroreDominio

# Sinonimi che un cliente può usare per indicare un allergene.
SINONIMI_ALLERGENI = {
    "gluten": "glutine",
    "frumento": "glutine",
    "celiaco": "glutine",
    "celiachia": "glutine",
    "lattosio": "latte",
    "latticini": "latte",
    "formaggio": "latte",
    "uovo": "uova",
    "frutta secca": "frutta_a_guscio",
    "frutta a guscio": "frutta_a_guscio",
    "noci": "frutta_a_guscio",
    "nocciole": "frutta_a_guscio",
    "mandorle": "frutta_a_guscio",
    "arachide": "arachidi",
    "crostaceo": "crostacei",
    "gamberi": "crostacei",
    "mollusco": "molluschi",
    "cozze": "molluschi",
    "vongole": "molluschi",
    "solfito": "solfiti",
    "anidride solforosa": "solfiti",
    "lupino": "lupini",
    "soya": "soia",
}


def _norm(testo: str) -> str:
    testo = unicodedata.normalize("NFKD", testo.strip().lower())
    return "".join(c for c in testo if not unicodedata.combining(c))


def codici_allergeni(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT codice FROM ALLERGENI ORDER BY codice")]


def risolvi_allergeni(conn: sqlite3.Connection, richiesti: list[str]) -> list[str]:
    validi = set(codici_allergeni(conn))
    risolti, sconosciuti = [], []
    for voce in richiesti:
        chiave = _norm(voce).replace("-", " ")
        codice = SINONIMI_ALLERGENI.get(chiave, chiave.replace(" ", "_"))
        if codice in validi:
            risolti.append(codice)
        else:
            sconosciuti.append(voce)
    if sconosciuti:
        raise ErroreDominio(
            "ALLERGENE_SCONOSCIUTO",
            f"Allergeni non riconosciuti: {', '.join(sconosciuti)}.",
            {"allergeni_validi": sorted(validi)},
        )
    return risolti


def categorie(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT nome FROM CATEGORIE ORDER BY ordine")]


def porzioni_disponibili(conn: sqlite3.Connection, id_articolo: int) -> int:
    """Numero massimo di porzioni preparabili con le scorte attuali."""
    righe = conn.execute(
        """SELECT ai.quantita AS q, i.quantita_disponibile AS disp
           FROM ARTICOLI_INGREDIENTI ai JOIN INGREDIENTI i ON i.id_ingrediente = ai.id_ingrediente
           WHERE ai.id_articolo = ?""",
        (id_articolo,),
    ).fetchall()
    if not righe:
        return 99
    return min(99, min(math.floor(r["disp"] / r["q"]) for r in righe))


def _allergeni_di(conn: sqlite3.Connection, id_articolo: int) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            """SELECT a.codice FROM ARTICOLI_ALLERGENI aa JOIN ALLERGENI a ON a.id_allergene = aa.id_allergene
               WHERE aa.id_articolo = ? ORDER BY a.codice""",
            (id_articolo,),
        )
    ]


def cerca_menu(
    conn: sqlite3.Connection,
    testo: str | None = None,
    categoria: str | None = None,
    escludi_allergeni: list[str] | None = None,
    solo_vegetariani: bool = False,
    solo_asporto: bool = False,
) -> dict[str, Any]:
    condizioni, parametri = ["a.attivo = 1"], []
    if categoria:
        trovata = next((c for c in categorie(conn) if _norm(c) == _norm(categoria)), None)
        if trovata is None:
            raise ErroreDominio(
                "CATEGORIA_SCONOSCIUTA",
                f"La categoria '{categoria}' non esiste.",
                {"categorie_valide": categorie(conn)},
            )
        condizioni.append("c.nome = ?")
        parametri.append(trovata)
    if testo:
        condizioni.append("(a.nome LIKE ? OR a.descrizione LIKE ?)")
        parametri += [f"%{testo.strip()}%"] * 2
    if solo_vegetariani:
        condizioni.append("a.vegetariano = 1")
    if solo_asporto:
        condizioni.append("a.disponibile_asporto = 1")
    da_escludere = set(risolvi_allergeni(conn, escludi_allergeni or []))

    righe = conn.execute(
        f"""SELECT a.id_articolo, a.nome, a.prezzo, a.vegetariano, a.disponibile_asporto, c.nome AS categoria
            FROM ARTICOLI a JOIN CATEGORIE c ON c.id_categoria = a.id_categoria
            WHERE {' AND '.join(condizioni)} ORDER BY c.ordine, a.nome""",
        parametri,
    ).fetchall()
    piatti = []
    for r in righe:
        allergeni = _allergeni_di(conn, r["id_articolo"])
        if da_escludere.intersection(allergeni):
            continue
        piatti.append(
            {
                "id_articolo": r["id_articolo"],
                "nome": r["nome"],
                "categoria": r["categoria"],
                "prezzo": r["prezzo"],
                "allergeni": allergeni,
                "vegetariano": bool(r["vegetariano"]),
                "asporto": bool(r["disponibile_asporto"]),
                "esaurito": porzioni_disponibili(conn, r["id_articolo"]) == 0,
            }
        )
    return {"numero_risultati": len(piatti), "piatti": piatti}


def dettaglio_piatto(conn: sqlite3.Connection, id_articolo: int) -> dict[str, Any]:
    r = conn.execute(
        """SELECT a.*, c.nome AS categoria FROM ARTICOLI a JOIN CATEGORIE c ON c.id_categoria = a.id_categoria
           WHERE a.id_articolo = ? AND a.attivo = 1""",
        (id_articolo,),
    ).fetchone()
    if r is None:
        raise ErroreDominio("PIATTO_INESISTENTE", f"Non esiste nessun piatto con id {id_articolo}.")
    ingredienti = [
        x[0]
        for x in conn.execute(
            """SELECT i.nome FROM ARTICOLI_INGREDIENTI ai JOIN INGREDIENTI i ON i.id_ingrediente = ai.id_ingrediente
               WHERE ai.id_articolo = ? ORDER BY ai.quantita DESC""",
            (id_articolo,),
        )
    ]
    return {
        "id_articolo": r["id_articolo"],
        "nome": r["nome"],
        "categoria": r["categoria"],
        "descrizione": r["descrizione"],
        "prezzo": r["prezzo"],
        "ingredienti": ingredienti,
        "allergeni": _allergeni_di(conn, id_articolo),
        "vegetariano": bool(r["vegetariano"]),
        "asporto": bool(r["disponibile_asporto"]),
        "porzioni_disponibili": porzioni_disponibili(conn, id_articolo),
    }
