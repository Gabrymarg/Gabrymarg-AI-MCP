"""Test unitari dei servizi del back-end (regole di business)."""

import pytest

from backend import menu, ordini, prenotazioni
from backend.errori import ErroreDominio
from tests.conftest import id_piatto

TEL_RIF = "3331234567"


def codice_errore(fn, *args, **kwargs):
    with pytest.raises(ErroreDominio) as exc:
        fn(*args, **kwargs)
    return exc.value.codice


# ------------------------------------------------------------------ prenotazioni


def test_disponibilita_domani(db):
    conn, _ = db
    esito = prenotazioni.verifica_disponibilita(conn, "2026-12-04", "20:30", 2)
    assert esito["disponibile"] is True
    assert esito["turno"] == "cena"


def test_sabato_al_completo_propone_alternative(db):
    conn, info = db
    esito = prenotazioni.verifica_disponibilita(conn, info["sabato_completo"], "20:30", 4)
    assert esito["disponibile"] is False
    assert esito["orari_alternativi"] == ["22:00"]


def test_data_passata(db):
    conn, _ = db
    assert codice_errore(prenotazioni.verifica_disponibilita, conn, "2026-12-01", "20:00", 2) == "DATA_PASSATA"


def test_lunedi_chiuso(db):
    conn, _ = db
    assert codice_errore(prenotazioni.verifica_disponibilita, conn, "2026-12-07", "20:00", 2) == "FUORI_ORARIO"


def test_ultima_prenotazione_90_minuti_prima_della_chiusura(db):
    conn, _ = db
    assert prenotazioni.verifica_disponibilita(conn, "2026-12-04", "22:00", 2)["disponibile"]
    assert codice_errore(prenotazioni.verifica_disponibilita, conn, "2026-12-04", "22:30", 2) == "FUORI_ORARIO"


def test_gruppo_troppo_numeroso(db):
    conn, _ = db
    assert (
        codice_errore(prenotazioni.verifica_disponibilita, conn, "2026-12-04", "20:00", 14)
        == "GRUPPO_TROPPO_NUMEROSO"
    )


@pytest.mark.parametrize(
    "espressione,attesa",
    [("domani", "2026-12-04"), ("Dopodomani", "2026-12-05"), ("sabato", "2026-12-05"),
     ("giovedì", "2026-12-03"), ("prossimo martedì", "2026-12-08"), ("oggi", "2026-12-03")],
)
def test_date_relative(db, espressione, attesa):
    from backend.validazione import parse_data

    assert parse_data(espressione).isoformat() == attesa


def test_formato_data_non_valido(db):
    conn, _ = db
    assert codice_errore(prenotazioni.verifica_disponibilita, conn, "04/12/2026", "20:00", 2) == "DATA_NON_VALIDA"


def test_crea_e_trova_prenotazione(db):
    conn, _ = db
    p = prenotazioni.crea_prenotazione(conn, "2026-12-10", "13:00", 3, "Anna Neri", "+39 340 000 1111")
    assert p["stato"] == "confermata"
    assert p["telefono"] == "3400001111"
    trovate = prenotazioni.trova_prenotazioni(conn, telefono="340 0001111")
    assert [t["id_prenotazione"] for t in trovate] == [p["id_prenotazione"]]


def test_trova_senza_filtri(db):
    conn, _ = db
    assert codice_errore(prenotazioni.trova_prenotazioni, conn) == "FILTRO_MANCANTE"


def test_sabato_pieno_non_si_crea(db):
    conn, info = db
    with pytest.raises(ErroreDominio) as exc:
        prenotazioni.crea_prenotazione(conn, info["sabato_completo"], "20:00", 2, "Test", "3330000000")
    assert exc.value.codice == "NESSUN_TAVOLO_LIBERO"
    assert "orari_alternativi" in exc.value.dettagli


def test_modifica_con_telefono_errato(db):
    conn, info = db
    rif = info["prenotazione_riferimento"]
    assert (
        codice_errore(prenotazioni.modifica_prenotazione, conn, rif, "3999999999", ora="21:00")
        == "PRENOTAZIONE_INESISTENTE"
    )


