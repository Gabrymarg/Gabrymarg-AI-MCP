"""Back-end web (FastAPI) di Osteria del Borgo.

Responsabilità:
  - autenticazione degli utenti e rilascio del token (cookie HttpOnly);
  - una sessione agentica per utente, collegata al server MCP via HTTP con il token dell'utente;
  - chat in streaming (Server-Sent Events) con gli eventi del ciclo agentico e le richieste di conferma;
  - API di amministrazione (solo ruolo admin): utenti e anagrafiche del menu (categorie, ingredienti, articoli).

Il server MCP è un processo separato (python -m mcp_server.server --http) avviato all'avvio della web app.
I permessi sui dati sono applicati dal server MCP: la web app NON accede direttamente a prenotazioni e ordini.
Le anagrafiche sono configurazione, non operazioni da delegare all'agente: si gestiscono con maschere
tradizionali, tramite i servizi del back-end (backend/anagrafiche.py), solo dall'amministratore.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import anagrafiche, permessi, storico, token_accesso, utenti
from backend.db import connessione
from backend.errori import ErroreDominio
from backend.permessi import Utente
from harness import metriche
from harness.config import RADICE, Config
from webapp.sessioni import GestoreSessioni

STATIC = Path(__file__).resolve().parent / "static"
COOKIE = "risto_token"
HOST_MCP = os.environ.get("RISTO_MCP_HOST", "127.0.0.1")
PORTA_MCP = int(os.environ.get("RISTO_MCP_PORT", "8765"))
URL_MCP = f"http://{HOST_MCP}:{PORTA_MCP}/mcp"

MODELLI = [
    {"id": "ollama:qwen2.5:3b", "etichetta": "qwen2.5:3b - locale (Ollama)", "provider": "ollama", "modello": "qwen2.5:3b"},
    {"id": "groq:openai/gpt-oss-120b", "etichetta": "gpt-oss-120b - cloud (Groq)", "provider": "groq",
     "modello": "openai/gpt-oss-120b"},
    # I limiti del piano gratuito di Groq sono per modello: un secondo modello ha un budget separato.
    {"id": "groq:openai/gpt-oss-20b", "etichetta": "gpt-oss-20b - cloud (Groq)", "provider": "groq",
     "modello": "openai/gpt-oss-20b"},
    # Instradamento automatico: qwen in locale per le consultazioni, gpt-oss in cloud per le scritture.
    {"id": "router:qwen+gpt-oss-120b", "etichetta": "Automatico: locale + cloud (router)", "provider": "router",
     "modello": "ollama:qwen2.5:3b|groq:openai/gpt-oss-120b"},
]

# Protezione dai tentativi ripetuti di indovinare la password.
MAX_TENTATIVI, BLOCCO_S = 5, 60
_tentativi: dict[str, list[float]] = {}


def modelli_disponibili() -> list[dict[str, str]]:
    """Modelli selezionabili; se c'è la chiave Groq il modello cloud è il predefinito (primo), perché
    il modello locale su CPU richiede da decine di secondi a qualche minuto per risposta."""
    disponibili = [m for m in MODELLI if m["provider"] not in ("groq", "router") or os.environ.get("GROQ_API_KEY")]
    return sorted(disponibili, key=lambda m: m["provider"] != "groq")


# ============================================================================ avvio del server MCP


def _porta_aperta(host: str, porta: int) -> bool:
    try:
        socket.create_connection((host, porta), timeout=0.3).close()
        return True
    except OSError:
        return False


@asynccontextmanager
async def ciclo_di_vita(app: FastAPI):
    processo = None
    if os.environ.get("RISTO_MCP_ESTERNO") != "1" and not _porta_aperta(HOST_MCP, PORTA_MCP):
        processo = subprocess.Popen(
            [sys.executable, "-m", "mcp_server.server", "--http", "--host", HOST_MCP, "--port", str(PORTA_MCP)],
            cwd=RADICE,
        )
        for _ in range(100):
            if _porta_aperta(HOST_MCP, PORTA_MCP):
                break
            await asyncio.sleep(0.1)
    app.state.sessioni = GestoreSessioni(URL_MCP)
    with connessione() as conn:
        storico.crea_tabelle(conn)  # database creati prima dell'introduzione dello storico
    try:
        yield
    finally:
        await app.state.sessioni.chiudi_tutte()
        if processo:
            processo.terminate()


app = FastAPI(title="Osteria del Borgo", lifespan=ciclo_di_vita, docs_url=None, redoc_url=None)


@app.middleware("http")
async def intestazioni_sicurezza(request: Request, call_next):
    risposta = await call_next(request)
    risposta.headers["X-Content-Type-Options"] = "nosniff"
    risposta.headers["X-Frame-Options"] = "DENY"
    risposta.headers["Referrer-Policy"] = "no-referrer"
    risposta.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
    )
    return risposta


# ============================================================================ autenticazione


def utente_corrente(request: Request) -> tuple[Utente, str]:
    """Dipendenza: utente autenticato dal cookie, riletto dal database (ruolo e stato aggiornati)."""
    token = request.cookies.get(COOKIE)
    contenuto = token_accesso.verifica(token)
    if contenuto is None:
        raise HTTPException(401, "Sessione scaduta o non valida: effettuare di nuovo l'accesso.")
    with connessione() as conn:
        utente = utenti.utente_attivo(conn, int(contenuto["sub"]))
    if utente is None:
        raise HTTPException(401, "Account non attivo.")
    return utente, token


def solo_admin(dati: tuple[Utente, str] = Depends(utente_corrente)) -> Utente:
    if dati[0].ruolo != "admin":
        raise HTTPException(403, "Operazione riservata all'amministratore.")
    return dati[0]


class Credenziali(BaseModel):
    username: str = Field(max_length=40)
    password: str = Field(max_length=200)


def _profilo(utente: Utente) -> dict[str, Any]:
    return {
        "id_utente": utente.id_utente,
        "nome": utente.nome,
        "ruolo": utente.ruolo,
        "descrizione_ruolo": permessi.ETICHETTE_RUOLI[utente.ruolo],
        "modelli": modelli_disponibili(),
    }


@app.post("/api/login")
async def login(credenziali: Credenziali, response: Response):
    chiave = credenziali.username.strip().lower()
    adesso = time.time()
    recenti = [t for t in _tentativi.get(chiave, []) if adesso - t < BLOCCO_S]
    if len(recenti) >= MAX_TENTATIVI:
        raise HTTPException(429, f"Troppi tentativi falliti: riprovare tra {BLOCCO_S} secondi.")
    with connessione() as conn:
        utente = utenti.autentica(conn, credenziali.username, credenziali.password)
    if utente is None:
        _tentativi[chiave] = recenti + [adesso]
        await asyncio.sleep(0.5)
        raise HTTPException(401, "Username o password non corretti.")
    _tentativi.pop(chiave, None)
    token = token_accesso.emetti(utente.id_utente, utente.ruolo)
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", max_age=token_accesso.DURATA_PREDEFINITA_S)
    return _profilo(utente)


@app.post("/api/logout")
async def logout(request: Request, response: Response):
    contenuto = token_accesso.verifica(request.cookies.get(COOKIE))
    if contenuto:
        await request.app.state.sessioni.chiudi(int(contenuto["sub"]))
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/me")
async def me(dati: tuple[Utente, str] = Depends(utente_corrente)):
    return _profilo(dati[0])


# ============================================================================ chat con l'agente


class SceltaModello(BaseModel):
    modello: str


class Messaggio(BaseModel):
    testo: str = Field(min_length=1, max_length=2000)


class RispostaConferma(BaseModel):
    id: str
    approvato: bool


@app.post("/api/sessione")
async def apri_sessione(scelta: SceltaModello, request: Request, dati: tuple[Utente, str] = Depends(utente_corrente)):
    utente, token = dati
    modello = next((m for m in modelli_disponibili() if m["id"] == scelta.modello), None)
    if modello is None:
        raise HTTPException(400, "Modello non disponibile.")
    try:
        sessione = await request.app.state.sessioni.apri(utente.id_utente, token, modello["provider"], modello["modello"])
    except asyncio.TimeoutError:
        raise HTTPException(504, "Il server MCP o il modello non rispondono.") from None
    if sessione.errore_avvio:
        await request.app.state.sessioni.chiudi(utente.id_utente)
        raise HTTPException(502, f"Impossibile avviare l'assistente: {sessione.errore_avvio}")
    return {"modello": modello, "ruolo": sessione.profilo.get("ruolo"), "strumenti": sessione.strumenti}


def _sessione(request: Request, utente: Utente):
    sessione = request.app.state.sessioni.get(utente.id_utente)
    if sessione is None or sessione.errore_avvio:
        raise HTTPException(409, "Nessuna sessione attiva: scegliere un modello.")
    return sessione


@app.post("/api/chat")
async def chat(messaggio: Messaggio, request: Request, dati: tuple[Utente, str] = Depends(utente_corrente)):
    sessione = _sessione(request, dati[0])
    if sessione.occupata:
        raise HTTPException(409, "L'assistente sta ancora rispondendo al messaggio precedente.")
    sessione.occupata = True
    uscita = await sessione.esegui("turno", messaggio.testo)

    async def flusso():
        try:
            while (evento := await uscita.get()) is not None:
                yield f"data: {json.dumps(evento, ensure_ascii=False, default=str)}\n\n"
        finally:
            sessione.occupata = False

    return StreamingResponse(flusso(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


@app.post("/api/conferma")
async def conferma(risposta: RispostaConferma, request: Request, dati: tuple[Utente, str] = Depends(utente_corrente)):
    if not _sessione(request, dati[0]).rispondi_conferma(risposta.id, risposta.approvato):
        raise HTTPException(404, "Richiesta di conferma inesistente o scaduta.")
    return {"ok": True}


@app.post("/api/nuova-conversazione")
async def nuova_conversazione(request: Request, dati: tuple[Utente, str] = Depends(utente_corrente)):
    uscita = await _sessione(request, dati[0]).esegui("nuova")
    while await uscita.get() is not None:
        pass
    return {"ok": True}


# ============================================================================ storico delle conversazioni


def _storico(funzione, *argomenti, **opzioni):
    try:
        with connessione() as conn:
            return funzione(conn, *argomenti, **opzioni)
    except ErroreDominio as e:
        stato = 404 if e.codice == "CONVERSAZIONE_INESISTENTE" else 403
        raise HTTPException(stato, e.messaggio) from None


@app.get("/api/conversazioni")
async def elenco_conversazioni(tutte: bool = False, dati: tuple[Utente, str] = Depends(utente_corrente)):
    return _storico(storico.elenco, dati[0], tutte)


@app.get("/api/conversazioni/{id_conversazione}")
async def leggi_conversazione(id_conversazione: int, dati: tuple[Utente, str] = Depends(utente_corrente)):
    return _storico(storico.leggi, id_conversazione, dati[0])


@app.post("/api/conversazioni/{id_conversazione}/riprendi")
async def riprendi_conversazione(id_conversazione: int, request: Request,
                                 dati: tuple[Utente, str] = Depends(utente_corrente)):
    """Riprende una propria conversazione: l'agente riparte con i messaggi salvati."""
    conversazione = _storico(storico.leggi, id_conversazione, dati[0], per_riprendere=True)
    sessione = _sessione(request, dati[0])
    if sessione.occupata:
        raise HTTPException(409, "L'assistente sta ancora rispondendo al messaggio precedente.")
    storia = [(m["ruolo"], m["testo"]) for m in conversazione["messaggi"]]
    uscita = await sessione.esegui("riprendi", (id_conversazione, storia))
    while await uscita.get() is not None:
        pass
    return conversazione


