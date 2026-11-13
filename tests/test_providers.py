"""Test dei provider compatibili OpenAI con un server HTTP finto (nessuna chiamata di rete)."""

import json

import httpx
import pytest

from harness.llm.base import Messaggio, ToolSpec
from harness.llm.openai_provider import GroqProvider, OpenAICompatibileProvider

RISPOSTA_TOOL = {
    "model": "finto",
    "choices": [{"message": {"content": None, "tool_calls": [
        {"id": "call_1", "type": "function",
         "function": {"name": "cerca_menu", "arguments": json.dumps({"testo": "carbonara"})}}
    ]}}],
    "usage": {"prompt_tokens": 120, "completion_tokens": 15},
}


def provider_con(gestore) -> OpenAICompatibileProvider:
    p = OpenAICompatibileProvider("finto", base_url="https://esempio.test/v1", api_key="x")
    p.http = httpx.Client(transport=httpx.MockTransport(gestore))
    return p


def test_conversione_tool_call_e_token():
    p = provider_con(lambda req: httpx.Response(200, json=RISPOSTA_TOOL))
    r = p.chat([Messaggio("user", "carbonara?")], [ToolSpec("cerca_menu", "Cerca", {"type": "object"})])
    assert r.tool_calls[0].nome == "cerca_menu" and r.tool_calls[0].argomenti == {"testo": "carbonara"}
    assert (r.uso.token_input, r.uso.token_output) == (120, 15)


def test_riprova_dopo_limite_di_frequenza():
    risposte = iter([httpx.Response(429, headers={"retry-after": "0"}, text="rate limit"),
                     httpx.Response(200, json=RISPOSTA_TOOL)])
    p = provider_con(lambda req: next(risposte))
    r = p.chat([Messaggio("user", "ciao")], [])
    assert r.tool_calls and p.attese_limite == 1


def test_errore_definitivo_senza_chiave_nel_messaggio():
    p = provider_con(lambda req: httpx.Response(401, text='{"error": "invalid api key"}'))
    with pytest.raises(RuntimeError) as exc:
        p.chat([Messaggio("user", "ciao")], [])
    assert "401" in str(exc.value) and "Bearer" not in str(exc.value)


def test_groq_senza_chiave(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        GroqProvider("llama-3.3-70b-versatile")
