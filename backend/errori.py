"""Errori di dominio del back-end.

Un ErroreDominio rappresenta una violazione di una regola di business
(es. data nel passato, tavoli esauriti). Non è un malfunzionamento: il server MCP
lo converte in un risultato di errore leggibile dal modello, che può così
correggere la richiesta o spiegare il problema all'utente.
"""

from __future__ import annotations

from typing import Any


class ErroreDominio(Exception):
    def __init__(self, codice: str, messaggio: str, dettagli: dict[str, Any] | None = None):
        super().__init__(messaggio)
        self.codice = codice
        self.messaggio = messaggio
        self.dettagli = dettagli or {}

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"codice": self.codice, "messaggio": self.messaggio}
        if self.dettagli:
            d["dettagli"] = self.dettagli
        return d