@app.delete("/api/conversazioni/{id_conversazione}")
async def elimina_conversazione(id_conversazione: int, request: Request,
                                dati: tuple[Utente, str] = Depends(utente_corrente)):
    _storico(storico.elimina, id_conversazione, dati[0])
    sessione = request.app.state.sessioni.get(dati[0].id_utente)
    if sessione and sessione.id_conversazione == id_conversazione and not sessione.occupata:
        uscita = await sessione.esegui("nuova")  # la conversazione in corso è stata eliminata: si riparte da zero
        while await uscita.get() is not None:
            pass
    return {"ok": True}


# ============================================================================ amministrazione utenti


class NuovoUtente(BaseModel):
    username: str = Field(max_length=40)
    password: str = Field(max_length=200)
    ruolo: str
    nome: str = Field(max_length=80)
    telefono: str | None = Field(default=None, max_length=20)


class ModificaUtente(BaseModel):
    ruolo: str | None = None
    attivo: bool | None = None
    password: str | None = Field(default=None, max_length=200)
    nome: str | None = Field(default=None, max_length=80)
    telefono: str | None = Field(default=None, max_length=20)


def _errore_dominio(e: ErroreDominio) -> HTTPException:
    return HTTPException(400, e.messaggio)


@app.get("/api/admin/utenti")
async def elenco(admin: Utente = Depends(solo_admin)):
    with connessione() as conn:
        return utenti.elenco_utenti(conn)


