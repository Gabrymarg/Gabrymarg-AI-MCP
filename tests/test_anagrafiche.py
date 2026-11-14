"""Anagrafiche del menu (categorie, ingredienti, articoli), giacenze e relative API della web app."""

import pytest

from backend import anagrafiche, menu, permessi
from backend.errori import ErroreDominio


def _errore(funzione, *argomenti, **opzioni) -> str:
    with pytest.raises(ErroreDominio) as exc:
        funzione(*argomenti, **opzioni)
    return exc.value.codice


# ------------------------------------------------------------------ giacenze (tool MCP)


def test_giacenze_ingredienti(db):
    conn, _ = db
    tutte = menu.giacenze_ingredienti(conn)
    assert tutte["numero_ingredienti"] == conn.execute("SELECT COUNT(*) FROM INGREDIENTI").fetchone()[0]
    tartufo = menu.giacenze_ingredienti(conn, testo="tartufo")["ingredienti"]
    assert [i["ingrediente"] for i in tartufo] == ["tartufo nero"]
    conn.execute("UPDATE INGREDIENTI SET quantita_disponibile = 0, scorta_minima = 50 WHERE nome = 'tartufo nero'")
    sotto = menu.giacenze_ingredienti(conn, solo_sotto_scorta=True)
    assert "tartufo nero" in {i["ingrediente"] for i in sotto["ingredienti"]}
    assert all(i["sotto_scorta_minima"] for i in sotto["ingredienti"])
    assert sotto["sotto_scorta"] == sotto["numero_ingredienti"]


def test_permessi_giacenze():
    assert permessi.puo("cucina", "giacenze_ingredienti")
    assert permessi.puo("admin", "giacenze_ingredienti")
    assert not permessi.puo("cliente", "giacenze_ingredienti")
    assert not permessi.puo("sala", "giacenze_ingredienti")
    assert not permessi.puo("cucina", "aggiorna_scorta")


# ------------------------------------------------------------------ categorie


def test_categorie(db):
    conn, _ = db
    nuova = anagrafiche.salva_categoria(conn, "Pizze")
    assert nuova["numero_articoli"] == 0 and nuova["ordine"] == max(c["ordine"] for c in anagrafiche.elenco_categorie(conn))
    assert _errore(anagrafiche.salva_categoria, conn, "pizze") == "NOME_GIA_USATO"
    rinominata = anagrafiche.salva_categoria(conn, "Pizze al forno", 0, nuova["id_categoria"])
    assert rinominata["nome"] == "Pizze al forno" and rinominata["ordine"] == 0
    anagrafiche.elimina_categoria(conn, nuova["id_categoria"])
    assert "Pizze al forno" not in {c["nome"] for c in anagrafiche.elenco_categorie(conn)}


def test_categoria_con_articoli_non_si_elimina(db):
    conn, _ = db
    piena = next(c for c in anagrafiche.elenco_categorie(conn) if c["numero_articoli"] > 0)
    assert _errore(anagrafiche.elimina_categoria, conn, piena["id_categoria"]) == "CATEGORIA_IN_USO"


# ------------------------------------------------------------------ ingredienti


def test_ingredienti(db):
    conn, _ = db
    nuovo = anagrafiche.salva_ingrediente(conn, "curcuma", "g", 10, 20)
    assert nuovo["sotto_scorta_minima"] and nuovo["numero_ricette"] == 0
    assert _errore(anagrafiche.salva_ingrediente, conn, "Curcuma", "g", 1) == "NOME_GIA_USATO"
    assert _errore(anagrafiche.salva_ingrediente, conn, "sale grosso", "kg", 1) == "UNITA_NON_VALIDA"
    assert _errore(anagrafiche.salva_ingrediente, conn, "sale grosso", "g", -1) == "QUANTITA_NON_VALIDA"
    aggiornato = anagrafiche.salva_ingrediente(conn, "curcuma", "g", 50, 20, nuovo["id_ingrediente"])
    assert not aggiornato["sotto_scorta_minima"]
    anagrafiche.elimina_ingrediente(conn, nuovo["id_ingrediente"])


def test_ingrediente_usato_in_ricetta_non_si_elimina(db):
    conn, _ = db
    usato = next(i for i in anagrafiche.elenco_ingredienti(conn) if i["numero_ricette"] > 0)
    assert _errore(anagrafiche.elimina_ingrediente, conn, usato["id_ingrediente"]) == "INGREDIENTE_IN_USO"


# ------------------------------------------------------------------ articoli


