"""Server MCP di Osteria del Borgo.

Espone le funzionalità del sistema informativo (menu, prenotazioni, ordini, magazzino) come
tool MCP, con schema dei parametri e annotazioni sugli effetti:
- readOnlyHint=True  -> il tool legge soltanto;
- readOnlyHint=False -> il tool scrive sui dati (l'harness chiederà conferma all'utente);
- destructiveHint    -> la scrittura annulla/sovrascrive dati esistenti.

Due modalità di avvio:
  python -m mcp_server.server              trasporto stdio, senza login: l'utente è un "ospite"
                                            (CLI e scenari di test; identità verificata col telefono)
  python -m mcp_server.server --http       trasporto HTTP (Streamable HTTP): ogni richiesta deve
                                            portare un token "Authorization: Bearer ..." emesso dalla
                                            web app; ruolo e permessi sono applicati a ogni tool.

Il controllo dei permessi avviene QUI, sul server, a ogni chiamata: anche se il modello
linguistico venisse manipolato, non potrebbe usare un tool non consentito al ruolo dell'utente.

Iniezione di guasti (solo per i test): RISTO_GUASTI contiene i nomi dei tool che falliscono
simulando un database non raggiungibile.
"""

from __future__ import annotations

import argparse
import contextvars
import json
import os
import sqlite3
import sys
from datetime import timedelta
from functools import wraps
from pathlib import Path
from typing import Annotated, Any, Callable, Literal

from pydantic import Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.auth.middleware.auth_context import get_access_token  # noqa: E402
from mcp.server.auth.provider import AccessToken  # noqa: E402
from mcp.server.auth.settings import AuthSettings  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from backend import clock, menu, ordini, permessi, prenotazioni, token_accesso, utenti  # noqa: E402
from backend.db import connessione  # noqa: E402
from backend.errori import ErroreDominio  # noqa: E402
from backend.orari import descrizione_orari  # noqa: E402
from backend.permessi import OSPITE, Utente  # noqa: E402
from mcp_server.schemas import (  # noqa: E402
    DettaglioPiatto,
    Disponibilita,
    DisponibilitaPiatto,
    ElencoOrdini,
    ElencoPrenotazioni,
    EsitoScorta,
    Giacenze,
    OrariApertura,
    OrariDisponibili,
    Ordine,
    Prenotazione,
    Profilo,
    QuadroSala,
    RigaOrdineIn,
    RisultatoMenu,
)

URL_WEB = os.environ.get("RISTO_WEB_URL", "http://127.0.0.1:8000")
HOST_MCP = os.environ.get("RISTO_MCP_HOST", "127.0.0.1")
PORTA_MCP = int(os.environ.get("RISTO_MCP_PORT", "8765"))


# ============================================================================ autenticazione