@app.post("/api/admin/utenti", status_code=201)
async def crea(nuovo: NuovoUtente, admin: Utente = Depends(solo_admin)):
    try:
        with connessione() as conn:
            return utenti.crea_utente(conn, nuovo.username, nuovo.password, nuovo.ruolo, nuovo.nome, nuovo.telefono)
    except ErroreDominio as e:
        raise _errore_dominio(e) from None


@app.patch("/api/admin/utenti/{id_utente}")
async def modifica(id_utente: int, modifiche: ModificaUtente, request: Request, admin: Utente = Depends(solo_admin)):
    if id_utente == admin.id_utente and (modifiche.attivo is False or (modifiche.ruolo and modifiche.ruolo != "admin")):
        raise HTTPException(400, "Non è possibile disattivare o declassare il proprio account.")
    try:
        with connessione() as conn:
            aggiornato = utenti.modifica_utente(
                conn, id_utente, modifiche.ruolo, modifiche.attivo, modifiche.password or None,
                modifiche.nome, modifiche.telefono,
            )
    except ErroreDominio as e:
        raise _errore_dominio(e) from None
    # Un utente disattivato o cambiato di ruolo perde la sessione agentica in corso.
    if modifiche.attivo is False or modifiche.ruolo:
        await request.app.state.sessioni.chiudi(id_utente)
    return aggiornato


