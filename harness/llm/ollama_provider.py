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

    def chat(self, messaggi: list[Messaggio], strumenti: list[ToolSpec]) -> LLMResponse:
        inizio = time.perf_counter()
        risposta = self.client.chat(
            model=self.modello,
            messages=[self._converti_messaggio(m) for m in messaggi],
            tools=[self._converti_tool(t) for t in strumenti] or None,
            options=self.opzioni,
        )
        chiamate = []
        for tc in risposta.message.tool_calls or []:
            argomenti = tc.function.arguments
            if isinstance(argomenti, str):  # alcuni modelli restituiscono JSON come stringa
                try:
                    argomenti = json.loads(argomenti)
                except json.JSONDecodeError:
                    argomenti = {"_argomenti_non_json": argomenti}
            chiamate.append(ToolCall(id=uuid.uuid4().hex[:8], nome=tc.function.name, argomenti=dict(argomenti or {})))
        return LLMResponse(
            testo=risposta.message.content or "",
            tool_calls=chiamate,
            uso=Uso(risposta.prompt_eval_count or 0, risposta.eval_count or 0),
            modello=risposta.model or self.modello,
            durata_ms=int((time.perf_counter() - inizio) * 1000),
        )
