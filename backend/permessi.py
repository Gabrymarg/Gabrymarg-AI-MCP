"""Ruoli e permessi: chi può usare quali tool (RBAC, Role-Based Access Control).

È la tabella di autorizzazione dell'intero sistema. La applicano:
  - il server MCP, a ogni chiamata di tool (controllo vincolante);
  - l'harness, che mostra al modello solo i tool consentiti (riduce errori e tentativi inutili).

Dove stanno le regole:
  - il DATABASE (tabella PERMESSI_RUOLI) contiene i permessi correnti, che l'amministratore può modificare
    dalla web app; ogni modifica è registrata in REGISTRO_PERMESSI (chi, quando, cosa);
  - il CODICE (questo modulo) contiene i permessi predefiniti e i VINCOLI che nessuna modifica nel database
    può superare, perché vengono riapplicati a ogni lettura:
      * l'amministratore ha sempre tutti i permessi (nessuno può chiudersi fuori dal sistema);
      * gli strumenti interni del personale non sono mai concessi a clienti e ospiti;
      * mio_profilo è sempre disponibile;
      * un tool sconosciuto è negato a tutti (fail-safe: negato per impostazione predefinita).

Il ruolo "ospite" corrisponde all'uso senza login (CLI e scenari via stdio): può usare i tool
pubblici e verifica l'identità del cliente tramite il numero di telefono.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

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

# Permessi predefiniti: tool -> ruoli autorizzati. Sono il punto di partenza e il "ripristina" del pannello.
PERMESSI_PREDEFINITI: dict[str, set[str]] = {
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
    # magazzino e menu: la cucina consulta le giacenze, solo l'amministratore modifica
    "giacenze_ingredienti": {"cucina", "admin"},
    "aggiorna_scorta": {"admin"},
    "imposta_disponibilita_piatto": {"admin"},
}
PERMESSI = PERMESSI_PREDEFINITI  # nome storico, usato dalla documentazione generata

# Vincoli non modificabili dal database.
SEMPRE_CONSENTITI = {"mio_profilo"}
SOLO_PERSONALE = {  # strumenti interni: mai a clienti e ospiti, qualunque cosa contenga il database
    "prenotazioni_del_giorno", "ordini_da_preparare", "aggiorna_stato_ordine",
    "giacenze_ingredienti", "aggiorna_scorta", "imposta_disponibilita_piatto",
}
RUOLI_ESTERNI = {"ospite", "cliente"}
TOOL_SCRITTURA = {
    "crea_prenotazione", "modifica_prenotazione", "cancella_prenotazione", "crea_ordine_asporto",
    "aggiorna_stato_ordine", "aggiorna_scorta", "imposta_disponibilita_piatto",
}

# Ruoli che possono operare su prenotazioni e ordini di chiunque, senza verifica del telefono.
RUOLI_PERSONALE = {"sala", "cucina", "admin"}


class PermessoNonModificabile(ValueError):
    """Modifica che violerebbe un vincolo scritto nel codice."""


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


# --------------------------------------------------------------------------- vincoli


def motivo_blocco(ruolo: str, tool: str) -> str | None:
    """Perché un permesso non è modificabile (None se è modificabile)."""
    if ruolo == "admin":
        return "L'amministratore ha sempre tutti i permessi."
    if tool in SEMPRE_CONSENTITI:
        return "Strumento sempre disponibile a tutti."
    if ruolo in RUOLI_ESTERNI and tool in SOLO_PERSONALE:
        return "Strumento interno del personale: non può essere concesso a clienti e ospiti."
    return None


def _applica_vincoli(tabella: dict[str, set[str]]) -> dict[str, set[str]]:
    """Riapplica i vincoli del codice a una tabella letta dal database (anche se manomessa)."""
    risultato = {}
    for tool in PERMESSI_PREDEFINITI:  # i tool sconosciuti nel database vengono ignorati (fail-safe)
        ruoli = set(tabella.get(tool, set())) & TUTTI
        if tool in SOLO_PERSONALE:
            ruoli -= RUOLI_ESTERNI
        ruoli.add("admin")
        if tool in SEMPRE_CONSENTITI:
            ruoli |= TUTTI
        risultato[tool] = ruoli
    return risultato


# --------------------------------------------------------------------------- lettura


def puo(ruolo: str, tool: str, tabella: dict[str, set[str]] | None = None) -> bool:
    """Il ruolo può usare il tool? Con tabella=None valgono i permessi predefiniti."""
    return ruolo in (tabella if tabella is not None else PERMESSI_PREDEFINITI).get(tool, set())


def tool_consentiti(ruolo: str, tabella: dict[str, set[str]] | None = None) -> list[str]:
    tabella = tabella if tabella is not None else PERMESSI_PREDEFINITI
    return sorted(t for t, ruoli in tabella.items() if ruolo in ruoli)


def carica(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """Permessi correnti dal database, con i vincoli del codice riapplicati.

    Se la tabella non esiste o è vuota (database precedente ai permessi modificabili) valgono i predefiniti.
    """
    try:
        righe = conn.execute("SELECT ruolo, tool FROM PERMESSI_RUOLI").fetchall()
    except sqlite3.OperationalError:
        righe = []
    if not righe:
        return {t: set(r) for t, r in PERMESSI_PREDEFINITI.items()}
    tabella: dict[str, set[str]] = {}
    for ruolo, tool in righe:
        tabella.setdefault(tool, set()).add(ruolo)
    return _applica_vincoli(tabella)


# --------------------------------------------------------------------------- scrittura (solo admin)


def _scrivi_tabella(conn: sqlite3.Connection, tabella: dict[str, set[str]]) -> None:
    conn.execute("DELETE FROM PERMESSI_RUOLI")
    conn.executemany(
        "INSERT INTO PERMESSI_RUOLI (ruolo, tool) VALUES (?, ?)",
        [(ruolo, tool) for tool, ruoli in tabella.items() for ruolo in sorted(ruoli)],
    )


def crea_tabelle(conn: sqlite3.Connection) -> None:
    """Crea le tabelle se mancano e, se vuote, le popola con i permessi predefiniti."""
    from backend.db import SCHEMA

    schema = SCHEMA.read_text(encoding="utf-8")
    conn.executescript(schema[schema.index("CREATE TABLE IF NOT EXISTS PERMESSI_RUOLI"):])
    if conn.execute("SELECT COUNT(*) FROM PERMESSI_RUOLI").fetchone()[0] == 0:
        _scrivi_tabella(conn, _applica_vincoli(PERMESSI_PREDEFINITI))


def _verifica_admin(admin: Utente) -> None:
    if admin.ruolo != "admin":
        raise PermissionError("Solo l'amministratore può modificare i permessi.")


def _registra(conn: sqlite3.Connection, admin: Utente, azione: str, ruolo: str | None = None,
              tool: str | None = None) -> None:
    riga = conn.execute("SELECT username FROM UTENTI WHERE id_utente = ?", (admin.id_utente,)).fetchone()
    conn.execute(
        "INSERT INTO REGISTRO_PERMESSI (quando, id_utente, username, ruolo, tool, azione) VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), admin.id_utente, riga[0] if riga else "?", ruolo, tool, azione),
    )


def imposta(conn: sqlite3.Connection, admin: Utente, ruolo: str, tool: str, consentito: bool) -> dict[str, set[str]]:
    """Concede o revoca un permesso. Solo l'amministratore; i vincoli del codice non si possono superare."""
    _verifica_admin(admin)
    if ruolo not in TUTTI:
        raise PermessoNonModificabile(f"Ruolo sconosciuto: {ruolo}.")
    if tool not in PERMESSI_PREDEFINITI:
        raise PermessoNonModificabile(f"Strumento sconosciuto: {tool}.")
    if motivo := motivo_blocco(ruolo, tool):
        raise PermessoNonModificabile(motivo)
    crea_tabelle(conn)
    tabella = carica(conn)
    if (ruolo in tabella[tool]) == consentito:
        return tabella  # nessun cambiamento: niente da registrare
    if consentito:
        tabella[tool].add(ruolo)
    else:
        tabella[tool].discard(ruolo)
    _scrivi_tabella(conn, _applica_vincoli(tabella))
    _registra(conn, admin, "concesso" if consentito else "revocato", ruolo, tool)
    return carica(conn)


def ripristina(conn: sqlite3.Connection, admin: Utente) -> dict[str, set[str]]:
    """Riporta i permessi ai valori predefiniti del codice."""
    _verifica_admin(admin)
    crea_tabelle(conn)
    _scrivi_tabella(conn, _applica_vincoli(PERMESSI_PREDEFINITI))
    _registra(conn, admin, "ripristino")
    return carica(conn)


def registro(conn: sqlite3.Connection, limite: int = 30) -> list[dict]:
    try:
        righe = conn.execute(
            "SELECT quando, username, ruolo, tool, azione FROM REGISTRO_PERMESSI ORDER BY id_modifica DESC LIMIT ?",
            (limite,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [{"quando": r[0], "username": r[1], "ruolo": r[2], "tool": r[3], "azione": r[4]} for r in righe]