class VerificatoreToken:
    """Verifica i token emessi dalla web app e rilegge l'utente dal database.

    Il ruolo usato è quello ATTUALE nel database (non quello scritto nel token): un utente
    disattivato o declassato dall'amministratore perde subito i permessi.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        contenuto = token_accesso.verifica(token)
        if contenuto is None:
            return None
        with connessione() as conn:
            utente = utenti.utente_attivo(conn, int(contenuto["sub"]))
        if utente is None:
            return None
        return AccessToken(
            token=token,
            client_id="risto-web",
            scopes=[utente.ruolo],
            subject=str(utente.id_utente),
            expires_at=int(contenuto["exp"]),
        )


mcp = MCPServer(
    name="osteria-del-borgo",
    version="2.0.0",
    instructions=(
        "Sistema informativo del ristorante Osteria del Borgo: menu e allergeni, prenotazioni dei tavoli, "
        "ordini da asporto e magazzino. I tool disponibili dipendono dal ruolo dell'utente (mio_profilo)."
    ),
    token_verifier=VerificatoreToken(),
    auth=AuthSettings(
        issuer_url=URL_WEB,
        resource_server_url=f"http://{HOST_MCP}:{PORTA_MCP}/mcp",
        validate_token_resource=False,  # l'audience è implicita: i token sono firmati solo per questo sistema
    ),
)

_utente_corrente: contextvars.ContextVar[Utente] = contextvars.ContextVar("utente_corrente", default=OSPITE)


def _identita() -> Utente:
    """Chi sta chiamando: dal token (HTTP) oppure ospite (stdio, nessun token)."""
    accesso = get_access_token()
    if accesso is None:
        return OSPITE
    with connessione() as conn:
        utente = utenti.utente_attivo(conn, int(accesso.subject))
    if utente is None:
        raise ToolError(json.dumps({"errore": {"codice": "ACCESSO_REVOCATO",
                                               "messaggio": "L'account non è più attivo."}}))
    return utente


def utente() -> Utente:
    return _utente_corrente.get()


def _tabella_corrente() -> dict[str, set[str]]:
    with connessione() as conn:
        return permessi.carica(conn)


# ============================================================================ infrastruttura dei tool

DESCR_DATA = (
    "Data AAAA-MM-GG, oppure direttamente le parole dell'utente: 'oggi', 'domani', 'dopodomani', "
    "il nome del giorno (es. 'sabato') o giorno e mese (es. '24 dicembre'): il sistema le converte "
    "nella data corretta."
)
DESCR_ID_PRENOTAZIONE = (
    "Numero della prenotazione. Facoltativo: se manca, il sistema usa l'unica prenotazione ATTIVA del cliente "
    "(cliente registrato, oppure ospite tramite telefono); se il cliente ne ha più di una restituisce l'elenco, "
    "da cui chiedere quale intende per giorno e ora."
)
DESCR_TELEFONO_VERIFICA = (
    "Telefono usato per la prenotazione o l'ordine (verifica dell'identità). "
    "Non serve per i clienti registrati né per il personale."
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


def _errore(codice: str, messaggio: str, **dettagli: Any) -> ToolError:
    errore: dict[str, Any] = {"codice": codice, "messaggio": messaggio}
    if dettagli:
        errore["dettagli"] = dettagli
    return ToolError(json.dumps({"errore": errore}, ensure_ascii=False))


def tool_protetto(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decoratore comune a tutti i tool: identità, autorizzazione, conversione degli errori di dominio.

    Gli errori imprevisti (es. database non raggiungibile) sono lasciati propagare:
    l'SDK li trasforma in un risultato di errore generico, senza esporre dettagli interni.
    """

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        chi = _identita()
        with connessione() as conn:
            # Permessi correnti (modificabili dall'admin) letti a ogni chiamata, con i vincoli del codice.
            tabella = permessi.carica(conn)
        if not permessi.puo(chi.ruolo, fn.__name__, tabella):
            raise _errore(
                "PERMESSO_NEGATO",
                f"Il ruolo '{chi.ruolo}' non è autorizzato a usare '{fn.__name__}'.",
                tool_consentiti=permessi.tool_consentiti(chi.ruolo, tabella),
            )
        _guasto_simulato(fn.__name__)
        segnaposto = _utente_corrente.set(chi)
        try:
            return fn(*args, **kwargs)
        except ErroreDominio as e:
            raise ToolError(json.dumps({"errore": e.to_dict()}, ensure_ascii=False)) from None
        finally:
            _utente_corrente.reset(segnaposto)

    return wrapper


# ============================================================================ informazioni


@mcp.tool(annotations=LETTURA)
@tool_protetto
def mio_profilo() -> Profilo:
    """Restituisce il ruolo e il nome dell'utente con cui si sta parlando e i tool che può usare.
    Il ruolo deriva dall'accesso effettuato, non da quanto dichiarato nella conversazione."""
    u = utente()
    return Profilo(
        ruolo=u.ruolo,
        descrizione_ruolo=permessi.ETICHETTE_RUOLI[u.ruolo],
        nome=u.nome or None,
        tool_consentiti=permessi.tool_consentiti(u.ruolo, _tabella_corrente()),
    )


