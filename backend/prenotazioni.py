"""Servizio prenotazioni: disponibilità, creazione, ricerca, modifica e cancellazione.

Regole di business:
- una prenotazione occupa il tavolo per DURATA_MIN minuti;
- si può prenotare solo durante un turno di apertura, entro MARGINE_FINALE_MIN
  minuti dalla chiusura, non nel passato e al massimo ANTICIPO_MAX_GIORNI giorni avanti;
- viene assegnato il tavolo libero più piccolo con posti sufficienti;
- chi può vedere o modificare una prenotazione dipende dall'utente (vedi backend/permessi.py):
  il personale opera su tutte; un cliente registrato solo sulle proprie (id_utente);
  un ospite senza login deve fornire il telefono usato in fase di prenotazione.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta
from typing import Any

from backend import clock
from backend.errori import ErroreDominio
from backend.orari import Turno, descrizione_orari, turni_del_giorno
from backend.permessi import OSPITE, Utente
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


def _carica_verificata(
    conn: sqlite3.Connection, id_prenotazione: int, telefono: str | None, utente: Utente = OSPITE
) -> sqlite3.Row:
    r = _carica(conn, id_prenotazione)
    if utente.personale:
        autorizzato = True
    elif utente.cliente_registrato:
        autorizzato = r["id_utente"] == utente.id_utente
    else:
        autorizzato = bool(telefono) and stesso_telefono(r["telefono"], telefono)
    if not autorizzato:
        # Stesso messaggio della prenotazione inesistente: non si rivela se il numero esiste.
        raise ErroreDominio(
            "PRENOTAZIONE_INESISTENTE",
            f"Non esiste nessuna prenotazione con numero {id_prenotazione} "
            + ("tra le sue prenotazioni." if utente.cliente_registrato else "associata a questo telefono."),
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


GIORNI = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")


def _risolvi_id(conn: sqlite3.Connection, id_prenotazione: int | None, telefono: str | None, utente: Utente) -> int:
    """Se il numero non è indicato, individua la prenotazione tra quelle ATTIVE del cliente.

    Il cliente non deve conoscere il numero della propria prenotazione: un cliente registrato è identificato
    dal login, un ospite dal telefono. Con una sola prenotazione attiva si usa quella; con più prenotazioni
    l'errore elenca data, giorno e ora, così l'assistente può chiedere quale senza parlare di numeri.
    """
    if id_prenotazione is not None:
        return id_prenotazione
    if not (utente.cliente_registrato or telefono):
        raise ErroreDominio(
            "PRENOTAZIONE_DA_INDICARE",
            "Per trovare la prenotazione serve il telefono con cui è stata fatta (o il suo numero).",
        )
    attive = trova_prenotazioni(conn, telefono=None if utente.cliente_registrato else telefono, utente=utente)
    if not attive:
        raise ErroreDominio("NESSUNA_PRENOTAZIONE_ATTIVA", "Non risultano prenotazioni attive da modificare.")
    if len(attive) > 1:
        raise ErroreDominio(
            "PIU_PRENOTAZIONI_ATTIVE",
            f"Il cliente ha {len(attive)} prenotazioni attive: chiedere quale intende, indicandole per giorno, "
            "data e ora (non per numero).",
            {"prenotazioni_attive": [
                {"id_prenotazione": p["id_prenotazione"], "giorno": GIORNI[date.fromisoformat(p["data"]).weekday()],
                 "data": p["data"], "ora": p["ora"], "coperti": p["coperti"]}
                for p in attive
            ]},
        )
    return attive[0]["id_prenotazione"]


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


def orari_disponibili(conn: sqlite3.Connection, data: str, coperti: int) -> dict[str, Any]:
    """Tutti gli orari prenotabili (a passi di 30 minuti) con almeno un tavolo libero, per turno."""
    giorno = parse_data(data)
    _verifica_coperti(conn, coperti)
    if giorno < clock.adesso().date():
        raise ErroreDominio("DATA_PASSATA", f"Il giorno {giorno.isoformat()} è già passato.")
    turni = turni_del_giorno(conn, giorno)
    esito: dict[str, Any] = {"data": giorno.isoformat(), "coperti": coperti, "chiuso": not turni, "turni": {}}
    for turno in turni:
        liberi = []
        t = datetime.combine(giorno, turno.apertura)
        fine = datetime.combine(giorno, turno.chiusura) - timedelta(minutes=MARGINE_FINALE_MIN)
        while t <= fine:
            if t > clock.adesso() and _tavoli_liberi(conn, giorno, t.time(), coperti):
                liberi.append(f"{t:%H:%M}")
            t += timedelta(minutes=PASSO_ALTERNATIVE_MIN)
        esito["turni"][turno.nome] = liberi
    if not turni:
        esito["messaggio"] = descrizione_orari(conn, giorno)
    return esito


def crea_prenotazione(
    conn: sqlite3.Connection,
    data: str,
    ora: str,
    coperti: int,
    nome: str | None,
    telefono: str | None,
    note: str | None = None,
    fonte: str = "agente",
    utente: Utente = OSPITE,
) -> dict[str, Any]:
    giorno, orario = parse_data(data), parse_ora(ora)
    if utente.cliente_registrato:
        # Per un cliente registrato nome e telefono vengono dal profilo, non dalla conversazione.
        nome, telefono = nome or utente.nome, telefono or utente.telefono
    nome = nome_cliente(nome or "")
    if not telefono:
        raise ErroreDominio("TELEFONO_MANCANTE", "Il numero di telefono del cliente è obbligatorio.")
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
                                     id_tavolo, fonte, id_utente, creata_il)
           VALUES (?, ?, ?, ?, ?, ?, 'confermata', ?, ?, ?, ?)""",
        (
            giorno.isoformat(),
            f"{orario:%H:%M}",
            coperti,
            nome,
            tel,
            note,
            liberi[0]["id_tavolo"],
            fonte,
            utente.id_utente if utente.cliente_registrato else None,
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
    utente: Utente = OSPITE,
) -> list[dict[str, Any]]:
    condizioni, parametri = ["p.stato = 'confermata'"], []
    if utente.cliente_registrato:
        # Un cliente registrato vede solo le proprie prenotazioni, qualunque filtro indichi.
        condizioni.append("p.id_utente = ?")
        parametri.append(utente.id_utente)
    elif not (nome or telefono or data):
        raise ErroreDominio(
            "FILTRO_MANCANTE", "Indicare almeno uno tra nome, telefono e data per cercare le prenotazioni."
        )
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
        # Solo le prenotazioni attive: future, oppure di oggi con l'orario non ancora passato.
        adesso = clock.adesso()
        condizioni.append("(p.data > ? OR (p.data = ? AND p.ora > ?))")
        parametri += [adesso.date().isoformat(), adesso.date().isoformat(), f"{adesso:%H:%M}"]
    righe = conn.execute(
        _SELECT_PRENOTAZIONE + " WHERE " + " AND ".join(condizioni) + " ORDER BY p.data, p.ora LIMIT 20",
        parametri,
    ).fetchall()
    return [_riga_in_dict(r) for r in righe]


