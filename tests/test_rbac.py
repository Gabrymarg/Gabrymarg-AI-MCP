"""Permessi dei ruoli modificabili dall'amministratore (RBAC) e vincoli che il codice impone comunque."""

import pytest

from backend import permessi
from backend.permessi import PermessoNonModificabile, Utente


def _admin(conn):
    r = conn.execute("SELECT id_utente FROM UTENTI WHERE username = 'admin'").fetchone()
    return Utente(r[0], "admin", "Amministratore")


def test_predefiniti_nel_database_nuovo(db):
    conn, _ = db
    assert permessi.carica(conn) == {t: set(r) | {"admin"} for t, r in permessi.PERMESSI_PREDEFINITI.items()}
    assert permessi.registro(conn) == []


def test_admin_concede_e_revoca_con_registro(db):
    conn, _ = db
    admin = _admin(conn)
    tabella = permessi.imposta(conn, admin, "sala", "aggiorna_scorta", True)
    assert permessi.puo("sala", "aggiorna_scorta", tabella)
    tabella = permessi.imposta(conn, admin, "cucina", "stato_ordine", False)
    assert not permessi.puo("cucina", "stato_ordine", tabella)
    registro = permessi.registro(conn)
    assert [(m["azione"], m["ruolo"], m["tool"]) for m in registro] == [
        ("revocato", "cucina", "stato_ordine"), ("concesso", "sala", "aggiorna_scorta")]
    assert registro[0]["username"] == "admin"
    # una modifica che non cambia nulla non viene registrata
    permessi.imposta(conn, admin, "sala", "aggiorna_scorta", True)
    assert len(permessi.registro(conn)) == 2
    tabella = permessi.ripristina(conn, admin)
    assert not permessi.puo("sala", "aggiorna_scorta", tabella) and permessi.puo("cucina", "stato_ordine", tabella)
    assert permessi.registro(conn)[0]["azione"] == "ripristino"


@pytest.mark.parametrize("ruolo,tool,consentito", [
    ("admin", "aggiorna_scorta", False),          # l'admin non perde mai i permessi
    ("cliente", "aggiorna_scorta", True),         # strumenti interni mai ai clienti
    ("ospite", "prenotazioni_del_giorno", True),  # ...né agli ospiti
    ("sala", "mio_profilo", False),               # sempre disponibile
    ("sala", "strumento_inventato", True),        # tool sconosciuto
    ("ruolo_inventato", "cerca_menu", True),      # ruolo sconosciuto
])
def test_vincoli_del_codice(db, ruolo, tool, consentito):
    conn, _ = db
    with pytest.raises(PermessoNonModificabile):
        permessi.imposta(conn, _admin(conn), ruolo, tool, consentito)


def test_solo_admin_modifica(db):
    conn, _ = db
    sala = Utente(5, "sala")
    with pytest.raises(PermissionError):
        permessi.imposta(conn, sala, "sala", "aggiorna_scorta", True)
    with pytest.raises(PermissionError):
        permessi.ripristina(conn, sala)


def test_database_manomesso_non_supera_i_vincoli(db):
    conn, _ = db
    # qualcuno scrive direttamente nel database, aggirando l'applicazione
    conn.execute("DELETE FROM PERMESSI_RUOLI WHERE ruolo = 'admin'")
    conn.execute("INSERT INTO PERMESSI_RUOLI (ruolo, tool) VALUES ('cliente', 'aggiorna_scorta')")
    conn.execute("INSERT INTO PERMESSI_RUOLI (ruolo, tool) VALUES ('cliente', 'strumento_segreto')")
    tabella = permessi.carica(conn)
    assert not permessi.puo("cliente", "aggiorna_scorta", tabella)
    assert permessi.puo("admin", "aggiorna_scorta", tabella)
    assert "strumento_segreto" not in tabella


def test_database_senza_tabella_usa_i_predefiniti(tmp_path):
    from backend.db import connetti

    conn = connetti(tmp_path / "vecchio.db")
    assert permessi.carica(conn) == {t: set(r) for t, r in permessi.PERMESSI_PREDEFINITI.items()}


def test_api_permessi(db, monkeypatch):
    from fastapi.testclient import TestClient

    from backend import token_accesso
    from webapp import app as modulo

    monkeypatch.setenv("RISTO_MCP_ESTERNO", "1")
    conn, _ = db
    ids = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT username, id_utente, ruolo FROM UTENTI")}

    def client(nome):
        c = TestClient(modulo.app)
        c.cookies.set(modulo.COOKIE, token_accesso.emetti(*ids[nome]))
        return c

    with client("sala") as c:
        assert c.get("/api/admin/permessi").status_code == 403
        assert c.put("/api/admin/permessi", json={"ruolo": "sala", "tool": "aggiorna_scorta", "consentito": True}).status_code == 403
    with client("admin") as c:
        matrice = c.get("/api/admin/permessi").json()
        scorta = next(s for s in matrice["strumenti"] if s["nome"] == "aggiorna_scorta")
        assert scorta["scrittura"] and scorta["ruoli"]["cliente"]["bloccato"] and not scorta["ruoli"]["sala"]["bloccato"]
        r = c.put("/api/admin/permessi", json={"ruolo": "sala", "tool": "aggiorna_scorta", "consentito": True})
        assert r.status_code == 200 and r.json()["registro"][0]["azione"] == "concesso"
        assert c.put("/api/admin/permessi", json={"ruolo": "cliente", "tool": "aggiorna_scorta", "consentito": True}).status_code == 400
        assert c.post("/api/admin/permessi/ripristina").json()["registro"][0]["azione"] == "ripristino"
