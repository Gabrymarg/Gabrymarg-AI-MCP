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
    notifiche = []
    p.notifica_attesa = lambda secondi, tentativo: notifiche.append((secondi, tentativo))
    r = p.chat([Messaggio("user", "ciao")], [])
    assert r.tool_calls and p.attese_limite == 1
    assert notifiche == [(0.0, 1)]  # l'attesa è stata segnalata prima di riprovare


def test_limite_giornaliero_nessun_tentativo_inutile():
    """Con il limite giornaliero (TPD) superato non si riprova: si fallisce subito con l'errore 429."""
    chiamate = []

    def gestore(req):
        chiamate.append(1)
        return httpx.Response(429, headers={"retry-after": "988"},
                              text='{"error": {"message": "Rate limit reached ... on tokens per day (TPD)"}}')

    p = provider_con(gestore)
    with pytest.raises(RuntimeError, match="429"):
        p.chat([Messaggio("user", "ciao")], [])
    assert len(chiamate) == 1 and p.attese_limite == 0


def test_errore_definitivo_senza_chiave_nel_messaggio():
    p = provider_con(lambda req: httpx.Response(401, text='{"error": "invalid api key"}'))
    with pytest.raises(RuntimeError) as exc:
        p.chat([Messaggio("user", "ciao")], [])
    assert "401" in str(exc.value) and "Bearer" not in str(exc.value)


def test_groq_senza_chiave(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        GroqProvider("llama-3.3-70b-versatile")


# ------------------------------------------------------------------ Ollama: streaming e ragionamento


def test_ollama_streaming_e_ragionamento():
    from types import SimpleNamespace as NS

    from harness.llm.ollama_provider import OllamaProvider

    def pezzo(contenuto="", pensiero=None, chiamate=None, fine=False):
        return NS(message=NS(content=contenuto, thinking=pensiero, tool_calls=chiamate or []),
                  prompt_eval_count=120 if fine else None, eval_count=30 if fine else None, model="finto")

    class ClientFinto:
        def show(self, modello):
            return NS(capabilities=["completion", "tools", "thinking"])

        def chat(self, stream=False, **richiesta):
            assert stream and richiesta["think"] is True
            chiamata = NS(function=NS(name="cerca_menu", arguments={"testo": "tiramisù"}))
            return iter([pezzo(pensiero="Serve il menu. "), pezzo(pensiero="Cerco il dolce."),
                         pezzo("Un attimo"), pezzo(chiamate=[chiamata]), pezzo(fine=True)])

    p = OllamaProvider("finto")
    p.client = ClientFinto()
    ricevuti = []
    p.notifica_flusso = lambda tipo, frammento: ricevuti.append((tipo, frammento))
    r = p.chat([], [])
    assert ricevuti == [("pensiero", "Serve il menu. "), ("pensiero", "Cerco il dolce."), ("testo", "Un attimo")]
    assert r.ragionamento == "Serve il menu. Cerco il dolce." and r.testo == "Un attimo"
    assert r.tool_calls[0].nome == "cerca_menu" and r.uso.token_input == 120 and r.uso.token_output == 30
