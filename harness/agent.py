"""Ciclo agentico.

Per ogni messaggio dell'utente (un "turno") l'agente ripete:
  1. invia al modello la conversazione e l'elenco dei tool;
  2. se il modello risponde senza chiedere tool -> risposta finale, fine del turno;
  3. altrimenti, per ogni chiamata richiesta:
       a. verifica che il tool esista,
       b. valida gli argomenti con il JSON Schema dichiarato dal server,
       c. se il tool scrive sui dati chiede conferma all'utente (human-in-the-loop),
       d. invoca il tool sul server MCP (con timeout),
       e. restituisce al modello il risultato o l'errore in forma strutturata;
  4. controlla le condizioni di arresto e torna al punto 1.

Condizioni di arresto esplicite (motivo registrato nel log):
  risposta_finale | max_iterazioni | loop_rilevato | troppi_errori | errore_modello
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from jsonschema import Draft202012Validator

from harness.config import Config
from harness.confirm import FunzioneConferma, riepilogo
from harness.guardrail import AVVISO as AVVISO_GUARDRAIL
from harness.guardrail import afferma_operazione
from harness.llm.base import LLMProvider, Messaggio, ToolCall, ToolSpec, Uso
from harness.logger import LoggerJSONL
from harness.mcp_client import EsitoTool
from harness.prompt import prompt_di_sistema
from harness.schema_utils import compatta_schema

MESSAGGI_ARRESTO = {
    "max_iterazioni": "Mi dispiace, non sono riuscito a completare la richiesta. Può riformularla in modo più "
                      "semplice oppure contattare il ristorante per telefono?",
    "loop_rilevato": "Mi dispiace, sto avendo difficoltà a completare la richiesta. Può riformularla oppure "
                     "contattare il ristorante per telefono?",
    "troppi_errori": "Mi dispiace, in questo momento il sistema del ristorante non risponde correttamente. "
                     "La invito a riprovare più tardi o a telefonare al ristorante.",
    "errore_modello": "Mi dispiace, l'assistente non è al momento disponibile. Riprovi tra poco.",
}


class EsecutoreTool(Protocol):
    async def elenco_strumenti(self) -> list[ToolSpec]: ...
    async def chiama(self, nome: str, argomenti: dict[str, Any], timeout_s: float) -> EsitoTool: ...


@dataclass
class EsitoTurno:
    risposta: str
    motivo_arresto: str
    iterazioni: int
    uso: Uso
    chiamate_modello: int
    tool_invocati: list[str] = field(default_factory=list)
    durata_ms: int = 0


def _rimuovi_null(argomenti: dict[str, Any]) -> dict[str, Any]:
    """I modelli spesso passano esplicitamente null per i parametri facoltativi: li si omette."""
    return {k: v for k, v in argomenti.items() if v is not None}


class Agent:
    def __init__(
        self,
        llm: LLMProvider,
        esecutore: EsecutoreTool,
        conferma: FunzioneConferma,
        logger: LoggerJSONL,
        config: Config | None = None,
    ):
        self.llm = llm
        self.esecutore = esecutore
        self.conferma = conferma
        self.log = logger
        self.cfg = config or Config()
        self.strumenti: dict[str, ToolSpec] = {}
        self.validatori: dict[str, Draft202012Validator] = {}
        self.messaggi: list[Messaggio] = []
        self.turno = 0
        self.uso_sessione = Uso()

    # ------------------------------------------------------------------ avvio

    async def avvia(self) -> None:
        """Carica i tool dal server e prepara il prompt di sistema con data e orari correnti."""
        for spec in await self.esecutore.elenco_strumenti():
            # La validazione usa lo schema originale; al modello va la versione compatta.
            self.validatori[spec.nome] = Draft202012Validator(spec.parametri)
            spec.parametri = compatta_schema(spec.parametri)
            self.strumenti[spec.nome] = spec
        adesso, orari = datetime.now(), []
        if "orari_apertura" in self.strumenti:
            esito = await self.esecutore.chiama("orari_apertura", {}, self.cfg.timeout_tool_s)
            if esito.ok and isinstance(esito.contenuto, dict):
                adesso = datetime.fromisoformat(esito.contenuto["oggi"])
                orari = esito.contenuto["settimana"]
        self.messaggi = [Messaggio("system", prompt_di_sistema(adesso, orari))]
        self.log.registra(
            "avvio",
            turno=0,
            modello=self.llm.descrizione(),
            strumenti=[
                {"nome": s.nome, "scrittura": s.scrittura, "distruttivo": s.distruttivo}
                for s in self.strumenti.values()
            ],
            data_riferimento=adesso.isoformat(timespec="minutes"),
            prompt_di_sistema=self.messaggi[0].contenuto,
        )

    def nuova_conversazione(self) -> None:
        self.messaggi = self.messaggi[:1]

    # ------------------------------------------------------------------ ciclo

    async def esegui_turno(self, testo_utente: str) -> EsitoTurno:
        self.turno += 1
        inizio = time.perf_counter()
        self.messaggi.append(Messaggio("user", testo_utente))
        self.log.registra("richiesta_utente", self.turno, testo=testo_utente)

        uso = Uso()
        chiamate_modello = 0
        tool_invocati: list[str] = []
        firme: Counter[str] = Counter()
        errori_consecutivi = 0
        scritture_eseguite = scrittura_negata = guardrail_usato = False
        inviati_finora = len(self.messaggi) - 1
        motivo, risposta_finale, iterazione = "max_iterazioni", "", 0

        for iterazione in range(1, self.cfg.max_iterazioni + 1):
            # 1. richiesta al modello
            nuovi = [m.to_dict() for m in self.messaggi[inviati_finora:]]
            self.log.registra(
                "richiesta_modello", self.turno, iterazione,
                messaggi_totali=len(self.messaggi), nuovi_messaggi=nuovi,
            )
            inviati_finora = len(self.messaggi)
            try:
                r = await asyncio.to_thread(self.llm.chat, self.messaggi, list(self.strumenti.values()))
            except Exception as e:
                self.log.registra("errore_modello", self.turno, iterazione, errore=f"{type(e).__name__}: {e}")
                motivo = "errore_modello"
                break
            chiamate_modello += 1
            uso.token_input += r.uso.token_input
            uso.token_output += r.uso.token_output
            self.log.registra(
                "risposta_modello", self.turno, iterazione,
                testo=r.testo,
                tool_calls=[{"nome": t.nome, "argomenti": t.argomenti} for t in r.tool_calls],
                token_input=r.uso.token_input, token_output=r.uso.token_output, durata_ms=r.durata_ms,
            )

            # 2. nessun tool richiesto -> risposta finale (dopo il controllo di coerenza)
            if not r.tool_calls:
                if (
                    self.cfg.guardrail_coerenza
                    and not guardrail_usato
                    and not scritture_eseguite
                    and not scrittura_negata
                    and afferma_operazione(r.testo)
                ):
                    guardrail_usato = True
                    self.messaggi.append(Messaggio("assistant", r.testo))
                    self.messaggi.append(Messaggio("system", AVVISO_GUARDRAIL))
                    self.log.registra("guardrail_coerenza", self.turno, iterazione, testo_respinto=r.testo)
                    continue
                risposta_finale, motivo = r.testo.strip(), "risposta_finale"
                break

            # 3. esecuzione dei tool richiesti
            self.messaggi.append(Messaggio("assistant", r.testo, tool_calls=r.tool_calls))
            for chiamata in r.tool_calls:
                esito = await self._esegui_chiamata(chiamata, iterazione)
                tool_invocati.append(chiamata.nome)
                self.messaggi.append(
                    Messaggio("tool", json.dumps(esito, ensure_ascii=False, default=str),
                              tool_call_id=chiamata.id, nome_tool=chiamata.nome)
                )
                errori_consecutivi = errori_consecutivi + 1 if not esito["ok"] else 0
                spec = self.strumenti.get(chiamata.nome)
                if spec and spec.scrittura:
                    scritture_eseguite |= bool(esito["ok"])
                    scrittura_negata |= bool(esito.get("annullato_da_utente"))
                firme[chiamata.nome + json.dumps(chiamata.argomenti, sort_keys=True, default=str)] += 1

            # 4. condizioni di arresto anticipato
            if errori_consecutivi >= self.cfg.max_errori_consecutivi:
                motivo = "troppi_errori"
                break
            if max(firme.values()) > self.cfg.max_ripetizioni_chiamata:
                motivo = "loop_rilevato"
                break

        if motivo != "risposta_finale" or not risposta_finale:
            if motivo == "risposta_finale":  # risposta vuota: la si tratta come errore del modello
                motivo = "errore_modello"
            risposta_finale = MESSAGGI_ARRESTO[motivo]
        self.messaggi.append(Messaggio("assistant", risposta_finale))
        self.uso_sessione.token_input += uso.token_input
        self.uso_sessione.token_output += uso.token_output

        esito_turno = EsitoTurno(
            risposta=risposta_finale,
            motivo_arresto=motivo,
            iterazioni=iterazione,
            uso=uso,
            chiamate_modello=chiamate_modello,
            tool_invocati=tool_invocati,
            durata_ms=int((time.perf_counter() - inizio) * 1000),
        )
        self.log.registra(
            "fine_turno", self.turno, iterazione,
            motivo_arresto=motivo, risposta=risposta_finale, chiamate_modello=chiamate_modello,
            tool_invocati=tool_invocati, token_input=uso.token_input, token_output=uso.token_output,
            token_totali=uso.totale, durata_ms=esito_turno.durata_ms,
        )
        return esito_turno

    # ------------------------------------------------------------------ singola chiamata

    async def _esegui_chiamata(self, chiamata: ToolCall, iterazione: int) -> dict[str, Any]:
        nome, argomenti = chiamata.nome, _rimuovi_null(chiamata.argomenti)
        self.log.registra("chiamata_tool", self.turno, iterazione, tool=nome, argomenti=argomenti)

        def errore(codice: str, messaggio: str, **extra: Any) -> dict[str, Any]:
            esito = {"ok": False, "errore": {"codice": codice, "messaggio": messaggio, **extra}}
            self.log.registra("risultato_tool", self.turno, iterazione, tool=nome, **esito)
            return esito

        # a. il tool esiste?
        spec = self.strumenti.get(nome)
        if spec is None:
            return errore("TOOL_INESISTENTE", f"Il tool '{nome}' non esiste.", tool_disponibili=sorted(self.strumenti))

        # b. argomenti conformi allo schema?
        problemi = sorted(self.validatori[nome].iter_errors(argomenti), key=lambda e: list(e.path))
        if problemi:
            dettagli = [f"{'/'.join(map(str, p.path)) or '(radice)'}: {p.message}" for p in problemi[:5]]
            return errore("PARAMETRI_NON_VALIDI", "Argomenti non conformi allo schema del tool.", dettagli=dettagli)

        # c. human-in-the-loop per i tool con effetti di scrittura
        if spec.scrittura:
            approvato = await asyncio.to_thread(self.conferma, spec, argomenti)
            self.log.registra(
                "conferma_utente", self.turno, iterazione, tool=nome, approvato=approvato,
                riepilogo=riepilogo(spec, argomenti),
            )
            if not approvato:
                esito = {
                    "ok": False,
                    "annullato_da_utente": True,
                    "messaggio": "L'utente NON ha confermato: l'operazione non è stata eseguita. "
                                 "Non riprovare: chiedi all'utente cosa desidera cambiare.",
                }
                self.log.registra("risultato_tool", self.turno, iterazione, tool=nome, **esito)
                return esito

        # d. invocazione sul server MCP
        inizio = time.perf_counter()
        r = await self.esecutore.chiama(nome, argomenti, self.cfg.timeout_tool_s)
        durata = int((time.perf_counter() - inizio) * 1000)
        esito = {"ok": True, "risultato": r.contenuto} if r.ok else {"ok": False, "errore": r.errore}
        self.log.registra("risultato_tool", self.turno, iterazione, tool=nome, durata_ms=durata, **esito)
        return esito
