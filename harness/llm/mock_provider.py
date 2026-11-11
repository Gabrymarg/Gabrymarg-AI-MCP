"""Provider fittizio con risposte predefinite, per test deterministici del ciclo agentico.

Ogni elemento del copione è una LLMResponse oppure una funzione che riceve i
messaggi e restituisce una LLMResponse (utile per reagire ai risultati dei tool).
"""

from __future__ import annotations

from typing import Callable, Union

from harness.llm.base import LLMProvider, LLMResponse, Messaggio, ToolCall, ToolSpec, Uso

Passo = Union[LLMResponse, Callable[[list[Messaggio]], LLMResponse]]


def risposta(testo: str = "", *chiamate: tuple[str, dict], token: tuple[int, int] = (100, 20)) -> LLMResponse:
    return LLMResponse(
        testo=testo,
        tool_calls=[ToolCall(id=f"c{i}", nome=n, argomenti=a) for i, (n, a) in enumerate(chiamate)],
        uso=Uso(*token),
        modello="mock",
    )


class MockProvider(LLMProvider):
    nome = "mock"

    def __init__(self, copione: list[Passo], ripeti_ultimo: bool = False):
        super().__init__("mock")
        self.copione = list(copione)
        self.ripeti_ultimo = ripeti_ultimo
        self.chiamate: list[list[Messaggio]] = []

    def chat(self, messaggi: list[Messaggio], strumenti: list[ToolSpec]) -> LLMResponse:
        self.chiamate.append(list(messaggi))
        if not self.copione:
            raise RuntimeError("Copione del MockProvider esaurito")
        passo = self.copione[0] if (self.ripeti_ultimo and len(self.copione) == 1) else self.copione.pop(0)
        return passo(messaggi) if callable(passo) else passo
