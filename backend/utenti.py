"""Gestione degli utenti: creazione, autenticazione, modifica di ruolo e stato.

Le password non sono mai salvate in chiaro: si conserva solo un hash scrypt (funzione di
derivazione lenta, resistente agli attacchi a forza bruta) con salt casuale per utente.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from typing import Any

from backend import clock
from backend.errori import ErroreDominio
from backend.permessi import RUOLI, Utente
from backend.validazione import normalizza_telefono

SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
LUNGHEZZA_MINIMA_PASSWORD = 10


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derivata = hashlib.scrypt(password.encode("utf-8"), salt=salt, **SCRYPT)
    return f"scrypt${salt.hex()}${derivata.hex()}"


def verifica_password(password: str, memorizzato: str) -> bool:
    try:
        schema, salt_hex, derivata_hex = memorizzato.split("$")
    except ValueError:
        return False
    if schema != "scrypt":
        return False
    calcolata = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), **SCRYPT)
    return hmac.compare_digest(calcolata.hex(), derivata_hex)  # confronto a tempo costante


def _valida(username: str, password: str | None, ruolo: str) -> None:
    if not username or not username.replace(".", "").replace("_", "").isalnum() or len(username) > 40:
        raise ErroreDominio("USERNAME_NON_VALIDO", "Username non valido (lettere, numeri, punto e trattino basso).")
    if password is not None and len(password) < LUNGHEZZA_MINIMA_PASSWORD:
        raise ErroreDominio(
            "PASSWORD_DEBOLE", f"La password deve avere almeno {LUNGHEZZA_MINIMA_PASSWORD} caratteri."
        )
    if ruolo not in RUOLI:
        raise ErroreDominio("RUOLO_NON_VALIDO", f"Ruolo non valido. Ruoli ammessi: {', '.join(RUOLI)}.")


def _in_dict(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "id_utente": r["id_utente"],
        "username": r["username"],
        "ruolo": r["ruolo"],
        "nome": r["nome"],
        "telefono": r["telefono"],
        "attivo": bool(r["attivo"]),
        "creato_il": r["creato_il"],
    }


def crea_utente(
    conn: sqlite3.Connection, username: str, password: str, ruolo: str, nome: str, telefono: str | None = None
) -> dict[str, Any]:
    username = (username or "").strip().lower()
    _valida(username, password, ruolo)
    tel = normalizza_telefono(telefono) if telefono else None
    if not (nome or "").strip():
        raise ErroreDominio("NOME_MANCANTE", "Il nome è obbligatorio.")
    try:
        cur = conn.execute(
            "INSERT INTO UTENTI (username, password_hash, ruolo, nome, telefono, creato_il) VALUES (?, ?, ?, ?, ?, ?)",
            (username, hash_password(password), ruolo, nome.strip(), tel, clock.adesso().isoformat(timespec="minutes")),
        )
    except sqlite3.IntegrityError:
        raise ErroreDominio("USERNAME_ESISTENTE", f"L'username '{username}' è già in uso.") from None
    return trova_utente(conn, cur.lastrowid)


def trova_utente(conn: sqlite3.Connection, id_utente: int) -> dict[str, Any]:
    r = conn.execute("SELECT * FROM UTENTI WHERE id_utente = ?", (id_utente,)).fetchone()
    if r is None:
        raise ErroreDominio("UTENTE_INESISTENTE", f"Utente {id_utente} inesistente.")
    return _in_dict(r)


def elenco_utenti(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [_in_dict(r) for r in conn.execute("SELECT * FROM UTENTI ORDER BY ruolo, username")]


def autentica(conn: sqlite3.Connection, username: str, password: str) -> Utente | None:
    """Restituisce l'utente se le credenziali sono corrette e l'account è attivo, altrimenti None.

    Il messaggio d'errore lato web è sempre lo stesso, per non rivelare quali username esistono.
    """
    r = conn.execute("SELECT * FROM UTENTI WHERE username = ?", ((username or "").strip().lower(),)).fetchone()
    if r is None:
        hash_password(password or "x")  # tempo di risposta simile anche per username inesistenti
        return None
    if not verifica_password(password or "", r["password_hash"]) or not r["attivo"]:
        return None
    return Utente(id_utente=r["id_utente"], ruolo=r["ruolo"], nome=r["nome"], telefono=r["telefono"])


def utente_attivo(conn: sqlite3.Connection, id_utente: int) -> Utente | None:
    """Rilegge l'utente dal database: un account disattivato o cambiato di ruolo vale subito."""
    r = conn.execute("SELECT * FROM UTENTI WHERE id_utente = ?", (id_utente,)).fetchone()
    if r is None or not r["attivo"]:
        return None
    return Utente(id_utente=r["id_utente"], ruolo=r["ruolo"], nome=r["nome"], telefono=r["telefono"])


def modifica_utente(
    conn: sqlite3.Connection,
    id_utente: int,
    ruolo: str | None = None,
    attivo: bool | None = None,
    password: str | None = None,
    nome: str | None = None,
    telefono: str | None = None,
) -> dict[str, Any]:
    attuale = trova_utente(conn, id_utente)
    nuovo_ruolo = ruolo or attuale["ruolo"]
    _valida(attuale["username"], password, nuovo_ruolo)
    conn.execute(
        "UPDATE UTENTI SET ruolo = ?, attivo = ?, nome = ?, telefono = ? WHERE id_utente = ?",
        (
            nuovo_ruolo,
            int(attuale["attivo"] if attivo is None else attivo),
            (nome or attuale["nome"]).strip(),
            normalizza_telefono(telefono) if telefono else attuale["telefono"],
            id_utente,
        ),
    )
    if password:
        conn.execute("UPDATE UTENTI SET password_hash = ? WHERE id_utente = ?", (hash_password(password), id_utente))
    return trova_utente(conn, id_utente)
