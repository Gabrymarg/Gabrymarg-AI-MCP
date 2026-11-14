"""Tipi neutri rispetto al fornitore e interfaccia astratta LLMProvider.

Il ciclo agentico lavora solo con questi tipi: per cambiare modello o fornitore
basta una nuova sottoclasse di LLMProvider che traduca da/verso il formato del fornitore.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Literal


@dataclass
class ToolCall:
    id: str
    nome: str
    argomenti: dict[str, Any]


@dataclass
class Messaggio:
    ruolo: Literal["system", "user", "assistant", "tool"]
    contenuto: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)  # solo ruolo "assistant"
    tool_call_id: str | None = None  # solo ruolo "tool"
    nome_tool: str | None = None  # solo ruolo "tool"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"ruolo": self.ruolo, "contenuto": self.contenuto}
        if self.tool_calls:
            d["tool_calls"] = [{"id": t.id, "nome": t.nome, "argomenti": t.argomenti} for t in self.tool_calls]
        if self.nome_tool:
            d["nome_tool"] = self.nome_tool
        return d


@dataclass
class ToolSpec:
    """Descrizione di un tool come la vede l'harness (ricavata dalla lista MCP)."""

    nome: str
    descrizione: str
    parametri: dict[str, Any]  # JSON Schema dei parametri d'ingresso
    scrittura: bool = False  # derivato da readOnlyHint
    distruttivo: bool = False  # derivato da destructiveHint


@dataclass
class Uso:
    token_input: int = 0
    token_output: int = 0

    @property
    def totale(self) -> int:
        return self.token_input + self.token_output


@dataclass
class LLMResponse:
    testo: str
    tool_calls: list[ToolCall]
    uso: Uso
    modello: str
    durata_ms: int = 0
    ragionamento: str = ""  # "thinking" del modello, se il modello lo produce e il fornitore lo restituisce


class LLMProvider(ABC):
    nome: str = "astratto"

    def __init__(self, modello: str):
        self.modello = modello
        # Facoltativa: funzione (tipo, frammento) chiamata durante la generazione, con tipo "pensiero" o
        # "testo". Permette all'interfaccia di mostrare la risposta mentre il modello la scrive.
        self.notifica_flusso: Callable[[str, str], None] | None = None

    @abstractmethod
    def chat(self, messaggi: list[Messaggio], strumenti: list[ToolSpec]) -> LLMResponse:
        """Invia la conversazione e i tool disponibili, restituisce la risposta del modello.

        Solleva un'eccezione se il fornitore non è raggiungibile o risponde con errore.
        """

    def descrizione(self) -> str:
        return f"{self.nome}:{self.modello}"
