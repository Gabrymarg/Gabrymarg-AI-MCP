"""Storico delle conversazioni: salvataggio, regole di accesso, API e ripresa nell'agente."""

import pytest

from backend import storico
from backend.errori import ErroreDominio
from backend.permessi import Utente


def _utenti(conn):
    righe = conn.execute("SELECT id_utente, username, ruolo, nome FROM UTENTI").fetchall()
    return {r["username"]: Utente(r["id_utente"], r["ruolo"], r["nome"]) for r in righe}


def test_salvataggio_ed_elenco(db):
    conn, _ = db
    u = _utenti(conn)
    c = storico.nuova(conn, u["giulia"].id_utente, "Vorrei prenotare per sabato sera in quattro persone, se c'è posto vicino alla finestra")
    storico.aggiungi(conn, c, "utente", "Vorrei prenotare per sabato")
    storico.aggiungi(conn, c, "assistente", "Prenotazione n. 186 confermata.")
    elenco = storico.elenco(conn, u["giulia"])
    assert len(elenco) == 1 and elenco[0]["numero_messaggi"] == 2 and elenco[0]["propria"]
    assert len(elenco[0]["titolo"]) <= storico.LUNGHEZZA_TITOLO and elenco[0]["titolo"].endswith("…")
    assert storico.elenco(conn, u["luca"]) == []


def test_regole_di_accesso(db):
    conn, _ = db
    u = _utenti(conn)
    c = storico.nuova(conn, u["giulia"].id_utente, "Ciao")
    storico.aggiungi(conn, c, "utente", "Ciao")
    # un altro cliente non la vede: risponde come inesistente
    with pytest.raises(ErroreDominio) as exc:
        storico.leggi(conn, c, u["luca"])
    assert exc.value.codice == "CONVERSAZIONE_INESISTENTE"
    # l'amministratore la legge, ma non può riprenderla né eliminarla
    assert storico.leggi(conn, c, u["admin"])["username"] == "giulia"
    for funzione in (lambda: storico.leggi(conn, c, u["admin"], per_riprendere=True), lambda: storico.elimina(conn, c, u["admin"])):
        with pytest.raises(ErroreDominio):
            funzione()
    # solo l'amministratore può chiedere l'elenco di tutti
    with pytest.raises(ErroreDominio):
        storico.elenco(conn, u["giulia"], tutte=True)
    assert any(x["username"] == "giulia" for x in storico.elenco(conn, u["admin"], tutte=True))
    storico.elimina(conn, c, u["giulia"])
    assert storico.elenco(conn, u["giulia"]) == []


def test_tabelle_create_su_database_esistente(tmp_path):
    from backend.db import connetti

    conn = connetti(tmp_path / "vecchio.db")
    conn.execute("CREATE TABLE UTENTI (id_utente INTEGER PRIMARY KEY)")
    storico.crea_tabelle(conn)
    storico.crea_tabelle(conn)  # idempotente
    nomi = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"CONVERSAZIONI", "MESSAGGI_CHAT"} <= nomi


def test_ripresa_considera_verificati_i_numeri_gia_consegnati():
    from harness.agent import Agent
    from harness.config import Config
    from harness.guardrail import riferimenti_inventati
    from harness.llm.base import Messaggio
    from harness.llm.mock_provider import MockProvider
    from harness.logger import LoggerNullo

    agente = Agent(MockProvider([]), None, lambda *a: True, LoggerNullo(), Config())
    agente.messaggi = [Messaggio("system", "istruzioni")]
    agente.ripristina([("utente", "Prenota per sabato"), ("assistente", "Prenotazione n. 186 confermata.")])
    assert [m.ruolo for m in agente.messaggi] == ["system", "user", "assistant"]
    assert ("prenotazione", 186) in agente.riferimenti_verificati
    citazione = "Ricordo la sua prenotazione n. 186."
    assert riferimenti_inventati(citazione, agente.messaggi, agente.riferimenti_verificati) == []
    assert riferimenti_inventati("La prenotazione n. 187.", agente.messaggi, agente.riferimenti_verificati)
    agente.nuova_conversazione()
    assert agente.riferimenti_verificati == set() and len(agente.messaggi) == 1


def test_api_storico(db, monkeypatch):
    from fastapi.testclient import TestClient

    from backend import token_accesso
    from webapp import app as modulo

    monkeypatch.setenv("RISTO_MCP_ESTERNO", "1")
    conn, _ = db
    u = _utenti(conn)
    c = storico.nuova(conn, u["giulia"].id_utente, "Il tiramisù ha uova?")
    storico.aggiungi(conn, c, "utente", "Il tiramisù ha uova?")
    conn.commit()

    def client(nome):
        cl = TestClient(modulo.app)
        cl.cookies.set(modulo.COOKIE, token_accesso.emetti(u[nome].id_utente, u[nome].ruolo))
        return cl

    with client("giulia") as cl:
        assert [x["id_conversazione"] for x in cl.get("/api/conversazioni").json()] == [c]
        assert cl.get("/api/conversazioni?tutte=true").status_code == 403
        assert cl.get(f"/api/conversazioni/{c}").json()["messaggi"][0]["testo"] == "Il tiramisù ha uova?"
    with client("luca") as cl:
        assert cl.get(f"/api/conversazioni/{c}").status_code == 404
        assert cl.delete(f"/api/conversazioni/{c}").status_code == 404
    with client("admin") as cl:
        assert cl.get(f"/api/conversazioni/{c}").status_code == 200
        assert cl.post(f"/api/conversazioni/{c}/riprendi").status_code == 404  # non è sua
        assert cl.delete(f"/api/conversazioni/{c}").status_code == 404
    with client("giulia") as cl:
        assert cl.delete(f"/api/conversazioni/{c}").status_code == 200
        assert cl.get("/api/conversazioni").json() == []