@mcp.tool(annotations=LETTURA)
@tool_protetto
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
@tool_protetto
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
@tool_protetto
def dettaglio_piatto(
    nome: Annotated[
        str | None, Field(description="Nome del piatto come lo dice il cliente (es. 'tiramisù', 'carbonara').")
    ] = None,
    id_articolo: Annotated[int | None, Field(description="In alternativa al nome: id restituito da cerca_menu.")] = None,
) -> DettaglioPiatto:
    """Restituisce descrizione, ingredienti, ALLERGENI e porzioni ancora disponibili di un piatto.
    Indicare il piatto per nome: non indovinare gli id. Usare sempre per domande su allergeni o ingredienti."""
    with connessione() as conn:
        return DettaglioPiatto(**menu.dettaglio_piatto(conn, id_articolo, nome))


# ============================================================================ prenotazioni


@mcp.tool(annotations=LETTURA)
@tool_protetto
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
@tool_protetto
def orari_disponibili(
    data: Annotated[str, Field(description=DESCR_DATA)],
    coperti: Annotated[int, Field(ge=1, description="Numero di persone.")],
) -> OrariDisponibili:
    """Elenca TUTTI gli orari della giornata (pranzo e cena, ogni 30 minuti) in cui c'è un tavolo libero
    per il numero di persone indicato. Usare quando il cliente chiede quali orari sono disponibili o
    vuole alternative, invece di provare un orario alla volta. Non registra nulla."""
    with connessione() as conn:
        return OrariDisponibili(**prenotazioni.orari_disponibili(conn, data, coperti))


@mcp.tool(annotations=LETTURA)
@tool_protetto
def trova_prenotazioni(
    nome: Annotated[str | None, Field(description="Nome (anche parziale) del cliente.")] = None,
    telefono: Annotated[str | None, Field(description="Telefono del cliente.")] = None,
    data: Annotated[str | None, Field(description=DESCR_DATA)] = None,
) -> ElencoPrenotazioni:
    """Cerca le prenotazioni attive (da oggi in poi). Un cliente registrato vede solo le proprie, anche senza filtri;
    negli altri casi indicare almeno uno tra nome, telefono e data."""
    with connessione() as conn:
        trovate = prenotazioni.trova_prenotazioni(conn, nome, telefono, data, utente=utente())
    return ElencoPrenotazioni(numero_risultati=len(trovate), prenotazioni=[Prenotazione(**p) for p in trovate])


@mcp.tool(annotations=SCRITTURA)
@tool_protetto
def crea_prenotazione(
    data: Annotated[str, Field(description=DESCR_DATA)],
    ora: Annotated[str, Field(description="Ora nel formato HH:MM.")],
    coperti: Annotated[int, Field(ge=1, description="Numero di persone.")],
    nome_cliente: Annotated[
        str | None, Field(description="Nome e cognome del cliente (non serve per i clienti registrati).")
    ] = None,
    telefono: Annotated[str | None, Field(description="Telefono del cliente (non serve per i clienti registrati).")] = None,
    note: Annotated[str | None, Field(description="Richieste particolari (es. seggiolone).")] = None,
) -> Prenotazione:
    """Registra una nuova prenotazione e assegna un tavolo. SCRIVE sui dati.
    Controlla da sola la disponibilità. Per un ospite servono nome e telefono reali forniti dal cliente
    (non inventarli); per un cliente registrato si usano i dati del suo profilo."""
    with connessione() as conn:
        return Prenotazione(
            **prenotazioni.crea_prenotazione(conn, data, ora, coperti, nome_cliente, telefono, note, utente=utente())
        )


