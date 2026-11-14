"""Prenotazioni attive e individuazione automatica della prenotazione da modificare o cancellare."""

import pytest

from backend import prenotazioni
from backend.errori import ErroreDominio
from backend.permessi import Utente

PRENOTAZIONE_GIULIA = 86  # unica prenotazione di Giulia nel seed, il 2026-12-11 (orologio fissato al 2026-12-03 11:00)


def _giulia(conn):
    r = conn.execute("SELECT id_utente, nome, telefono FROM UTENTI WHERE username = 'giulia'").fetchone()
    return Utente(r["id_utente"], "cliente", r["nome"], r["telefono"])


def _codice(funzione, *argomenti, **opzioni):
    with pytest.raises(ErroreDominio) as exc:
        funzione(*argomenti, **opzioni)
    return exc.value


def test_solo_prenotazioni_attive(db):
    conn, _ = db
    giulia = _giulia(conn)
    # una prenotazione di oggi già passata (10:00) e una di oggi ancora da venire (20:00)
    for ora in ("10:00", "20:00"):
        conn.execute(
            """INSERT INTO PRENOTAZIONI (data, ora, coperti, nome_cliente, telefono, stato, id_tavolo, fonte,
                                         id_utente, creata_il)
               VALUES ('2026-12-03', ?, 2, 'Giulia Ferri', '3331234567', 'confermata', 1, 'sito', ?, '2026-12-01T10:00')""",
            (ora, giulia.id_utente),
        )
    attive = prenotazioni.trova_prenotazioni(conn, utente=giulia)
    assert [p["ora"] for p in attive if p["data"] == "2026-12-03"] == ["20:00"]
    tutte = prenotazioni.trova_prenotazioni(conn, includi_passate=True, utente=giulia)
    assert "10:00" in [p["ora"] for p in tutte if p["data"] == "2026-12-03"]


def test_cliente_registrato_modifica_senza_numero(db):
    conn, _ = db
    giulia = _giulia(conn)
    r = prenotazioni.modifica_prenotazione(conn, None, None, ora="21:00", utente=giulia)
    assert r["id_prenotazione"] == PRENOTAZIONE_GIULIA and r["ora"] == "21:00"


def test_piu_prenotazioni_attive_elenco_per_data(db):
    conn, _ = db
    giulia = _giulia(conn)
    prenotazioni.crea_prenotazione(conn, "2026-12-04", "20:30", 2, None, None, utente=giulia)
    e = _codice(prenotazioni.cancella_prenotazione, conn, None, None, utente=giulia)
    assert e.codice == "PIU_PRENOTAZIONI_ATTIVE"
    elenco = e.dettagli["prenotazioni_attive"]
    assert [(p["giorno"], p["data"]) for p in elenco] == [("venerdì", "2026-12-04"), ("venerdì", "2026-12-11")]
    # nessuna cancellazione è avvenuta
    assert len(prenotazioni.trova_prenotazioni(conn, utente=giulia)) == 2


def test_ospite_tramite_telefono_e_casi_senza_dati(db):
    conn, _ = db
    r = prenotazioni.modifica_prenotazione(conn, None, "333 1234567", coperti=3)
    assert r["id_prenotazione"] == PRENOTAZIONE_GIULIA and r["coperti"] == 3
    assert _codice(prenotazioni.cancella_prenotazione, conn, None, None).codice == "PRENOTAZIONE_DA_INDICARE"
    assert _codice(prenotazioni.cancella_prenotazione, conn, None, "320 0000000").codice == "NESSUNA_PRENOTAZIONE_ATTIVA"


def test_scheda_di_conferma_senza_numero():
    from harness.confirm import riepilogo
    from harness.llm.base import ToolSpec

    testo = riepilogo(ToolSpec("modifica_prenotazione", "", {}, scrittura=True), {"ora": "21:00"})
    assert "unica prenotazione attiva" in testo and "21:00" in testo
