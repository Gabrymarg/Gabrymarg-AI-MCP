"""Provider per qualsiasi servizio compatibile con l'API OpenAI Chat Completions.

Funziona con Ollama stesso (http://localhost:11434/v1), con servizi che offrono un
piano gratuito e un endpoint compatibile, o con OpenAI. Dimostra che il ciclo
agentico non dipende dal fornitore: cambia solo questa classe.

Configurazione: RISTO_OPENAI_BASE_URL, RISTO_OPENAI_API_KEY.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from harness.llm.base import LLMProvider, LLMResponse, Messaggio, ToolCall, ToolSpec, Uso


class OpenAICompatibileProvider(LLMProvider):
    nome = "openai"

    def __init__(
        self,
        modello: str,
        base_url: str | None = None,
        api_key: str | None = None,
        temperatura: float = 0.0,
        timeout: float = 120.0,
    ):
        super().__init__(modello)
        self.base_url = (base_url or os.environ.get("RISTO_OPENAI_BASE_URL", "http://localhost:11434/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("RISTO_OPENAI_API_KEY", "ollama")
        self.temperatura = temperatura
        self.http = httpx.Client(timeout=timeout)

    @staticmethod
    def _converti_messaggio(m: Messaggio) -> dict[str, Any]:
        if m.ruolo == "tool":
            return {"role": "tool", "content": m.contenuto, "tool_call_id": m.tool_call_id}
        d: dict[str, Any] = {"role": m.ruolo, "content": m.contenuto}
        if m.tool_calls:
            d["tool_calls"] = [
                {"id": t.id, "type": "function", "function": {"name": t.nome, "arguments": json.dumps(t.argomenti)}}
                for t in m.tool_calls
            ]
        return d

    def chat(self, messaggi: list[Messaggio], strumenti: list[ToolSpec]) -> LLMResponse:
        corpo: dict[str, Any] = {
            "model": self.modello,
            "messages": [self._converti_messaggio(m) for m in messaggi],
            "temperature": self.temperatura,
        }
        if strumenti:
            corpo["tools"] = [
                {"type": "function", "function": {"name": t.nome, "description": t.descrizione, "parameters": t.parametri}}
                for t in strumenti
            ]
        inizio = time.perf_counter()
        r = self.http.post(
            f"{self.base_url}/chat/completions", json=corpo, headers={"Authorization": f"Bearer {self.api_key}"}
        )
        r.raise_for_status()
        dati = r.json()
        msg = dati["choices"][0]["message"]
        chiamate = []
        for tc in msg.get("tool_calls") or []:
            try:
                argomenti = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                argomenti = {"_argomenti_non_json": tc["function"].get("arguments")}
            chiamate.append(ToolCall(id=tc.get("id") or "", nome=tc["function"]["name"], argomenti=argomenti))
        uso = dati.get("usage") or {}
        return LLMResponse(
            testo=msg.get("content") or "",
            tool_calls=chiamate,
            uso=Uso(uso.get("prompt_tokens", 0), uso.get("completion_tokens", 0)),
            modello=dati.get("model", self.modello),
            durata_ms=int((time.perf_counter() - inizio) * 1000),
        )
