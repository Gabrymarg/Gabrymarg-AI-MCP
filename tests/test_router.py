"""Instradamento tra modello locale e modello cloud."""

import json

import pytest

from harness.llm.base import Messaggio
from harness.llm.mock_provider import MockProvider, risposta
from harness.llm.router import RouterProvider, scegli


def U(testo):
    return Messaggio("user", testo)


@pytest.mark.parametrize(
    "testo,destinazione",
    [
        ("Il tiramisù contiene uova?", "cloud"),
        ("Sono celiaco, cosa posso mangiare?", "cloud"),
        ("Che dolci avete?", "locale"),
        ("Siamo in 4 sabato alle 20:30, c'è posto?", "locale"),
        ("Che orari avete domani sera?", "locale"),
        ("Prenota per 2 domani alle 20", "cloud"),
        ("Vorrei cancellare la prenotazione 86", "cloud"),
        ("Vorrei 2 carbonare da asporto per le 20", "cloud"),
        ("Segna pronto l'ordine 1", "cloud"),
        ("È arrivato un carico di tartufo", "cloud"),
        # casi emersi dalla batteria del router (S09 e S15): richieste di scrittura senza le parole chiave iniziali
        ("Prenotate per domani.", "cloud"),
        ("Vorremmo venire lunedì a cena alle 20, in 3.", "cloud"),
        ("Sono Anna Neri, 340 000 1111.", "cloud"),
    ],
)
def test_scelta_per_tipo_di_richiesta(testo, destinazione):
    assert scegli([Messaggio("system", "istruzioni"), U(testo)])[0] == destinazione


def test_seguito_di_una_scrittura_resta_in_cloud():
    messaggi = [U("Vorrei prenotare per 2 domani"), Messaggio("assistant", "A che nome e con quale telefono?"),
                U("Sì, alle 20 va bene")]
    assert scegli(messaggi) == ("cloud", "seguito di una richiesta di modifica dei dati")
    # una domanda nuova dopo una scrittura non resta in cloud per inerzia
    nuova_domanda = [U("Vorrei prenotare per 2 domani"), Messaggio("assistant", "A che nome?"),
                     U("Che dolci avete?")]
    assert scegli(nuova_domanda)[0] == "locale"


def test_scala_al_cloud_dopo_un_errore_o_una_correzione():
    errore = Messaggio("tool", json.dumps({"ok": False, "errore": {"codice": "PIATTO_INESISTENTE"}}))
    assert scegli([U("Il tiramisu ha uova?"), Messaggio("assistant", ""), errore])[0] == "cloud"
    assert scegli([U("Ciao"), Messaggio("assistant", "..."), Messaggio("system", "NOTA INTERNA")])[0] == "cloud"
    annullato = Messaggio("tool", json.dumps({"ok": False, "annullato_da_utente": True}))
    assert scegli([U("Che dolci avete?"), annullato])[0] == "locale"


def test_router_registra_la_scelta_e_ripiega_se_un_modello_non_risponde():
    locale, cloud = MockProvider([risposta("dal locale")]), MockProvider([risposta("dal cloud")])
    router = RouterProvider(locale, cloud)
    r = router.chat([U("Che dolci avete?")], [])
    assert r.testo == "dal locale" and r.instradamento.startswith("locale:")

    class Guasto(MockProvider):
        def chat(self, messaggi, strumenti):
            raise ConnectionError("servizio irraggiungibile")

    router = RouterProvider(Guasto([]), MockProvider([risposta("dal cloud")]))
    r = router.chat([U("Che dolci avete?")], [])
    assert r.testo == "dal cloud" and "ripiego" in r.instradamento


def test_turno_passato_al_cloud_non_torna_al_locale():
    locale = MockProvider([risposta("dal locale")] * 3)
    cloud = MockProvider([risposta("dal cloud")] * 3)

    class GuastoUnaVolta(MockProvider):
        guasto = True

        def chat(self, messaggi, strumenti):
            if self.guasto:
                self.guasto = False
                raise TimeoutError("modello in caricamento")
            return super().chat(messaggi, strumenti)

    router = RouterProvider(GuastoUnaVolta([risposta("dal locale")] * 3), cloud)
    messaggi = [U("Che dolci avete?")]
    assert "ripiego" in router.chat(messaggi, []).instradamento  # il locale non risponde: si passa al cloud
    seconda = router.chat(messaggi + [Messaggio("tool", "{}")], [])  # stesso turno
    assert seconda.testo == "dal cloud" and "già passato" in seconda.instradamento
    nuova = router.chat(messaggi + [Messaggio("assistant", "Ecco."), U("E che orari fate?")], [])
    assert nuova.testo == "dal locale"  # turno nuovo: si riparte dalle regole
