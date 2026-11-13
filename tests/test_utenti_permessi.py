"""Test di utenti, token, permessi e regole di proprietà dei dati."""

import base64
import json

import pytest

from backend import menu, ordini, permessi, prenotazioni, token_accesso, utenti
from backend.errori import ErroreDominio
from backend.permessi import Utente


def utente(conn, username):
    r = conn.execute("SELECT * FROM UTENTI WHERE username = ?", (username,)).fetchone()
    return Utente(r["id_utente"], r["ruolo"], r["nome"], r["telefono"])


# ------------------------------------------------------------------ password e autenticazione


def test_password_mai_in_chiaro(db):
    conn, _ = db
    memorizzato = conn.execute("SELECT password_hash FROM UTENTI WHERE username='giulia'").fetchone()[0]
    assert memorizzato.startswith("scrypt$") and "Giulia-Borgo-2026" not in memorizzato


def test_autenticazione(db):
    conn, _ = db
    assert utenti.autentica(conn, "giulia", "Giulia-Borgo-2026").ruolo == "cliente"
    assert utenti.autentica(conn, "GIULIA ", "Giulia-Borgo-2026") is not None  # username normalizzato
    assert utenti.autentica(conn, "giulia", "sbagliata") is None
    assert utenti.autentica(conn, "nessuno", "qualunque") is None


def test_utente_disattivato_non_entra(db):
    conn, _ = db
    u = utente(conn, "giulia")
    utenti.modifica_utente(conn, u.id_utente, attivo=False)
    assert utenti.autentica(conn, "giulia", "Giulia-Borgo-2026") is None
    assert utenti.utente_attivo(conn, u.id_utente) is None


def test_creazione_utente_validata(db):
    conn, _ = db
    with pytest.raises(ErroreDominio, match="almeno"):
        utenti.crea_utente(conn, "nuovo", "corta", "cliente", "Nuovo")
    with pytest.raises(ErroreDominio) as exc:
        utenti.crea_utente(conn, "nuovo", "Password-lunga-1", "superuser", "Nuovo")
    assert exc.value.codice == "RUOLO_NON_VALIDO"
    with pytest.raises(ErroreDominio) as exc:
        utenti.crea_utente(conn, "giulia", "Password-lunga-1", "cliente", "Doppione")
    assert exc.value.codice == "USERNAME_ESISTENTE"


# ------------------------------------------------------------------ token


def test_token_valido_e_manomesso(db, monkeypatch):
    monkeypatch.setenv("RISTO_SECRET", "segreto-di-test")
    t = token_accesso.emetti(4, "cliente")
    assert token_accesso.verifica(t)["ruolo"] == "cliente"
    # Tentativo di promuoversi ad admin modificando il contenuto: la firma non corrisponde più.
    corpo, firma = t.split(".")
    dati = json.loads(base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4)))
    dati["ruolo"] = "admin"
    falso = base64.urlsafe_b64encode(json.dumps(dati).encode()).rstrip(b"=").decode() + "." + firma
    assert token_accesso.verifica(falso) is None
    assert token_accesso.verifica("spazzatura") is None
    monkeypatch.setenv("RISTO_SECRET", "altro-segreto")
    assert token_accesso.verifica(t) is None


def test_token_scaduto(db, monkeypatch):
    monkeypatch.setenv("RISTO_SECRET", "segreto-di-test")
    assert token_accesso.verifica(token_accesso.emetti(1, "admin", durata_s=-1)) is None


# ------------------------------------------------------------------ permessi


def test_tabella_permessi():
    assert permessi.puo("admin", "aggiorna_scorta")
    assert not permessi.puo("cliente", "aggiorna_scorta")
    assert not permessi.puo("cucina", "crea_prenotazione")
    assert permessi.puo("cucina", "aggiorna_stato_ordine")
    assert not permessi.puo("cliente", "prenotazioni_del_giorno")
    assert permessi.puo("ospite", "cerca_menu")
    assert not permessi.puo("ruolo_inventato", "cerca_menu")
    assert "aggiorna_scorta" not in permessi.tool_consentiti("sala")


# ------------------------------------------------------------------ proprietà dei dati


