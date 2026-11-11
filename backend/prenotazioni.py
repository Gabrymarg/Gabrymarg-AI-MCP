"""Servizio prenotazioni: disponibilità, creazione, ricerca, modifica e cancellazione.

Regole di business:
- una prenotazione occupa il tavolo per DURATA_MIN minuti;
- si può prenotare solo durante un turno di apertura, entro MARGINE_FINALE_MIN
  minuti dalla chiusura, non nel passato e al massimo ANTICIPO_MAX_GIORNI giorni avanti;
- viene assegnato il tavolo libero più piccolo con posti sufficienti;
- modifica e cancellazione richiedono il telefono usato in fase di prenotazione
  (verifica minima dell'identità del cliente).
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta
from typing import Any

from backend import clock
from backend.errori import ErroreDominio
from backend.orari import Turno, descrizione_orari, turni_del_giorno
from backend.validazione import (
    nome_cliente,
    normalizza_telefono,
    parse_data,
    parse_ora,
    stesso_telefono,
    testo_breve,
)

DURATA_MIN = 120
MARGINE_FINALE_MIN = 90
ANTICIPO_MAX_GIORNI = 60
PASSO_ALTERNATIVE_MIN = 30
MAX_ALTERNATIVE = 3


# --------------------------------------------------------------------------- utilità


def _minuti(o: time) -> int:
    return o.hour * 60 + o.minute


def _max_posti(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT MAX(n_posti) FROM TAVOLI").fetchone()[0] or 0


def _verifica_coperti(conn: sqlite3.Connection, coperti: int) -> None:
    if coperti < 1:
        raise ErroreDominio("COPERTI_NON_VALIDI", "Il numero di coperti deve essere almeno 1.")
    massimo = _max_posti(conn)
    if coperti > massimo:
        raise ErroreDominio(
            "GRUPPO_TROPPO_NUMEROSO",
            f"Per gruppi oltre {massimo} persone non è possibile prenotare online: "
            "il cliente deve contattare direttamente il ristorante.",
            {"max_coperti": massimo},
        )


def _verifica_momento(conn: sqlite3.Connection, giorno: date, ora: time) -> Turno:
    """Controlla che data e ora siano prenotabili e restituisce il turno corrispondente."""
    ora_attuale = clock.adesso()
    momento = datetime.combine(giorno, ora)
    if momento <= ora_attuale:
        raise ErroreDominio(
            "DATA_PASSATA",
            f"Il momento richiesto ({giorno.isoformat()} {ora:%H:%M}) è già passato. "
            f"Adesso sono le {ora_attuale:%H:%M} del {ora_attuale.date().isoformat()}.",
        )
    if giorno > ora_attuale.date() + timedelta(days=ANTICIPO_MAX_GIORNI):
        raise ErroreDominio(
            "TROPPO_IN_ANTICIPO",
            f"Si accettano prenotazioni al massimo {ANTICIPO_MAX_GIORNI} giorni in anticipo.",
        )
    turni = turni_del_giorno(conn, giorno)
    for turno in turni:
        if turno.contiene(ora, MARGINE_FINALE_MIN):
            return turno
    raise ErroreDominio(
        "FUORI_ORARIO",
        f"Alle {ora:%H:%M} del {giorno.isoformat()} non si accettano prenotazioni "
        f"({descrizione_orari(conn, giorno)}; ultima prenotazione {MARGINE_FINALE_MIN} minuti prima della chiusura).",
        {"orari": descrizione_orari(conn, giorno)},
    )


def _tavoli_liberi(
    conn: sqlite3.Connection,
    giorno: date,
    ora: time,
    coperti: int,
    escludi_prenotazione: int | None = None,
) -> list[sqlite3.Row]:
    occupati: set[int] = set()
    for p in conn.execute(
        "SELECT id_prenotazione, ora, id_tavolo FROM PRENOTAZIONI WHERE data = ? AND stato = 'confermata'",
        (giorno.isoformat(),),
    ):
        if p["id_prenotazione"] == escludi_prenotazione:
            continue
        if abs(_minuti(time.fromisoformat(p["ora"])) - _minuti(ora)) < DURATA_MIN:
            occupati.add(p["id_tavolo"])
    candidati = conn.execute(
        "SELECT id_tavolo, nome, n_posti, sala FROM TAVOLI WHERE n_posti >= ? ORDER BY n_posti, id_tavolo",
        (coperti,),
    ).fetchall()
    return [t for t in candidati if t["id_tavolo"] not in occupati]


def _orari_alternativi(
    conn: sqlite3.Connection, giorno: date, ora: time, coperti: int, turno: Turno
) -> list[str]:
    candidati: list[time] = []
    t = datetime.combine(giorno, turno.apertura)
    fine = datetime.combine(giorno, turno.chiusura) - timedelta(minutes=MARGINE_FINALE_MIN)
    while t <= fine:
        if t.time() != ora and t > clock.adesso():
            candidati.append(t.time())
        t += timedelta(minutes=PASSO_ALTERNATIVE_MIN)
    candidati.sort(key=lambda c: abs(_minuti(c) - _minuti(ora)))
    alternative = [c for c in candidati if _tavoli_liberi(conn, giorno, c, coperti)]
    return sorted(f"{c:%H:%M}" for c in alternative[:MAX_ALTERNATIVE])


def _riga_in_dict(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "id_prenotazione": r["id_prenotazione"],
        "data": r["data"],
        "ora": r["ora"],
        "coperti": r["coperti"],
        "nome_cliente": r["nome_cliente"],
        "telefono": r["telefono"],
        "note": r["note"],
        "stato": r["stato"],
        "tavolo": r["tavolo"],
        "sala": r["sala"],
    }


_SELECT_PRENOTAZIONE = """
    SELECT p.*, t.nome AS tavolo, t.sala AS sala
    FROM PRENOTAZIONI p JOIN TAVOLI t ON t.id_tavolo = p.id_tavolo
