"""Ruoli e permessi: chi può usare quali tool.

È la tabella di autorizzazione dell'intero sistema. La applicano:
  - il server MCP, a ogni chiamata di tool (controllo vincolante);
  - l'harness, che mostra al modello solo i tool consentiti (riduce errori e tentativi inutili).

Il ruolo "ospite" corrisponde all'uso senza login (CLI e scenari via stdio): può usare i tool
pubblici e verifica l'identità del cliente tramite il numero di telefono.
"""

from __future__ import annotations

from dataclasses import dataclass

RUOLI = ("cliente", "sala", "cucina", "admin")
ETICHETTE_RUOLI = {
    "ospite": "Ospite (senza login)",
    "cliente": "Cliente",
    "sala": "Personale di sala",
    "cucina": "Cucina",
    "admin": "Amministratore",
}

TUTTI = {"ospite", "cliente", "sala", "cucina", "admin"}
PUBBLICI = {
    "orari_apertura", "cerca_menu", "dettaglio_piatto", "verifica_disponibilita", "orari_disponibili", "mio_profilo",
}

# tool -> ruoli autorizzati
PERMESSI: dict[str, set[str]] = {
    **{tool: TUTTI for tool in PUBBLICI},
    # prenotazioni: il cliente opera solo sulle proprie, sala e admin su tutte
    "trova_prenotazioni": {"ospite", "cliente", "sala", "admin"},
    "crea_prenotazione": {"ospite", "cliente", "sala", "admin"},
    "modifica_prenotazione": {"ospite", "cliente", "sala", "admin"},
    "cancella_prenotazione": {"ospite", "cliente", "sala", "admin"},
    "prenotazioni_del_giorno": {"sala", "admin"},
    # ordini: il cliente vede e crea solo i propri; cucina e sala li gestiscono
    "crea_ordine_asporto": {"ospite", "cliente", "sala", "admin"},
    "stato_ordine": {"ospite", "cliente", "sala", "cucina", "admin"},
    "ordini_da_preparare": {"sala", "cucina", "admin"},
    "aggiorna_stato_ordine": {"cucina", "sala", "admin"},
    # magazzino e menu: solo amministratore
    "aggiorna_scorta": {"admin"},
    "imposta_disponibilita_piatto": {"admin"},
}

# Ruoli che possono operare su prenotazioni e ordini di chiunque, senza verifica del telefono.
RUOLI_PERSONALE = {"sala", "cucina", "admin"}


@dataclass(frozen=True)
class Utente:
    """Identità di chi sta operando, ricavata dal token (mai dal testo della conversazione)."""

    id_utente: int | None
    ruolo: str
    nome: str = ""
    telefono: str | None = None

    @property
    def personale(self) -> bool:
        return self.ruolo in RUOLI_PERSONALE

    @property
    def cliente_registrato(self) -> bool:
        return self.ruolo == "cliente" and self.id_utente is not None


OSPITE = Utente(id_utente=None, ruolo="ospite")


def puo(ruolo: str, tool: str) -> bool:
    return ruolo in PERMESSI.get(tool, set())


def tool_consentiti(ruolo: str) -> list[str]:
    return sorted(t for t, ruoli in PERMESSI.items() if ruolo in ruoli)