def test_nuovo_articolo_con_ricetta_e_allergeni(db):
    conn, _ = db
    categoria = anagrafiche.elenco_categorie(conn)[0]["id_categoria"]
    curcuma = anagrafiche.salva_ingrediente(conn, "curcuma", "g", 10)
    a = anagrafiche.salva_articolo(
        conn, "Risotto alla curcuma", "Carnaroli, curcuma e burro", 14, categoria,
        vegetariano=True, allergeni=["latte"], ricetta=[{"id_ingrediente": curcuma["id_ingrediente"], "quantita": 0.5}],
    )
    assert a["allergeni"] == ["latte"] and a["ricetta"][0]["nome"] == "curcuma"
    # Il nuovo piatto è subito visibile all'agente, con allergeni e porzioni calcolate dalle scorte.
    dettaglio = menu.dettaglio_piatto(conn, nome="risotto alla curcuma")
    assert dettaglio["allergeni"] == ["latte"] and dettaglio["porzioni_disponibili"] == 20

    tolto = anagrafiche.salva_articolo(
        conn, a["nome"], a["descrizione"], 15, categoria, attivo=False, allergeni=[], ricetta=[], id_articolo=a["id_articolo"],
    )
    assert not tolto["attivo"] and tolto["allergeni"] == [] and tolto["ricetta"] == []
    assert "Risotto alla curcuma" not in {p["nome"] for p in menu.cerca_menu(conn)["piatti"]}


def test_articolo_validato(db):
    conn, _ = db
    categoria = anagrafiche.elenco_categorie(conn)[0]["id_categoria"]
    esistente = anagrafiche.elenco_articoli(conn)[0]["nome"]
    assert _errore(anagrafiche.salva_articolo, conn, esistente, "x", 10, categoria) == "NOME_GIA_USATO"
    assert _errore(anagrafiche.salva_articolo, conn, "Nuovo", "x", -1, categoria) == "PREZZO_NON_VALIDO"
    assert _errore(anagrafiche.salva_articolo, conn, "Nuovo", "x", 10, 999) == "NON_TROVATO"
    assert _errore(anagrafiche.salva_articolo, conn, "Nuovo", "x", 10, categoria, allergeni=["pepe"]) == "ALLERGENE_SCONOSCIUTO"
    assert _errore(
        anagrafiche.salva_articolo, conn, "Nuovo", "x", 10, categoria,
        ricetta=[{"id_ingrediente": 1, "quantita": 10}, {"id_ingrediente": 1, "quantita": 5}],
    ) == "INGREDIENTE_DUPLICATO"


# ------------------------------------------------------------------ API della web app


@pytest.fixture
def web(db, monkeypatch):
    from fastapi.testclient import TestClient

    from backend import token_accesso
    from webapp import app as modulo

    monkeypatch.setenv("RISTO_MCP_ESTERNO", "1")  # il server MCP non serve per queste API
    conn, _ = db
    ids = {r["username"]: r["id_utente"] for r in conn.execute("SELECT username, id_utente FROM UTENTI")}

    def client(username):
        c = TestClient(modulo.app)
        c.cookies.set(modulo.COOKIE, token_accesso.emetti(ids[username], username if username != "giulia" else "cliente"))
        return c

    return client


def test_api_anagrafiche_solo_admin(web):
    with web("cucina") as c:
        assert c.get("/api/admin/menu").status_code == 403
        assert c.post("/api/admin/categorie", json={"nome": "Abusiva"}).status_code == 403
    with web("giulia") as c:
        assert c.get("/api/admin/menu").status_code == 403


def test_api_anagrafiche_admin(web):
    with web("admin") as c:
        dati = c.get("/api/admin/menu").json()
        assert {"categorie", "ingredienti", "articoli", "allergeni"} <= dati.keys() and len(dati["allergeni"]) == 14
        r = c.post("/api/admin/ingredienti", json={"nome": "curcuma", "unita_misura": "g", "quantita_disponibile": 5})
        assert r.status_code == 201
        id_ing = r.json()["id_ingrediente"]
        doppio = c.post("/api/admin/ingredienti", json={"nome": "curcuma", "unita_misura": "g", "quantita_disponibile": 5})
        assert doppio.status_code == 400 and "già" in doppio.json()["detail"]
        articolo = {
            "nome": "Risotto alla curcuma", "descrizione": "Carnaroli e curcuma", "prezzo": 14,
            "id_categoria": dati["categorie"][0]["id_categoria"], "allergeni": ["latte"],
            "ricetta": [{"id_ingrediente": id_ing, "quantita": 0.5}],
        }
        creato = c.post("/api/admin/articoli", json=articolo).json()
        assert c.put(f"/api/admin/articoli/{creato['id_articolo']}", json={**articolo, "prezzo": 15}).json()["prezzo"] == 15
        assert c.delete(f"/api/admin/ingredienti/{id_ing}").status_code == 400  # usato nella ricetta
