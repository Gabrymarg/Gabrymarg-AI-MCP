"""Gestione delle anagrafiche del menu: categorie, ingredienti e articoli (piatti).

Servizi usati dal pannello di amministrazione della web app. Non sono esposti come tool MCP:
sono operazioni di configurazione, svolte con maschere tradizionali e non in linguaggio naturale.

Regole principali:
  - i nomi sono unici (senza distinzione tra maiuscole e minuscole);
  - una categoria si elimina solo se non contiene articoli;
  - un ingrediente si elimina solo se nessuna ricetta lo usa;
  - un articolo non si elimina mai (gli ordini passati lo citano): si toglie dal menu (attivo = 0);
  - gli allergeni di un piatto sono dichiarati esplicitamente, perché sono un'informazione di sicurezza
    alimentare che il ristoratore deve confermare, non dedurre.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.errori import ErroreDominio

UNITA = ("g", "ml", "pz")


def _testo(valore: str | None, campo: str, massimo: int) -> str:
    valore = (valore or "").strip()
    if not valore:
        raise ErroreDominio("CAMPO_OBBLIGATORIO", f"Il campo '{campo}' è obbligatorio.")
    if len(valore) > massimo:
        raise ErroreDominio("CAMPO_TROPPO_LUNGO", f"Il campo '{campo}' supera i {massimo} caratteri.")
    return valore


def _nome_libero(conn: sqlite3.Connection, tabella: str, chiave: str, nome: str, escludi: int | None = None) -> None:
    riga = conn.execute(
        f"SELECT {chiave} FROM {tabella} WHERE lower(nome) = lower(?)", (nome,)
    ).fetchone()
    if riga and riga[0] != escludi:
        raise ErroreDominio("NOME_GIA_USATO", f"Esiste già un elemento chiamato '{nome}'.")


def _esiste(conn: sqlite3.Connection, tabella: str, chiave: str, id_: int, etichetta: str) -> sqlite3.Row:
    riga = conn.execute(f"SELECT * FROM {tabella} WHERE {chiave} = ?", (id_,)).fetchone()
    if riga is None:
        raise ErroreDominio("NON_TROVATO", f"{etichetta} {id_} inesistente.")
    return riga


# ============================================================================ categorie


def elenco_categorie(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in conn.execute(
            """SELECT c.id_categoria, c.nome, c.ordine, COUNT(a.id_articolo) AS numero_articoli
               FROM CATEGORIE c LEFT JOIN ARTICOLI a ON a.id_categoria = c.id_categoria
               GROUP BY c.id_categoria ORDER BY c.ordine, c.nome"""
        )
    ]


def salva_categoria(
    conn: sqlite3.Connection, nome: str, ordine: int | None = None, id_categoria: int | None = None
) -> dict[str, Any]:
    nome = _testo(nome, "nome", 40)
    _nome_libero(conn, "CATEGORIE", "id_categoria", nome, id_categoria)
    if ordine is None:
        ordine = conn.execute("SELECT COALESCE(MAX(ordine), 0) + 1 FROM CATEGORIE").fetchone()[0]
    if id_categoria is None:
        id_categoria = conn.execute(
            "INSERT INTO CATEGORIE (nome, ordine) VALUES (?, ?)", (nome, ordine)
        ).lastrowid
    else:
        _esiste(conn, "CATEGORIE", "id_categoria", id_categoria, "Categoria")
        conn.execute("UPDATE CATEGORIE SET nome = ?, ordine = ? WHERE id_categoria = ?", (nome, ordine, id_categoria))
    return next(c for c in elenco_categorie(conn) if c["id_categoria"] == id_categoria)


def elimina_categoria(conn: sqlite3.Connection, id_categoria: int) -> None:
    c = _esiste(conn, "CATEGORIE", "id_categoria", id_categoria, "Categoria")
    n = conn.execute("SELECT COUNT(*) FROM ARTICOLI WHERE id_categoria = ?", (id_categoria,)).fetchone()[0]
    if n:
        raise ErroreDominio(
            "CATEGORIA_IN_USO",
            f"La categoria '{c['nome']}' contiene {n} articoli: spostali in un'altra categoria prima di eliminarla.",
        )
    conn.execute("DELETE FROM CATEGORIE WHERE id_categoria = ?", (id_categoria,))


# ============================================================================ ingredienti


def elenco_ingredienti(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        {**dict(r), "sotto_scorta_minima": r["quantita_disponibile"] < r["scorta_minima"]}
        for r in conn.execute(
            """SELECT i.*, COUNT(ai.id_articolo) AS numero_ricette
               FROM INGREDIENTI i LEFT JOIN ARTICOLI_INGREDIENTI ai ON ai.id_ingrediente = i.id_ingrediente
               GROUP BY i.id_ingrediente ORDER BY i.nome"""
        )
    ]


def salva_ingrediente(
    conn: sqlite3.Connection,
    nome: str,
    unita_misura: str,
    quantita_disponibile: float,
    scorta_minima: float = 0,
    id_ingrediente: int | None = None,
) -> dict[str, Any]:
    nome = _testo(nome, "nome", 60)
    if unita_misura not in UNITA:
        raise ErroreDominio("UNITA_NON_VALIDA", f"Unità di misura ammesse: {', '.join(UNITA)}.")
    for valore, campo in ((quantita_disponibile, "quantità disponibile"), (scorta_minima, "scorta minima")):
        if valore is None or valore < 0 or valore > 1_000_000:
            raise ErroreDominio("QUANTITA_NON_VALIDA", f"Il campo '{campo}' deve essere tra 0 e 1.000.000.")
    _nome_libero(conn, "INGREDIENTI", "id_ingrediente", nome, id_ingrediente)
    valori = (nome, unita_misura, quantita_disponibile, scorta_minima)
    if id_ingrediente is None:
        id_ingrediente = conn.execute(
            "INSERT INTO INGREDIENTI (nome, unita_misura, quantita_disponibile, scorta_minima) VALUES (?, ?, ?, ?)",
            valori,
        ).lastrowid
    else:
        _esiste(conn, "INGREDIENTI", "id_ingrediente", id_ingrediente, "Ingrediente")
        conn.execute(
            """UPDATE INGREDIENTI SET nome = ?, unita_misura = ?, quantita_disponibile = ?, scorta_minima = ?
               WHERE id_ingrediente = ?""",
            (*valori, id_ingrediente),
        )
    return next(i for i in elenco_ingredienti(conn) if i["id_ingrediente"] == id_ingrediente)


def elimina_ingrediente(conn: sqlite3.Connection, id_ingrediente: int) -> None:
    i = _esiste(conn, "INGREDIENTI", "id_ingrediente", id_ingrediente, "Ingrediente")
    piatti = [
        r[0]
        for r in conn.execute(
            """SELECT a.nome FROM ARTICOLI_INGREDIENTI ai JOIN ARTICOLI a ON a.id_articolo = ai.id_articolo
               WHERE ai.id_ingrediente = ? ORDER BY a.nome""",
            (id_ingrediente,),
        )
    ]
    if piatti:
        raise ErroreDominio(
            "INGREDIENTE_IN_USO",
            f"'{i['nome']}' è usato nelle ricette di: {', '.join(piatti)}. Toglilo prima dalle ricette.",
        )
    conn.execute("DELETE FROM INGREDIENTI WHERE id_ingrediente = ?", (id_ingrediente,))


# ============================================================================ articoli


def elenco_allergeni(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT codice, nome FROM ALLERGENI ORDER BY nome")]


def _articolo(conn: sqlite3.Connection, r: sqlite3.Row) -> dict[str, Any]:
    id_articolo = r["id_articolo"]
    return {
        "id_articolo": id_articolo,
        "nome": r["nome"],
        "descrizione": r["descrizione"],
        "prezzo": r["prezzo"],
        "id_categoria": r["id_categoria"],
        "categoria": r["categoria"],
        "vegetariano": bool(r["vegetariano"]),
        "asporto": bool(r["disponibile_asporto"]),
        "attivo": bool(r["attivo"]),
        "allergeni": [
            x[0]
            for x in conn.execute(
                """SELECT al.codice FROM ARTICOLI_ALLERGENI aa JOIN ALLERGENI al ON al.id_allergene = aa.id_allergene
                   WHERE aa.id_articolo = ? ORDER BY al.codice""",
                (id_articolo,),
            )
        ],
        "ricetta": [
            dict(x)
            for x in conn.execute(
                """SELECT i.id_ingrediente, i.nome, i.unita_misura, ai.quantita
                   FROM ARTICOLI_INGREDIENTI ai JOIN INGREDIENTI i ON i.id_ingrediente = ai.id_ingrediente
                   WHERE ai.id_articolo = ? ORDER BY ai.quantita DESC""",
                (id_articolo,),
            )
        ],
    }


def elenco_articoli(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    righe = conn.execute(
        """SELECT a.*, c.nome AS categoria FROM ARTICOLI a JOIN CATEGORIE c ON c.id_categoria = a.id_categoria
           ORDER BY c.ordine, a.nome"""
    ).fetchall()
    return [_articolo(conn, r) for r in righe]


def salva_articolo(
    conn: sqlite3.Connection,
    nome: str,
    descrizione: str,
    prezzo: float,
    id_categoria: int,
    vegetariano: bool = False,
    asporto: bool = True,
    attivo: bool = True,
    allergeni: list[str] | None = None,
    ricetta: list[dict[str, Any]] | None = None,
    id_articolo: int | None = None,
) -> dict[str, Any]:
    nome = _testo(nome, "nome", 80)
    descrizione = _testo(descrizione, "descrizione", 300)
    if prezzo is None or prezzo < 0 or prezzo > 1000:
        raise ErroreDominio("PREZZO_NON_VALIDO", "Il prezzo deve essere tra 0 e 1000 euro.")
    _esiste(conn, "CATEGORIE", "id_categoria", id_categoria, "Categoria")
    _nome_libero(conn, "ARTICOLI", "id_articolo", nome, id_articolo)

    codici = {r["codice"]: r["id_allergene"] for r in conn.execute("SELECT codice, id_allergene FROM ALLERGENI")}
    sconosciuti = [a for a in allergeni or [] if a not in codici]
    if sconosciuti:
        raise ErroreDominio("ALLERGENE_SCONOSCIUTO", f"Allergeni non riconosciuti: {', '.join(sconosciuti)}.")

    righe_ricetta: dict[int, float] = {}
    for riga in ricetta or []:
        id_ing, quantita = int(riga["id_ingrediente"]), float(riga["quantita"])
        _esiste(conn, "INGREDIENTI", "id_ingrediente", id_ing, "Ingrediente")
        if quantita <= 0 or quantita > 100_000:
            raise ErroreDominio("QUANTITA_NON_VALIDA", "Ogni ingrediente della ricetta deve avere una quantità positiva.")
        if id_ing in righe_ricetta:
            raise ErroreDominio("INGREDIENTE_DUPLICATO", "Lo stesso ingrediente compare due volte nella ricetta.")
        righe_ricetta[id_ing] = quantita

    valori = (nome, descrizione, prezzo, id_categoria, int(vegetariano), int(asporto), int(attivo))
    if id_articolo is None:
        id_articolo = conn.execute(
            """INSERT INTO ARTICOLI (nome, descrizione, prezzo, id_categoria, vegetariano, disponibile_asporto, attivo)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            valori,
        ).lastrowid
    else:
        _esiste(conn, "ARTICOLI", "id_articolo", id_articolo, "Articolo")
        conn.execute(
            """UPDATE ARTICOLI SET nome = ?, descrizione = ?, prezzo = ?, id_categoria = ?, vegetariano = ?,
               disponibile_asporto = ?, attivo = ? WHERE id_articolo = ?""",
            (*valori, id_articolo),
        )
    # Allergeni e ricetta vengono sostituiti per intero: il modulo li invia sempre completi.
    conn.execute("DELETE FROM ARTICOLI_ALLERGENI WHERE id_articolo = ?", (id_articolo,))
    conn.executemany(
        "INSERT INTO ARTICOLI_ALLERGENI (id_articolo, id_allergene) VALUES (?, ?)",
        [(id_articolo, codici[a]) for a in set(allergeni or [])],
    )
    conn.execute("DELETE FROM ARTICOLI_INGREDIENTI WHERE id_articolo = ?", (id_articolo,))
    conn.executemany(
        "INSERT INTO ARTICOLI_INGREDIENTI (id_articolo, id_ingrediente, quantita) VALUES (?, ?, ?)",
        [(id_articolo, i, q) for i, q in righe_ricetta.items()],
    )
    r = conn.execute(
        """SELECT a.*, c.nome AS categoria FROM ARTICOLI a JOIN CATEGORIE c ON c.id_categoria = a.id_categoria
           WHERE a.id_articolo = ?""",
        (id_articolo,),
    ).fetchone()
    return _articolo(conn, r)