def test_modifica_orario_e_coperti(db):
    conn, info = db
    rif = info["prenotazione_riferimento"]
    p = prenotazioni.modifica_prenotazione(conn, rif, TEL_RIF, ora="21:00", coperti=4)
    assert (p["ora"], p["coperti"]) == ("21:00", 4)


def test_cancella_poi_non_modificabile(db):
    conn, info = db
    rif = info["prenotazione_riferimento"]
    assert prenotazioni.cancella_prenotazione(conn, rif, TEL_RIF)["stato"] == "cancellata"
    assert codice_errore(prenotazioni.cancella_prenotazione, conn, rif, TEL_RIF) == "PRENOTAZIONE_NON_MODIFICABILE"


# ------------------------------------------------------------------ menu


def test_menu_senza_glutine(db):
    conn, _ = db
    piatti = menu.cerca_menu(conn, escludi_allergeni=["glutine"])["piatti"]
    assert piatti and all("glutine" not in p["allergeni"] for p in piatti)
    assert "Torta al cioccolato senza glutine" in {p["nome"] for p in piatti}


def test_allergene_sinonimo_e_sconosciuto(db):
    conn, _ = db
    piatti = menu.cerca_menu(conn, escludi_allergeni=["Lattosio"])["piatti"]
    assert all("latte" not in p["allergeni"] for p in piatti)
    assert codice_errore(menu.cerca_menu, conn, escludi_allergeni=["kryptonite"]) == "ALLERGENE_SCONOSCIUTO"


def test_categoria_sconosciuta(db):
    conn, _ = db
    assert codice_errore(menu.cerca_menu, conn, categoria="Pizze") == "CATEGORIA_SCONOSCIUTA"


def test_branzino_esaurito(db):
    conn, _ = db
    d = menu.dettaglio_piatto(conn, id_piatto(conn, "Branzino al forno con patate"))
    assert d["porzioni_disponibili"] == 0


# ------------------------------------------------------------------ ordini


def test_ordine_tartufo_scorte(db):
    conn, _ = db
    tartufo = id_piatto(conn, "Tagliolini al tartufo nero")
    with pytest.raises(ErroreDominio) as exc:
        ordini.crea_ordine_asporto(conn, "Mario", "3330001111", [{"id_articolo": tartufo, "quantita": 3}], "20:00")
    assert exc.value.codice == "SCORTE_INSUFFICIENTI"
    assert exc.value.dettagli["porzioni_disponibili"]["Tagliolini al tartufo nero"] == 2
    o = ordini.crea_ordine_asporto(conn, "Mario", "3330001111", [{"id_articolo": tartufo, "quantita": 2}], "20:00")
    assert o["totale"] == 44.0
    assert menu.dettaglio_piatto(conn, tartufo)["porzioni_disponibili"] == 0


def test_ordine_piatto_non_da_asporto(db):
    conn, _ = db
    frittura = id_piatto(conn, "Frittura di calamari e gamberi")
    assert (
        codice_errore(ordini.crea_ordine_asporto, conn, "Mario", "3330001111", [{"id_articolo": frittura}], "20:00")
        == "NON_DISPONIBILE_ASPORTO"
    )


def test_ritiro_troppo_presto(db):
    conn, _ = db
    tiramisu = id_piatto(conn, "Tiramisù")
    assert (
        codice_errore(ordini.crea_ordine_asporto, conn, "Mario", "3330001111", [{"id_articolo": tiramisu}], "11:10")
        == "RITIRO_TROPPO_PRESTO"
    )


def test_stato_ordine(db):
    conn, info = db
    o = ordini.stato_ordine(conn, info["ordine_riferimento"], "347 111 2233")
    assert o["stato"] == "in_preparazione"
    assert codice_errore(ordini.stato_ordine, conn, info["ordine_riferimento"], "3330000000") == "ORDINE_INESISTENTE"
