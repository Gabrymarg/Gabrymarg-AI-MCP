"""Connessione al server MCP e traduzione dei tool nel formato dell'harness."""

from __future__ import annotations

import inspect
import json
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from harness.llm.base import ToolSpec


@dataclass
class EsitoTool:
    ok: bool
    contenuto: Any  # risultato strutturato (dict) oppure testo
    errore: dict[str, Any] | None = None


class ServerNonDisponibile(Exception):
    pass


def _interpreta_errore(testo: str) -> dict[str, Any]:
    """Estrae l'errore di dominio JSON dal messaggio dell'SDK, se presente."""
    inizio = testo.find("{")
    if inizio >= 0:
        try:
            dati = json.loads(testo[inizio:])
            if isinstance(dati, dict) and "errore" in dati:
                return dati["errore"]
        except json.JSONDecodeError:
            pass
    if testo.startswith("Unknown tool"):
        return {"codice": "TOOL_INESISTENTE", "messaggio": testo}
    if "validation error" in testo:
        return {"codice": "PARAMETRI_NON_VALIDI", "messaggio": testo}
    return {"codice": "ERRORE_TOOL", "messaggio": "Il servizio ha restituito un errore imprevisto: " + testo}


class ClienteMCP:
    """Connessione al server MCP.

    - stdio (comando + cartella): avvia il server come processo figlio, senza autenticazione;
    - HTTP (url + token): si collega a un server già in esecuzione, presentando il token dell'utente
      in ogni richiesta (Authorization: Bearer ...). La cache delle risposte del client è disattivata,
      perché le risposte dipendono dall'utente e non devono essere condivise.
    """

    def __init__(
        self,
        comando: list[str] | None = None,
        cartella: Path | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        token: str | None = None,
    ):
        self.url, self.token = url, token
        self.parametri = None
        if url is None:
            if comando is None or cartella is None:
                raise ValueError("Indicare comando e cartella (stdio) oppure url e token (HTTP).")
            self.parametri = StdioServerParameters(
                command=comando[0], args=comando[1:], cwd=str(cartella), env={**os.environ, **(env or {})}
            )
        self._stack: AsyncExitStack | None = None
        self._client: Client | None = None

    def _crea_client(self) -> Client:
        if self.url is None:
            return Client(self.parametri)
        intestazioni = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        trasporto = streamable_http_client(self.url, http_client=create_mcp_http_client(headers=intestazioni))
        return Client(trasporto, cache=None)

    async def __aenter__(self) -> "ClienteMCP":
        self._stack = AsyncExitStack()
        try:
            self._client = await self._stack.enter_async_context(self._crea_client())
        except Exception as e:
            await self._stack.aclose()
            raise ServerNonDisponibile(f"Impossibile avviare o contattare il server MCP: {e}") from e
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._stack:
            await self._stack.aclose()

    async def elenco_strumenti(self) -> list[ToolSpec]:
        assert self._client is not None
        risultato = await self._client.list_tools()
        strumenti = []
        for t in risultato.tools:
            a = t.annotations
            # Prudenza: se il server non dichiara readOnlyHint il tool è trattato come scrittura.
            sola_lettura = bool(a and a.read_only_hint)
            strumenti.append(
                ToolSpec(
                    nome=t.name,
                    descrizione=inspect.cleandoc(t.description or ""),
                    parametri=t.input_schema,
                    scrittura=not sola_lettura,
                    distruttivo=bool(a and a.destructive_hint),
                )
            )
        return strumenti

    async def chiama(self, nome: str, argomenti: dict[str, Any], timeout_s: float) -> EsitoTool:
        assert self._client is not None
        try:
            with anyio.fail_after(timeout_s):
                r = await self._client.call_tool(nome, argomenti)
        except TimeoutError:
            return EsitoTool(False, None, {"codice": "TIMEOUT", "messaggio": f"Il tool {nome} non ha risposto entro {timeout_s:.0f} s."})
        except Exception as e:  # errore di protocollo o di trasporto
            return EsitoTool(False, None, {"codice": "ERRORE_COMUNICAZIONE", "messaggio": f"{type(e).__name__}: {e}"})
        testo = "\n".join(c.text for c in r.content if getattr(c, "type", "") == "text")
        if r.is_error:
            return EsitoTool(False, None, _interpreta_errore(testo))
        return EsitoTool(True, r.structured_content if r.structured_content is not None else testo)