def test_cliente_vede_solo_le_proprie_prenotazioni(db):
    conn, info = db
    giulia, luca = utente(conn, "giulia"), utente(conn, "luca")
    mie = prenotazioni.trova_prenotazioni(conn, utente=giulia)
    assert mie and all(p["telefono"] == "3331234567" for p in mie)
    # Anche cercando per data o nome di altri, il filtro di proprietà resta.
    assert prenotazioni.trova_prenotazioni(conn, data="2026-12-05", utente=luca) == []


def test_cliente_non_modifica_prenotazioni_altrui(db):
    conn, info = db
    luca = utente(conn, "luca")
    with pytest.raises(ErroreDominio) as exc:
        prenotazioni.cancella_prenotazione(conn, info["prenotazione_riferimento"], "3331234567", utente=luca)
    assert exc.value.codice == "PRENOTAZIONE_INESISTENTE"  # nemmeno conoscendo il telefono


def test_cliente_modifica_la_propria_senza_telefono(db):
    conn, info = db
    p = prenotazioni.modifica_prenotazione(conn, info["prenotazione_riferimento"], None, ora="21:00",
                                           utente=utente(conn, "giulia"))
    assert p["ora"] == "21:00"


def test_sala_opera_su_tutte(db):
    conn, info = db
    sala = utente(conn, "sala")
    assert prenotazioni.cancella_prenotazione(conn, info["prenotazione_riferimento"], None, utente=sala)["stato"] == "cancellata"
    quadro = prenotazioni.prenotazioni_del_giorno(conn, "sabato")
    assert quadro["numero_prenotazioni"] == 15 and quadro["coperti_cena"] > 0


def test_cliente_registrato_prenota_con_i_dati_del_profilo(db):
    conn, _ = db
    giulia = utente(conn, "giulia")
    p = prenotazioni.crea_prenotazione(conn, "domani", "20:00", 2, None, None, utente=giulia)
    assert p["nome_cliente"] == "Giulia Ferri" and p["telefono"] == "3331234567"
    riga = conn.execute("SELECT id_utente FROM PRENOTAZIONI WHERE id_prenotazione = ?", (p["id_prenotazione"],)).fetchone()
    assert riga[0] == giulia.id_utente


def test_ospite_senza_telefono_rifiutato(db):
    conn, _ = db
    with pytest.raises(ErroreDominio) as exc:
        prenotazioni.crea_prenotazione(conn, "domani", "20:00", 2, "Anna", None)
    assert exc.value.codice == "TELEFONO_MANCANTE"


def test_ordini_proprieta_e_stati(db):
    conn, info = db
    luca, giulia, cucina = utente(conn, "luca"), utente(conn, "giulia"), utente(conn, "cucina")
    id_ordine = info["ordine_riferimento"]
    assert ordini.stato_ordine(conn, id_ordine, utente=luca)["stato"] == "in_preparazione"
    with pytest.raises(ErroreDominio):
        ordini.stato_ordine(conn, id_ordine, "3471112233", utente=giulia)
    assert ordini.stato_ordine(conn, id_ordine, utente=cucina)["nome_cliente"] == "Luca Bianchi"
    assert ordini.ordini_da_preparare(conn)["numero_ordini"] == 1
    assert ordini.aggiorna_stato_ordine(conn, id_ordine, "pronto")["stato"] == "pronto"
    with pytest.raises(ErroreDominio) as exc:
        ordini.aggiorna_stato_ordine(conn, id_ordine, "in_preparazione")
    assert exc.value.codice == "TRANSIZIONE_NON_AMMESSA"


def test_servizi_amministratore(db):
    conn, _ = db
    r = menu.aggiorna_scorta(conn, "tartufo", 100)
    assert r["ingrediente"] == "tartufo nero" and r["quantita_attuale"] == 125
    tartufo = menu.trova_piatto(conn, "tagliolini al tartufo")
    assert menu.porzioni_disponibili(conn, tartufo) == 12
    assert menu.imposta_disponibilita_piatto(conn, "tiramisù", False)["nel_menu"] is False
    assert "Tiramisù" not in {p["nome"] for p in menu.cerca_menu(conn)["piatti"]}
    assert menu.imposta_disponibilita_piatto(conn, "tiramisù", True)["nel_menu"] is True
