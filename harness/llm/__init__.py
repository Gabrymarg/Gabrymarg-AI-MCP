"""Livello di astrazione dal fornitore del modello linguistico."""

from harness.llm.base import LLMProvider, LLMResponse, Messaggio, ToolCall, ToolSpec, Uso


def crea_provider(nome: str, modello: str, **opzioni) -> LLMProvider:
    """Factory: l'unico punto del codice che conosce le implementazioni concrete."""
    if nome == "ollama":
        from harness.llm.ollama_provider import OllamaProvider

        return OllamaProvider(modello, **opzioni)
    if nome == "openai":
        from harness.llm.openai_provider import OpenAICompatibileProvider

        return OpenAICompatibileProvider(modello, **opzioni)
    if nome == "groq":
        from harness.llm.openai_provider import GroqProvider

        return GroqProvider(modello, **opzioni)
    raise ValueError(f"Provider sconosciuto: {nome!r} (valori ammessi: ollama, openai, groq)")


__all__ = ["LLMProvider", "LLMResponse", "Messaggio", "ToolCall", "ToolSpec", "Uso", "crea_provider"]
