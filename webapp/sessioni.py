"""Sessioni agentiche della web app: una per utente collegato.

Ogni sessione è un task asincrono di lunga durata che:
  - apre la connessione MCP via HTTP presentando il token DELL'UTENTE (il server applica i suoi permessi);
  - crea l'Agent con il modello scelto e ne esegue i turni uno alla volta;
  - inoltra al browser, in tempo reale, gli eventi del ciclo agentico e le richieste di conferma.

La connessione MCP è aperta e chiusa dentro lo stesso task (requisito di anyio); le richieste web
comunicano con la sessione solo tramite code.
"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from harness.agent import Agent
from harness.config import Config
from harness.confirm import riepilogo
from harness.llm import crea_provider
from harness.llm.base import ToolSpec
from harness.logger import LoggerJSONL
from harness.mcp_client import ClienteMCP

TIMEOUT_CONFERMA_S = 300

# Campi degli eventi del log inoltrati al browser (si escludono prompt e messaggi completi, voluminosi).
CAMPI_EVENTO = {
    "tipo", "iterazione", "turno", "tool", "argomenti", "ok", "errore", "risultato", "approvato",
    "token_input", "token_output", "durata_ms", "testo", "tool_calls", "motivo_arresto", "token_totali",
    "annullato_da_utente", "testo_respinto", "convertiti", "secondi", "tentativo",
    "fase", "frammento", "ragionamento", "riferimenti", "modello", "instradamento",
}


def evento_per_browser(evento: dict[str, Any]) -> dict[str, Any] | None:
    if evento["tipo"] in ("avvio", "richiesta_modello"):
        return None
    pulito = {k: v for k, v in evento.items() if k in CAMPI_EVENTO}
    if isinstance(pulito.get("risultato"), (dict, list)):
        # Il pannello mostra un estratto: il risultato completo resta nel log JSONL.
        testo = json.dumps(pulito["risultato"], ensure_ascii=False)
        pulito["risultato"] = testo[:600] + ("…" if len(testo) > 600 else "")
    return pulito


@dataclass
class Sessione:
    id_utente: int
    token: str
    url_mcp: str
    provider: str
    modello: str
    cfg: Config = field(default_factory=Config)
    pronta: asyncio.Event = field(default_factory=asyncio.Event)
    errore_avvio: str | None = None
    profilo: dict[str, Any] = field(default_factory=dict)
    strumenti: list[dict[str, Any]] = field(default_factory=list)
    _comandi: asyncio.Queue = field(default_factory=asyncio.Queue)
    _uscita: asyncio.Queue | None = None
    _conferme: dict[str, asyncio.Future] = field(default_factory=dict)
    _task: asyncio.Task | None = None
    _loop: asyncio.AbstractEventLoop | None = None
    _thread_loop: int | None = None
    occupata: bool = False

    # ------------------------------------------------------------------ ciclo di vita

    def avvia(self) -> None:
        self._task = asyncio.create_task(self._vita(), name=f"sessione-{self.id_utente}")

    async def chiudi(self) -> None:
        for futuro in self._conferme.values():
            if not futuro.done():
                futuro.set_result(False)
        await self._comandi.put(None)
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except (asyncio.TimeoutError, Exception):
                self._task.cancel()

    async def _vita(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._thread_loop = threading.get_ident()
        log = LoggerJSONL(self.cfg.cartella_log, prefisso=f"web_utente{self.id_utente}")
        log.ascoltatori.append(self._inoltra)
        try:
            async with ClienteMCP(url=self.url_mcp, token=self.token) as cliente:
                agente = Agent(crea_provider(self.provider, self.modello), cliente, self._conferma, log, self.cfg)
                await agente.avvia()
                self.profilo = agente.profilo
                self.strumenti = [
                    {"nome": s.nome, "scrittura": s.scrittura, "distruttivo": s.distruttivo}
                    for s in agente.strumenti.values()
                ]
                self.pronta.set()
                while (comando := await self._comandi.get()) is not None:
                    tipo, valore, uscita = comando
                    self._uscita = uscita
                    try:
                        if tipo == "turno":
                            esito = await agente.esegui_turno(valore)
                            await uscita.put({
                                "tipo": "risposta", "testo": esito.risposta, "motivo_arresto": esito.motivo_arresto,
                                "token": esito.uso.totale, "durata_ms": esito.durata_ms,
                                "token_sessione": agente.uso_sessione.totale,
                            })
                        elif tipo == "nuova":
                            agente.nuova_conversazione()
                    except Exception as e:  # un turno fallito non deve chiudere la sessione
                        await uscita.put({"tipo": "errore", "messaggio": f"Errore interno: {type(e).__name__}"})
                    finally:
                        await uscita.put(None)
                        self._uscita = None
        except Exception as e:
            self.errore_avvio = f"{type(e).__name__}: {e}"
            self.pronta.set()
        finally:
            log.chiudi()

    # ------------------------------------------------------------------ eventi e conferme

    def _inoltra(self, evento: dict[str, Any]) -> None:
        # Può essere chiamata anche dal thread del provider (attese del fornitore): asyncio.Queue non è
        # thread-safe, quindi l'inserimento passa sempre dal loop della sessione.
        uscita = self._uscita
        if uscita is None or self._loop is None or (pulito := evento_per_browser(evento)) is None:
            return
        if threading.get_ident() == self._thread_loop:
            uscita.put_nowait(pulito)  # dal ciclo della sessione: inserimento immediato, l'ordine è preservato
        else:
            self._loop.call_soon_threadsafe(uscita.put_nowait, pulito)

    async def _conferma(self, spec: ToolSpec, argomenti: dict[str, Any]) -> bool:
        """Human-in-the-loop via browser: invia la richiesta e attende il clic su Conferma o Annulla."""
        id_conferma = uuid.uuid4().hex[:12]
        futuro = asyncio.get_running_loop().create_future()
        self._conferme[id_conferma] = futuro
        if self._uscita is not None:
            await self._uscita.put({
                "tipo": "richiesta_conferma", "id": id_conferma, "tool": spec.nome,
                "distruttivo": spec.distruttivo, "riepilogo": riepilogo(spec, argomenti),
            })
        try:
            return await asyncio.wait_for(futuro, timeout=TIMEOUT_CONFERMA_S)
        except asyncio.TimeoutError:
            return False
        finally:
            self._conferme.pop(id_conferma, None)

    def rispondi_conferma(self, id_conferma: str, approvato: bool) -> bool:
        futuro = self._conferme.get(id_conferma)
        if futuro is None or futuro.done():
            return False
        futuro.set_result(approvato)
        return True

    # ------------------------------------------------------------------ comandi dalle richieste web

    async def esegui(self, tipo: str, valore: Any = None) -> asyncio.Queue:
        uscita: asyncio.Queue = asyncio.Queue()
        await self._comandi.put((tipo, valore, uscita))
        return uscita


class GestoreSessioni:
    def __init__(self, url_mcp: str):
        self.url_mcp = url_mcp
        self._sessioni: dict[int, Sessione] = {}

    def get(self, id_utente: int) -> Sessione | None:
        return self._sessioni.get(id_utente)

    async def apri(self, id_utente: int, token: str, provider: str, modello: str) -> Sessione:
        await self.chiudi(id_utente)
        sessione = Sessione(id_utente, token, self.url_mcp, provider, modello)
        self._sessioni[id_utente] = sessione
        sessione.avvia()
        await asyncio.wait_for(sessione.pronta.wait(), timeout=60)
        return sessione

    async def chiudi(self, id_utente: int) -> None:
        sessione = self._sessioni.pop(id_utente, None)
        if sessione:
            await sessione.chiudi()

    async def chiudi_tutte(self) -> None:
        for id_utente in list(self._sessioni):
            await self.chiudi(id_utente)
