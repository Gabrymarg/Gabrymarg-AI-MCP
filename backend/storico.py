"""Storico delle conversazioni della web app.

Regole di accesso (applicate qui, non nell'interfaccia):
  - ogni utente vede, riprende ed elimina solo le proprie conversazioni;
  - l'amministratore può LEGGERE tutte le conversazioni (controllo e assistenza), ma riprende ed elimina
    solo le proprie: riprendere la chat di un cliente farebbe lavorare l'agente con i permessi
    dell'amministratore dentro una conversazione altrui.

Si salvano solo le richieste dell'utente e le risposte finali, cioè ciò che l'utente ha visto. I passaggi
interni del ciclo (chiamate ai tool, risultati, ragionamento) restano nei log JSONL.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from backend.db import SCHEMA
from backend.errori import ErroreDominio
from backend.permessi import Utente

LUNGHEZZA_TITOLO = 60


def _adesso() -> str:
    # Orario reale (non l'orologio fissato per le demo): serve a ordinare le conversazioni.
    return datetime.now().isoformat(timespec="seconds")


def crea_tabelle(conn: sqlite3.Connection) -> None:
    """Crea le tabelle dello storico se mancano (database creati prima dell'introduzione dello storico)."""
    schema = SCHEMA.read_text(encoding="utf-8")
    conn.executescript(schema[schema.index("CREATE TABLE IF NOT EXISTS CONVERSAZIONI"):])


def titolo_da(testo: str) -> str:
    testo = " ".join(testo.split())
    return testo if len(testo) <= LUNGHEZZA_TITOLO else testo[: LUNGHEZZA_TITOLO - 1].rstrip() + "…"


def nuova(conn: sqlite3.Connection, id_utente: int, primo_messaggio: str, modello: str | None = None) -> int:
    adesso = _adesso()
    return conn.execute(
        "INSERT INTO CONVERSAZIONI (id_utente, titolo, modello, creata_il, aggiornata_il) VALUES (?, ?, ?, ?, ?)",
        (id_utente, titolo_da(primo_messaggio), modello, adesso, adesso),
    ).lastrowid


def aggiungi(conn: sqlite3.Connection, id_conversazione: int, ruolo: str, testo: str) -> None:
    adesso = _adesso()
    conn.execute(
        "INSERT INTO MESSAGGI_CHAT (id_conversazione, ruolo, testo, creato_il) VALUES (?, ?, ?, ?)",
        (id_conversazione, ruolo, testo, adesso),
    )
    conn.execute("UPDATE CONVERSAZIONI SET aggiornata_il = ? WHERE id_conversazione = ?", (adesso, id_conversazione))


def elenco(conn: sqlite3.Connection, utente: Utente, tutte: bool = False) -> list[dict[str, Any]]:
    """Conversazioni dell'utente, dalla più recente; con tutte=True (solo admin) quelle di tutti."""
    if tutte and utente.ruolo != "admin":
        raise ErroreDominio("PERMESSO_NEGATO", "Solo l'amministratore può vedere le conversazioni di tutti.")
    condizione, parametri = ("", []) if tutte else ("WHERE c.id_utente = ?", [utente.id_utente])
    righe = conn.execute(
        f"""SELECT c.id_conversazione, c.titolo, c.modello, c.creata_il, c.aggiornata_il, c.id_utente,
                   u.username, u.nome, COUNT(m.id_messaggio) AS numero_messaggi
            FROM CONVERSAZIONI c JOIN UTENTI u ON u.id_utente = c.id_utente
            LEFT JOIN MESSAGGI_CHAT m ON m.id_conversazione = c.id_conversazione
            {condizione}
            GROUP BY c.id_conversazione ORDER BY c.aggiornata_il DESC, c.id_conversazione DESC LIMIT 200""",
        parametri,
    ).fetchall()
    return [{**dict(r), "propria": r["id_utente"] == utente.id_utente} for r in righe]


def _accessibile(conn: sqlite3.Connection, id_conversazione: int, utente: Utente, solo_proprietario: bool) -> sqlite3.Row:
    r = conn.execute(
        """SELECT c.*, u.username FROM CONVERSAZIONI c JOIN UTENTI u ON u.id_utente = c.id_utente
           WHERE c.id_conversazione = ?""",
        (id_conversazione,),
    ).fetchone()
    # Una conversazione altrui risponde come inesistente: non si rivela che esiste.
    if r is None or (r["id_utente"] != utente.id_utente and (solo_proprietario or utente.ruolo != "admin")):
        raise ErroreDominio("CONVERSAZIONE_INESISTENTE", "Conversazione inesistente.")
    return r


def leggi(conn: sqlite3.Connection, id_conversazione: int, utente: Utente, per_riprendere: bool = False) -> dict[str, Any]:
    c = _accessibile(conn, id_conversazione, utente, solo_proprietario=per_riprendere)
    messaggi = [
        dict(m)
        for m in conn.execute(
            "SELECT ruolo, testo, creato_il FROM MESSAGGI_CHAT WHERE id_conversazione = ? ORDER BY id_messaggio",
            (id_conversazione,),
        )
    ]
    return {
        "id_conversazione": c["id_conversazione"], "titolo": c["titolo"], "username": c["username"],
        "propria": c["id_utente"] == utente.id_utente, "messaggi": messaggi,
    }


def elimina(conn: sqlite3.Connection, id_conversazione: int, utente: Utente) -> None:
    _accessibile(conn, id_conversazione, utente, solo_proprietario=True)
    conn.execute("DELETE FROM MESSAGGI_CHAT WHERE id_conversazione = ?", (id_conversazione,))
    conn.execute("DELETE FROM CONVERSAZIONI WHERE id_conversazione = ?", (id_conversazione,))