# ============================================================================ anagrafiche del menu


class Categoria(BaseModel):
    nome: str = Field(max_length=40)
    ordine: int | None = Field(default=None, ge=0, le=999)


class Ingrediente(BaseModel):
    nome: str = Field(max_length=60)
    unita_misura: str
    quantita_disponibile: float
    scorta_minima: float = 0


class RigaRicetta(BaseModel):
    id_ingrediente: int
    quantita: float


class Articolo(BaseModel):
    nome: str = Field(max_length=80)
    descrizione: str = Field(max_length=300)
    prezzo: float
    id_categoria: int
    vegetariano: bool = False
    asporto: bool = True
    attivo: bool = True
    allergeni: list[str] = Field(default_factory=list, max_length=14)
    ricetta: list[RigaRicetta] = Field(default_factory=list, max_length=30)


def _esegui(funzione, *argomenti, **opzioni):
    """Esegue un servizio delle anagrafiche in una transazione; le regole violate diventano errori 400."""
    try:
        with connessione() as conn:
            return funzione(conn, *argomenti, **opzioni)
    except ErroreDominio as e:
        raise _errore_dominio(e) from None


@app.get("/api/admin/menu")
async def anagrafiche_menu(admin: Utente = Depends(solo_admin)):
    with connessione() as conn:
        return {
            "categorie": anagrafiche.elenco_categorie(conn),
            "ingredienti": anagrafiche.elenco_ingredienti(conn),
            "articoli": anagrafiche.elenco_articoli(conn),
            "allergeni": anagrafiche.elenco_allergeni(conn),
        }


@app.post("/api/admin/categorie", status_code=201)
async def crea_categoria(dati: Categoria, admin: Utente = Depends(solo_admin)):
    return _esegui(anagrafiche.salva_categoria, dati.nome, dati.ordine)


@app.put("/api/admin/categorie/{id_categoria}")
async def modifica_categoria(id_categoria: int, dati: Categoria, admin: Utente = Depends(solo_admin)):
    return _esegui(anagrafiche.salva_categoria, dati.nome, dati.ordine, id_categoria)


@app.delete("/api/admin/categorie/{id_categoria}")
async def elimina_categoria(id_categoria: int, admin: Utente = Depends(solo_admin)):
    _esegui(anagrafiche.elimina_categoria, id_categoria)
    return {"ok": True}


@app.post("/api/admin/ingredienti", status_code=201)
async def crea_ingrediente(dati: Ingrediente, admin: Utente = Depends(solo_admin)):
    return _esegui(anagrafiche.salva_ingrediente, **dati.model_dump())


@app.put("/api/admin/ingredienti/{id_ingrediente}")
async def modifica_ingrediente(id_ingrediente: int, dati: Ingrediente, admin: Utente = Depends(solo_admin)):
    return _esegui(anagrafiche.salva_ingrediente, **dati.model_dump(), id_ingrediente=id_ingrediente)


@app.delete("/api/admin/ingredienti/{id_ingrediente}")
async def elimina_ingrediente(id_ingrediente: int, admin: Utente = Depends(solo_admin)):
    _esegui(anagrafiche.elimina_ingrediente, id_ingrediente)
    return {"ok": True}


@app.post("/api/admin/articoli", status_code=201)
async def crea_articolo(dati: Articolo, admin: Utente = Depends(solo_admin)):
    return _esegui(anagrafiche.salva_articolo, **dati.model_dump())


@app.put("/api/admin/articoli/{id_articolo}")
async def modifica_articolo(id_articolo: int, dati: Articolo, admin: Utente = Depends(solo_admin)):
    return _esegui(anagrafiche.salva_articolo, **dati.model_dump(), id_articolo=id_articolo)


# ============================================================================ cruscotto delle metriche


@app.get("/api/admin/metriche")
async def cruscotto(admin: Utente = Depends(solo_admin)):
    """Indicatori calcolati dai log JSONL delle conversazioni della web app."""
    return await asyncio.to_thread(metriche.analizza, Config().cartella_log)


# ============================================================================ pagine statiche


@app.get("/")
async def indice():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
