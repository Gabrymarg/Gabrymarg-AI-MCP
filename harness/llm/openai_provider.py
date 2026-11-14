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
from typing import Any, Callable

import httpx

from harness.llm.base import LLMProvider, LLMResponse, Messaggio, ToolCall, ToolSpec, Uso


ATTESA_MASSIMA_S = 120.0  # oltre questa attesa richiesta dal fornitore non si riprova


class OpenAICompatibileProvider(LLMProvider):
    nome = "openai"

    def __init__(
        self,
        modello: str,
        base_url: str | None = None,
        api_key: str | None = None,
        temperatura: float = 0.0,
        timeout: float = 120.0,
        max_tentativi: int = 6,
    ):
        super().__init__(modello)
        self.base_url = (base_url or os.environ.get("RISTO_OPENAI_BASE_URL", "http://localhost:11434/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("RISTO_OPENAI_API_KEY", "ollama")
        self.temperatura = temperatura
        self.max_tentativi = max_tentativi
        self.attese_limite = 0  # quante volte si è atteso per i limiti di frequenza
        # Funzione (secondi, tentativo) chiamata prima di ogni attesa imposta dal fornitore: permette
        # all'harness di mostrare all'utente che la risposta è in arrivo e non bloccata.
        self.notifica_attesa: Callable[[float, int], None] | None = None
        self.http = httpx.Client(timeout=timeout)

    def _post_con_riprova(self, corpo: dict[str, Any]) -> httpx.Response:
        """Gestisce i limiti dei piani gratuiti: su 429/5xx attende (Retry-After se presente) e riprova."""
        for tentativo in range(self.max_tentativi):
            r = self.http.post(
                f"{self.base_url}/chat/completions", json=corpo, headers={"Authorization": f"Bearer {self.api_key}"}
            )
            if r.status_code not in (429, 500, 502, 503) or tentativo == self.max_tentativi - 1:
                break
            attesa = r.headers.get("retry-after")
            try:
                richiesta = float(attesa) if attesa else 2.0 * 2**tentativo
            except ValueError:
                richiesta = 2.0 * 2**tentativo
            # Limite giornaliero o attesa lunga: riprovare tra pochi secondi è inutile, meglio fallire subito
            # con un messaggio chiaro (l'utente può cambiare modello) che tenere l'interfaccia in attesa.
            if r.status_code == 429 and ("per day" in r.text or richiesta > ATTESA_MASSIMA_S):
                break
            secondi = min(richiesta, ATTESA_MASSIMA_S)
            self.attese_limite += 1
            if self.notifica_attesa:
                self.notifica_attesa(secondi, tentativo + 1)
            time.sleep(secondi)
        if r.status_code >= 400:
            # Il messaggio d'errore del fornitore (mai la chiave) aiuta a capire limiti e modelli non validi.
            raise RuntimeError(f"HTTP {r.status_code} da {self.base_url}: {r.text[:300]}")
        return r

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
        r = self._post_con_riprova(corpo)
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
            ragionamento=msg.get("reasoning") or msg.get("reasoning_content") or "",
        )


class GroqProvider(OpenAICompatibileProvider):
    """Groq (https://console.groq.com): servizio cloud con piano gratuito e API compatibile OpenAI.

    Chiave letta da GROQ_API_KEY (es. nel file .env, escluso da git).
    """

    nome = "groq"

    def __init__(self, modello: str, **opzioni: Any):
        chiave = os.environ.get("GROQ_API_KEY")
        if not chiave:
            raise RuntimeError("Variabile GROQ_API_KEY mancante: aggiungerla al file .env (vedi .env.example).")
        super().__init__(modello, base_url="https://api.groq.com/openai/v1", api_key=chiave, **opzioni)
