"""Log strutturato JSON Lines: un evento per riga, un file per sessione.

Ogni evento contiene: istante, id della sessione, numero del turno di conversazione,
numero dell'iterazione del ciclo agentico, tipo di evento e i dati specifici.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


class LoggerJSONL:
    def __init__(self, cartella: Path, prefisso: str = "sessione"):
        cartella.mkdir(parents=True, exist_ok=True)
        self.id_sessione = uuid.uuid4().hex[:8]
        momento = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.percorso = cartella / f"{prefisso}_{momento}_{self.id_sessione}.jsonl"
        self._file = self.percorso.open("a", encoding="utf-8")
        self.eventi: list[dict[str, Any]] = []  # copia in memoria, utile a test e report
        # Funzioni chiamate a ogni evento (es. la web app che mostra il ciclo agentico in tempo reale).
        self.ascoltatori: list[Callable[[dict[str, Any]], None]] = []

    def registra(self, tipo: str, turno: int, iterazione: int | None = None, **dati: Any) -> dict[str, Any]:
        evento = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "sessione": self.id_sessione,
            "turno": turno,
            "iterazione": iterazione,
            "tipo": tipo,
            **dati,
        }
        self.eventi.append(evento)
        self._file.write(json.dumps(evento, ensure_ascii=False, default=str) + "\n")
        self._file.flush()
        for ascoltatore in self.ascoltatori:
            ascoltatore(evento)
        return evento

    def chiudi(self) -> None:
        self._file.close()


class LoggerNullo(LoggerJSONL):
    """Logger in memoria, senza file (per i test)."""

    def __init__(self) -> None:
        self.id_sessione = "test"
        self.percorso = None
        self.eventi = []
        self.ascoltatori = []

    def registra(self, tipo: str, turno: int, iterazione: int | None = None, **dati: Any) -> dict[str, Any]:
        evento = {"turno": turno, "iterazione": iterazione, "tipo": tipo, **dati}
        self.eventi.append(evento)
        for ascoltatore in self.ascoltatori:
            ascoltatore(evento)
        return evento

    def chiudi(self) -> None:
        pass