@mcp.tool(annotations=SCRITTURA)
@tool_protetto
def modifica_prenotazione(
    id_prenotazione: Annotated[int | None, Field(description=DESCR_ID_PRENOTAZIONE)] = None,
    telefono: Annotated[str | None, Field(description=DESCR_TELEFONO_VERIFICA)] = None,
    data: Annotated[str | None, Field(description="Nuova data. " + DESCR_DATA)] = None,
    ora: Annotated[str | None, Field(description="Nuova ora HH:MM.")] = None,
    coperti: Annotated[int | None, Field(ge=1, description="Nuovo numero di persone.")] = None,
    note: Annotated[str | None, Field(description="Nuove note.")] = None,
) -> Prenotazione:
    """Modifica data, ora, coperti o note di una prenotazione esistente. SCRIVE sui dati.
    Indicare solo i campi da cambiare. Se non c'è posto la prenotazione resta invariata."""
    with connessione() as conn:
        return Prenotazione(
            **prenotazioni.modifica_prenotazione(
                conn, id_prenotazione, telefono, data, ora, coperti, note, utente=utente()
            )
        )


@mcp.tool(annotations=SCRITTURA_DISTRUTTIVA)
@tool_protetto
def cancella_prenotazione(
    id_prenotazione: Annotated[int | None, Field(description=DESCR_ID_PRENOTAZIONE)] = None,
    telefono: Annotated[str | None, Field(description=DESCR_TELEFONO_VERIFICA)] = None,
) -> Prenotazione:
    """Cancella una prenotazione esistente. SCRIVE sui dati e non è annullabile."""
    with connessione() as conn:
        return Prenotazione(**prenotazioni.cancella_prenotazione(conn, id_prenotazione, telefono, utente=utente()))


@mcp.tool(annotations=LETTURA)
@tool_protetto
def prenotazioni_del_giorno(
    data: Annotated[str, Field(description=DESCR_DATA)],
) -> QuadroSala:
    """Quadro della sala per una data: tutte le prenotazioni attive con tavolo e coperti per turno.
    Riservato al personale di sala e all'amministratore."""
    with connessione() as conn:
        return QuadroSala(**prenotazioni.prenotazioni_del_giorno(conn, data))


# ============================================================================ ordini


@mcp.tool(annotations=SCRITTURA)
@tool_protetto
def crea_ordine_asporto(
    righe: Annotated[
        list[RigaOrdineIn],
        Field(min_length=1, description="Piatti ordinati, indicati per nome (es. [{'nome': 'carbonara', 'quantita': 2}])."),
    ],
    ora_ritiro: Annotated[str, Field(description="Ora di ritiro HH:MM.")],
    nome_cliente: Annotated[str | None, Field(description="Nome del cliente (non serve per i clienti registrati).")] = None,
    telefono: Annotated[str | None, Field(description="Telefono del cliente (non serve per i clienti registrati).")] = None,
    data_ritiro: Annotated[str | None, Field(description="Data di ritiro; se assente, oggi. " + DESCR_DATA)] = None,
    note: Annotated[str | None, Field(description="Note sull'ordine.")] = None,
) -> Ordine:
    """Registra un ordine da asporto e scala le scorte degli ingredienti. SCRIVE sui dati.
    Indicare i piatti per NOME (non serve cercare prima gli id). Fallisce, senza registrare nulla,
    se un piatto non esiste o è ambiguo, non è da asporto, le scorte non bastano o l'orario non è valido."""
    with connessione() as conn:
        return Ordine(
            **ordini.crea_ordine_asporto(
                conn, nome_cliente, telefono, [r.model_dump() for r in righe], ora_ritiro, data_ritiro, note,
                utente=utente(),
            )
        )


@mcp.tool(annotations=LETTURA)
@tool_protetto
def stato_ordine(
    id_ordine: Annotated[int, Field(description="Numero dell'ordine.")],
    telefono: Annotated[str | None, Field(description=DESCR_TELEFONO_VERIFICA)] = None,
) -> Ordine:
    """Restituisce stato, orario di ritiro e contenuto di un ordine da asporto."""
    with connessione() as conn:
        return Ordine(**ordini.stato_ordine(conn, id_ordine, telefono, utente=utente()))