"""


def _carica(conn: sqlite3.Connection, id_prenotazione: int) -> sqlite3.Row:
    r = conn.execute(_SELECT_PRENOTAZIONE + " WHERE p.id_prenotazione = ?", (id_prenotazione,)).fetchone()
    if r is None:
        raise ErroreDominio(
            "PRENOTAZIONE_INESISTENTE", f"Non esiste nessuna prenotazione con numero {id_prenotazione}."
        )
    return r


def _carica_verificata(conn: sqlite3.Connection, id_prenotazione: int, telefono: str) -> sqlite3.Row:
    r = _carica(conn, id_prenotazione)
    if not stesso_telefono(r["telefono"], telefono):
        # Stesso messaggio della prenotazione inesistente: non si rivela se il numero esiste.
        raise ErroreDominio(
            "PRENOTAZIONE_INESISTENTE",
            f"Non esiste nessuna prenotazione con numero {id_prenotazione} associata a questo telefono.",
        )
    if r["stato"] != "confermata":
        raise ErroreDominio(
            "PRENOTAZIONE_NON_MODIFICABILE",
            f"La prenotazione {id_prenotazione} è in stato '{r['stato']}' e non può essere modificata.",
        )
    if datetime.combine(date.fromisoformat(r["data"]), time.fromisoformat(r["ora"])) <= clock.adesso():
        raise ErroreDominio(
            "PRENOTAZIONE_NON_MODIFICABILE",
            f"La prenotazione {id_prenotazione} si riferisce a un momento già passato.",
        )
    return r


# --------------------------------------------------------------------------- operazioni


def verifica_disponibilita(conn: sqlite3.Connection, data: str, ora: str, coperti: int) -> dict[str, Any]:
    giorno, orario = parse_data(data), parse_ora(ora)
    _verifica_coperti(conn, coperti)
    turno = _verifica_momento(conn, giorno, orario)
    liberi = _tavoli_liberi(conn, giorno, orario, coperti)
    esito: dict[str, Any] = {
        "data": giorno.isoformat(),
        "ora": f"{orario:%H:%M}",
        "coperti": coperti,
        "disponibile": bool(liberi),
        "turno": turno.nome,
    }
    if liberi:
        esito["sala"] = liberi[0]["sala"]
    else:
        esito["orari_alternativi"] = _orari_alternativi(conn, giorno, orario, coperti, turno)
    return esito


def crea_prenotazione(
    conn: sqlite3.Connection,
    data: str,
    ora: str,
    coperti: int,
    nome: str,
    telefono: str,
    note: str | None = None,
    fonte: str = "agente",
) -> dict[str, Any]:
    giorno, orario = parse_data(data), parse_ora(ora)
    nome = nome_cliente(nome)
    tel = normalizza_telefono(telefono)
    note = testo_breve(note, "note", 300)
    _verifica_coperti(conn, coperti)
    turno = _verifica_momento(conn, giorno, orario)
    liberi = _tavoli_liberi(conn, giorno, orario, coperti)
    if not liberi:
        raise ErroreDominio(
            "NESSUN_TAVOLO_LIBERO",
            f"Non ci sono tavoli liberi per {coperti} persone il {giorno.isoformat()} alle {orario:%H:%M}.",
            {"orari_alternativi": _orari_alternativi(conn, giorno, orario, coperti, turno)},
        )
    cur = conn.execute(
        """INSERT INTO PRENOTAZIONI (data, ora, coperti, nome_cliente, telefono, note, stato,
                                     id_tavolo, fonte, creata_il)
           VALUES (?, ?, ?, ?, ?, ?, 'confermata', ?, ?, ?)""",
        (
            giorno.isoformat(),
            f"{orario:%H:%M}",
            coperti,
            nome,
            tel,
            note,
            liberi[0]["id_tavolo"],
            fonte,
            clock.adesso().isoformat(timespec="minutes"),
        ),
    )
    return _riga_in_dict(_carica(conn, cur.lastrowid))


def trova_prenotazioni(
    conn: sqlite3.Connection,
    nome: str | None = None,
    telefono: str | None = None,
    data: str | None = None,
    includi_passate: bool = False,
) -> list[dict[str, Any]]:
    if not (nome or telefono or data):
        raise ErroreDominio(
            "FILTRO_MANCANTE", "Indicare almeno uno tra nome, telefono e data per cercare le prenotazioni."
        )
    condizioni, parametri = ["p.stato = 'confermata'"], []
    if nome:
        condizioni.append("p.nome_cliente LIKE ?")
        parametri.append(f"%{nome.strip()}%")
    if telefono:
        condizioni.append("p.telefono = ?")
        parametri.append(normalizza_telefono(telefono))
    if data:
        condizioni.append("p.data = ?")
        parametri.append(parse_data(data).isoformat())
    if not includi_passate:
        condizioni.append("p.data >= ?")
        parametri.append(clock.adesso().date().isoformat())
    righe = conn.execute(
        _SELECT_PRENOTAZIONE + " WHERE " + " AND ".join(condizioni) + " ORDER BY p.data, p.ora LIMIT 20",
        parametri,
    ).fetchall()
    return [_riga_in_dict(r) for r in righe]


def modifica_prenotazione(
    conn: sqlite3.Connection,
    id_prenotazione: int,
    telefono: str,
    data: str | None = None,
    ora: str | None = None,
    coperti: int | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    attuale = _carica_verificata(conn, id_prenotazione, telefono)
    if data is None and ora is None and coperti is None and note is None:
        raise ErroreDominio("NESSUNA_MODIFICA", "Indicare almeno un campo da modificare.")
    giorno = parse_data(data) if data else date.fromisoformat(attuale["data"])
    orario = parse_ora(ora) if ora else time.fromisoformat(attuale["ora"])
    n_coperti = coperti if coperti is not None else attuale["coperti"]
    nuove_note = testo_breve(note, "note", 300) if note is not None else attuale["note"]
    _verifica_coperti(conn, n_coperti)
    turno = _verifica_momento(conn, giorno, orario)

    id_tavolo = attuale["id_tavolo"]
    liberi = _tavoli_liberi(conn, giorno, orario, n_coperti, escludi_prenotazione=id_prenotazione)
    if not liberi:
        raise ErroreDominio(
            "NESSUN_TAVOLO_LIBERO",
            f"Non ci sono tavoli liberi per {n_coperti} persone il {giorno.isoformat()} alle {orario:%H:%M}: "
            "la prenotazione originale resta invariata.",
            {"orari_alternativi": _orari_alternativi(conn, giorno, orario, n_coperti, turno)},
        )
    if id_tavolo not in {t["id_tavolo"] for t in liberi}:
        id_tavolo = liberi[0]["id_tavolo"]

    conn.execute(
        """UPDATE PRENOTAZIONI SET data = ?, ora = ?, coperti = ?, note = ?, id_tavolo = ?, modificata_il = ?
           WHERE id_prenotazione = ?""",
        (
            giorno.isoformat(),
            f"{orario:%H:%M}",
            n_coperti,
            nuove_note,
            id_tavolo,
            clock.adesso().isoformat(timespec="minutes"),
            id_prenotazione,
        ),
    )
    return _riga_in_dict(_carica(conn, id_prenotazione))


def cancella_prenotazione(conn: sqlite3.Connection, id_prenotazione: int, telefono: str) -> dict[str, Any]:
    _carica_verificata(conn, id_prenotazione, telefono)
    conn.execute(
        "UPDATE PRENOTAZIONI SET stato = 'cancellata', modificata_il = ? WHERE id_prenotazione = ?",
        (clock.adesso().isoformat(timespec="minutes"), id_prenotazione),
    )
    return _riga_in_dict(_carica(conn, id_prenotazione))
