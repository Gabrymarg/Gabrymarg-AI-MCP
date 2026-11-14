"""Provider per modelli eseguiti in locale con Ollama (API nativa /api/chat)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import ollama

from harness.llm.base import LLMProvider, LLMResponse, Messaggio, ToolCall, ToolSpec, Uso


class OllamaProvider(LLMProvider):
    nome = "ollama"

    def __init__(
        self,
        modello: str,
        host: str | None = None,
        temperatura: float = 0.0,
        contesto: int = 8192,
        timeout: float = 300.0,
    ):
        super().__init__(modello)
        self.client = ollama.Client(host=host, timeout=timeout)
        self.opzioni = {"temperature": temperatura, "num_ctx": contesto, "seed": 42}
        self._ragiona: bool | None = None

    @staticmethod
    def _converti_messaggio(m: Messaggio) -> dict[str, Any]:
        if m.ruolo == "tool":
            return {"role": "tool", "content": m.contenuto, "tool_name": m.nome_tool}
        d: dict[str, Any] = {"role": m.ruolo, "content": m.contenuto}
        if m.tool_calls:
            d["tool_calls"] = [{"function": {"name": t.nome, "arguments": t.argomenti}} for t in m.tool_calls]
        return d

    @staticmethod
    def _converti_tool(t: ToolSpec) -> dict[str, Any]:
        return {"type": "function", "function": {"name": t.nome, "description": t.descrizione, "parameters": t.parametri}}

    def _sa_ragionare(self) -> bool:
        """Il modello supporta la fase di ragionamento ("thinking")? Lo dichiara Ollama tra le capacità."""
        if self._ragiona is None:
            try:
                self._ragiona = "thinking" in (self.client.show(self.modello).capabilities or [])
            except Exception:
                self._ragiona = False
        return self._ragiona

    def chat(self, messaggi: list[Messaggio], strumenti: list[ToolSpec]) -> LLMResponse:
        inizio = time.perf_counter()
        richiesta = dict(
            model=self.modello,
            messages=[self._converti_messaggio(m) for m in messaggi],
            tools=[self._converti_tool(t) for t in strumenti] or None,
            options=self.opzioni,
        )
        if self._sa_ragionare():
            richiesta["think"] = True
        if self.notifica_flusso is None:
            risposta = self.client.chat(**richiesta)
            testo, pensiero = risposta.message.content or "", getattr(risposta.message, "thinking", None) or ""
            tool_calls, finale = list(risposta.message.tool_calls or []), risposta
        else:
            # Streaming: i frammenti arrivano man mano che il modello li genera e vengono inoltrati.
            testo, pensiero, tool_calls, finale = "", "", [], None
            for pezzo in self.client.chat(**richiesta, stream=True):
                if frammento := getattr(pezzo.message, "thinking", None):
                    pensiero += frammento
                    self.notifica_flusso("pensiero", frammento)
                if frammento := pezzo.message.content:
                    testo += frammento
                    self.notifica_flusso("testo", frammento)
                tool_calls += pezzo.message.tool_calls or []
                finale = pezzo
        chiamate = []
        for tc in tool_calls:
            argomenti = tc.function.arguments
            if isinstance(argomenti, str):  # alcuni modelli restituiscono JSON come stringa
                try:
                    argomenti = json.loads(argomenti)
                except json.JSONDecodeError:
                    argomenti = {"_argomenti_non_json": argomenti}
            chiamate.append(ToolCall(id=uuid.uuid4().hex[:8], nome=tc.function.name, argomenti=dict(argomenti or {})))
        return LLMResponse(
            testo=testo,
            tool_calls=chiamate,
            uso=Uso(finale.prompt_eval_count or 0, finale.eval_count or 0),
            modello=finale.model or self.modello,
            durata_ms=int((time.perf_counter() - inizio) * 1000),
            ragionamento=pensiero,
        )
