"""Server MCP di Osteria del Borgo.

Espone le funzionalità del sistema informativo (menu, prenotazioni, ordini da asporto)
come tool MCP, con schema dei parametri e annotazioni sugli effetti:
- readOnlyHint=True  -> il tool legge soltanto;
- readOnlyHint=False -> il tool scrive sui dati (l'harness chiederà conferma all'utente);
- destructiveHint    -> la scrittura annulla/sovrascrive dati esistenti.

Avvio (trasporto stdio):  python -m mcp_server.server

Iniezione di guasti (solo per i test): la variabile d'ambiente RISTO_GUASTI contiene
un elenco di nomi di tool separati da virgola che falliscono simulando un database
non raggiungibile.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import timedelta
from functools import wraps
from pathlib import Path
from typing import Annotated, Any, Callable

from pydantic import Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from backend import clock, menu, ordini, prenotazioni  # noqa: E402
from backend.db import connessione  # noqa: E402
from backend.errori import ErroreDominio  # noqa: E402
from backend.orari import descrizione_orari  # noqa: E402
from mcp_server.schemas import (  # noqa: E402
    DettaglioPiatto,
    Disponibilita,
    ElencoPrenotazioni,
    OrariApertura,
    Ordine,
    Prenotazione,
    RigaOrdineIn,
    RisultatoMenu,
)

mcp = MCPServer(
    name="osteria-del-borgo",
    version="1.0.0",
    instructions=(
        "Sistema informativo del ristorante Osteria del Borgo: menu e allergeni, "
        "prenotazioni dei tavoli e ordini da asporto. Le date sono nel formato AAAA-MM-GG, "
        "le ore nel formato HH:MM."
    ),
)

DESCR_DATA = (
    "Data AAAA-MM-GG, oppure direttamente le parole dell'utente 'oggi', 'domani', 'dopodomani' "
    "o il nome del giorno (es. 'sabato'): il sistema le converte nella data corretta."
)

LETTURA = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
SCRITTURA = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
SCRITTURA_DISTRUTTIVA = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False
)


def _guasto_simulato(nome_tool: str) -> None:
    guasti = {g.strip() for g in os.environ.get("RISTO_GUASTI", "").split(",") if g.strip()}
    if nome_tool in guasti or "*" in guasti:
        raise sqlite3.OperationalError("database is locked")


def gestisci_errori(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Converte gli errori di dominio in ToolError con un messaggio JSON leggibile dal modello.

    Gli errori imprevisti (es. database non raggiungibile) sono lasciati propagare:
    l'SDK li trasforma in un risultato di errore generico, senza esporre dettagli interni.
    """

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        _guasto_simulato(fn.__name__)
        try:
            return fn(*args, **kwargs)
        except ErroreDominio as e:
            raise ToolError(json.dumps({"errore": e.to_dict()}, ensure_ascii=False)) from None

    return wrapper


# ============================================================================ informazioni


@mcp.tool(annotations=LETTURA)
@gestisci_errori
def orari_apertura() -> OrariApertura:
    """Restituisce la data e l'ora attuali e gli orari di apertura del ristorante per ogni giorno della settimana.
    Usare per domande sugli orari o per sapere che giorno è oggi."""
    adesso = clock.adesso()
    lunedi = adesso.date() - timedelta(days=adesso.weekday())
    with connessione() as conn:
        settimana = [descrizione_orari(conn, lunedi + timedelta(days=i)) for i in range(7)]
    return OrariApertura(oggi=adesso.isoformat(timespec="minutes"), settimana=settimana)


# ============================================================================ menu


@mcp.tool(annotations=LETTURA)
@gestisci_errori
def cerca_menu(
    testo: Annotated[str | None, Field(description="Parola da cercare nel nome o nella descrizione (es. 'carbonara').")] = None,
    categoria: Annotated[
        str | None, Field(description="Antipasti, Primi, Secondi, Contorni, Dolci o Bevande.")
    ] = None,
    escludi_allergeni: Annotated[
        list[str] | None,
        Field(description="Allergeni da escludere, es. ['glutine', 'latte']. Codici: glutine, crostacei, uova, pesce, "
              "arachidi, soia, latte, frutta_a_guscio, sedano, senape, sesamo, solfiti, lupini, molluschi."),
    ] = None,
    solo_vegetariani: Annotated[bool, Field(description="True per mostrare solo piatti vegetariani.")] = False,
    solo_asporto: Annotated[bool, Field(description="True per mostrare solo piatti ordinabili da asporto.")] = False,
) -> RisultatoMenu:
    """Cerca i piatti del menu con filtri opzionali. Senza filtri restituisce l'intero menu.
    Ogni piatto riporta prezzo, allergeni e disponibilità."""
    with connessione() as conn:
        return RisultatoMenu(
            **menu.cerca_menu(conn, testo, categoria, escludi_allergeni, solo_vegetariani, solo_asporto)
        )


@mcp.tool(annotations=LETTURA)
@gestisci_errori
def dettaglio_piatto(
    id_articolo: Annotated[int, Field(description="Id del piatto, ottenuto da cerca_menu.")],
) -> DettaglioPiatto:
    """Restituisce descrizione, ingredienti, allergeni e porzioni ancora disponibili di un piatto."""
    with connessione() as conn:
        return DettaglioPiatto(**menu.dettaglio_piatto(conn, id_articolo))


# ============================================================================ prenotazioni