def modifica_prenotazione(
    conn: sqlite3.Connection,
    id_prenotazione: int | None,
    telefono: str | None,
    data: str | None = None,
    ora: str | None = None,
    coperti: int | None = None,
    note: str | None = None,
    utente: Utente = OSPITE,
) -> dict[str, Any]:
    if data is None and ora is None and coperti is None and note is None:
        raise ErroreDominio("NESSUNA_MODIFICA", "Indicare almeno un campo da modificare.")
    id_prenotazione = _risolvi_id(conn, id_prenotazione, telefono, utente)
    attuale = _carica_verificata(conn, id_prenotazione, telefono, utente)
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


def cancella_prenotazione(
    conn: sqlite3.Connection, id_prenotazione: int | None, telefono: str | None, utente: Utente = OSPITE
) -> dict[str, Any]:
    id_prenotazione = _risolvi_id(conn, id_prenotazione, telefono, utente)
    _carica_verificata(conn, id_prenotazione, telefono, utente)
    conn.execute(
        "UPDATE PRENOTAZIONI SET stato = 'cancellata', modificata_il = ? WHERE id_prenotazione = ?",
        (clock.adesso().isoformat(timespec="minutes"), id_prenotazione),
    )
    return _riga_in_dict(_carica(conn, id_prenotazione))


def prenotazioni_del_giorno(conn: sqlite3.Connection, data: str) -> dict[str, Any]:
    """Quadro della sala per una data (uso del personale): prenotazioni attive, coperti per turno."""
    giorno = parse_data(data)
    righe = conn.execute(
        _SELECT_PRENOTAZIONE + " WHERE p.data = ? AND p.stato = 'confermata' ORDER BY p.ora, t.nome",
        (giorno.isoformat(),),
    ).fetchall()
    prenotazioni = [_riga_in_dict(r) for r in righe]
    coperti = {"pranzo": 0, "cena": 0}
    for p in prenotazioni:
        coperti["pranzo" if p["ora"] < "17:00" else "cena"] += p["coperti"]
    return {
        "data": giorno.isoformat(),
        "numero_prenotazioni": len(prenotazioni),
        "coperti_pranzo": coperti["pranzo"],
        "coperti_cena": coperti["cena"],
        "prenotazioni": prenotazioni,
    }