@mcp.tool(annotations=LETTURA)
@tool_protetto
def ordini_da_preparare(
    data: Annotated[str | None, Field(description="Data di ritiro; se assente, oggi. " + DESCR_DATA)] = None,
) -> ElencoOrdini:
    """Elenco degli ordini da asporto ancora da evadere (ricevuti, in preparazione, pronti), in ordine di ritiro.
    Riservato a cucina, sala e amministratore."""
    with connessione() as conn:
        return ElencoOrdini(**ordini.ordini_da_preparare(conn, data))


@mcp.tool(annotations=SCRITTURA)
@tool_protetto
def aggiorna_stato_ordine(
    id_ordine: Annotated[int, Field(description="Numero dell'ordine.")],
    nuovo_stato: Annotated[
        Literal["in_preparazione", "pronto", "ritirato", "annullato"],
        Field(description="Nuovo stato: in_preparazione, pronto, ritirato o annullato."),
    ],
) -> Ordine:
    """Aggiorna lo stato di un ordine da asporto (es. da 'in_preparazione' a 'pronto'). SCRIVE sui dati.
    Sono ammesse solo le transizioni coerenti. Riservato a cucina, sala e amministratore."""
    with connessione() as conn:
        return Ordine(**ordini.aggiorna_stato_ordine(conn, id_ordine, nuovo_stato))


# ============================================================================ magazzino e amministrazione


@mcp.tool(annotations=LETTURA)
@tool_protetto
def giacenze_ingredienti(
    testo: Annotated[str | None, Field(description="Parte del nome dell'ingrediente (es. 'tartufo').")] = None,
    solo_sotto_scorta: Annotated[
        bool, Field(description="True per elencare solo gli ingredienti sotto la scorta minima (da riordinare).")
    ] = False,
) -> Giacenze:
    """Giacenze di magazzino degli ingredienti, con quantità, unità di misura e scorta minima.
    Indica quali ingredienti sono sotto scorta. Riservato a cucina e amministratore."""
    with connessione() as conn:
        return Giacenze(**menu.giacenze_ingredienti(conn, testo, solo_sotto_scorta))


@mcp.tool(annotations=SCRITTURA)
@tool_protetto
def aggiorna_scorta(
    ingrediente: Annotated[str, Field(description="Nome dell'ingrediente (es. 'tartufo nero').")],
    quantita: Annotated[float, Field(ge=0, description="Quantità nell'unità di misura dell'ingrediente (g, ml, pz).")],
    modalita: Annotated[
        Literal["aggiungi", "imposta"],
        Field(description="'aggiungi' per un carico di merce, 'imposta' per correggere la giacenza dopo un inventario."),
    ] = "aggiungi",
) -> EsitoScorta:
    """Aggiorna la giacenza di un ingrediente in magazzino. SCRIVE sui dati. Riservato all'amministratore."""
    with connessione() as conn:
        return EsitoScorta(**menu.aggiorna_scorta(conn, ingrediente, quantita, modalita))


@mcp.tool(annotations=SCRITTURA)
@tool_protetto
def imposta_disponibilita_piatto(
    nome: Annotated[str, Field(description="Nome del piatto.")],
    disponibile: Annotated[bool, Field(description="True per rimetterlo nel menu, False per toglierlo.")],
) -> DisponibilitaPiatto:
    """Toglie o rimette un piatto nel menu. SCRIVE sui dati. Riservato all'amministratore."""
    with connessione() as conn:
        return DisponibilitaPiatto(**menu.imposta_disponibilita_piatto(conn, nome, disponibile))


def main() -> None:
    parser = argparse.ArgumentParser(description="Server MCP di Osteria del Borgo")
    parser.add_argument("--http", action="store_true", help="trasporto HTTP con autenticazione (per la web app)")
    parser.add_argument("--host", default=HOST_MCP)
    parser.add_argument("--port", type=int, default=PORTA_MCP)
    args = parser.parse_args()
    if args.http:
        mcp.run("streamable-http", host=args.host, port=args.port)
    else:
        mcp.run("stdio")


if __name__ == "__main__":
    main()