@mcp.tool(annotations=LETTURA)
@gestisci_errori
def verifica_disponibilita(
    data: Annotated[str, Field(description=DESCR_DATA)],
    ora: Annotated[str, Field(description="Ora nel formato HH:MM.")],
    coperti: Annotated[int, Field(ge=1, description="Numero di persone.")],
) -> Disponibilita:
    """Verifica se c'è un tavolo libero per data, ora e numero di persone indicati.
    Se non c'è posto propone orari alternativi nello stesso turno. Non registra nulla."""
    with connessione() as conn:
        return Disponibilita(**prenotazioni.verifica_disponibilita(conn, data, ora, coperti))


@mcp.tool(annotations=LETTURA)
@gestisci_errori
def trova_prenotazioni(
    nome: Annotated[str | None, Field(description="Nome (anche parziale) del cliente.")] = None,
    telefono: Annotated[str | None, Field(description="Telefono del cliente.")] = None,
    data: Annotated[str | None, Field(description=DESCR_DATA)] = None,
) -> ElencoPrenotazioni:
    """Cerca le prenotazioni attive (da oggi in poi). Indicare almeno uno tra nome, telefono e data."""
    with connessione() as conn:
        trovate = prenotazioni.trova_prenotazioni(conn, nome, telefono, data)
    return ElencoPrenotazioni(numero_risultati=len(trovate), prenotazioni=[Prenotazione(**p) for p in trovate])


@mcp.tool(annotations=SCRITTURA)
@gestisci_errori
def crea_prenotazione(
    data: Annotated[str, Field(description=DESCR_DATA)],
    ora: Annotated[str, Field(description="Ora nel formato HH:MM.")],
    coperti: Annotated[int, Field(ge=1, description="Numero di persone.")],
    nome_cliente: Annotated[str, Field(min_length=1, description="Nome e cognome del cliente.")],
    telefono: Annotated[str, Field(description="Telefono del cliente.")],
    note: Annotated[str | None, Field(description="Richieste particolari (es. seggiolone).")] = None,
) -> Prenotazione:
    """Registra una nuova prenotazione e assegna un tavolo. SCRIVE sui dati.
    Richiede nome e telefono reali forniti dal cliente: non inventarli."""
    with connessione() as conn:
        return Prenotazione(
            **prenotazioni.crea_prenotazione(conn, data, ora, coperti, nome_cliente, telefono, note)
        )


@mcp.tool(annotations=SCRITTURA)
@gestisci_errori
def modifica_prenotazione(
    id_prenotazione: Annotated[int, Field(description="Numero della prenotazione.")],
    telefono: Annotated[str, Field(description="Telefono usato per la prenotazione (verifica dell'identità).")],
    data: Annotated[str | None, Field(description="Nuova data. " + DESCR_DATA)] = None,
    ora: Annotated[str | None, Field(description="Nuova ora HH:MM.")] = None,
    coperti: Annotated[int | None, Field(ge=1, description="Nuovo numero di persone.")] = None,
    note: Annotated[str | None, Field(description="Nuove note.")] = None,
) -> Prenotazione:
    """Modifica data, ora, coperti o note di una prenotazione esistente. SCRIVE sui dati.
    Indicare solo i campi da cambiare. Se non c'è posto la prenotazione resta invariata."""
    with connessione() as conn:
        return Prenotazione(
            **prenotazioni.modifica_prenotazione(conn, id_prenotazione, telefono, data, ora, coperti, note)
        )


@mcp.tool(annotations=SCRITTURA_DISTRUTTIVA)
@gestisci_errori
def cancella_prenotazione(
    id_prenotazione: Annotated[int, Field(description="Numero della prenotazione.")],
    telefono: Annotated[str, Field(description="Telefono usato per la prenotazione (verifica dell'identità).")],
) -> Prenotazione:
    """Cancella una prenotazione esistente. SCRIVE sui dati e non è annullabile."""
    with connessione() as conn:
        return Prenotazione(**prenotazioni.cancella_prenotazione(conn, id_prenotazione, telefono))


# ============================================================================ ordini


@mcp.tool(annotations=SCRITTURA)
@gestisci_errori
def crea_ordine_asporto(
    nome_cliente: Annotated[str, Field(min_length=1, description="Nome del cliente.")],
    telefono: Annotated[str, Field(description="Telefono del cliente.")],
    righe: Annotated[list[RigaOrdineIn], Field(min_length=1, description="Piatti ordinati (id da cerca_menu).")],
    ora_ritiro: Annotated[str, Field(description="Ora di ritiro HH:MM.")],
    data_ritiro: Annotated[str | None, Field(description="Data di ritiro; se assente, oggi. " + DESCR_DATA)] = None,
    note: Annotated[str | None, Field(description="Note sull'ordine.")] = None,
) -> Ordine:
    """Registra un ordine da asporto e scala le scorte degli ingredienti. SCRIVE sui dati.
    Fallisce se un piatto non è da asporto, se le scorte non bastano o se l'orario non è valido."""
    with connessione() as conn:
        return Ordine(
            **ordini.crea_ordine_asporto(
                conn, nome_cliente, telefono, [r.model_dump() for r in righe], ora_ritiro, data_ritiro, note
            )
        )


@mcp.tool(annotations=LETTURA)
@gestisci_errori
def stato_ordine(
    id_ordine: Annotated[int, Field(description="Numero dell'ordine.")],
    telefono: Annotated[str, Field(description="Telefono usato per l'ordine (verifica dell'identità).")],
) -> Ordine:
    """Restituisce stato, orario di ritiro e contenuto di un ordine da asporto."""
    with connessione() as conn:
        return Ordine(**ordini.stato_ordine(conn, id_ordine, telefono))


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
