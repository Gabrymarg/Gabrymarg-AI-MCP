"""Configurazione dell'harness, letta da variabili d'ambiente (con valori predefiniti)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent


def carica_env(percorso: Path = RADICE / ".env") -> None:
    """Legge le righe CHIAVE=valore del file .env (escluso da git), senza sovrascrivere l'ambiente."""
    if not percorso.exists():
        return
    for riga in percorso.read_text(encoding="utf-8-sig").splitlines():
        riga = riga.strip()
        if not riga or riga.startswith("#") or "=" not in riga:
            continue
        chiave, valore = riga.split("=", 1)
        os.environ.setdefault(chiave.strip(), valore.strip().strip('"').strip("'"))


carica_env()


@dataclass
class Config:
    provider: str = field(default_factory=lambda: os.environ.get("RISTO_LLM_PROVIDER", "ollama"))
    modello: str = field(default_factory=lambda: os.environ.get("RISTO_MODELLO", "qwen2.5:3b"))
    max_iterazioni: int = field(default_factory=lambda: int(os.environ.get("RISTO_MAX_ITERAZIONI", "8")))
    max_errori_consecutivi: int = field(default_factory=lambda: int(os.environ.get("RISTO_MAX_ERRORI", "3")))
    max_ripetizioni_chiamata: int = 2  # stessa chiamata (nome + argomenti) ripetuta più volte = loop
    # Respinge (una volta per turno) le risposte che affermano operazioni non eseguite.
    guardrail_coerenza: bool = field(default_factory=lambda: os.environ.get("RISTO_GUARDRAIL", "1") != "0")
    # Gestione del contesto: i risultati dei tool dei turni PRECEDENTI vengono accorciati a questo numero
    # di caratteri prima di essere rinviati al modello (il log e la cronologia interna restano completi).
    max_caratteri_risultati_storici: int = field(
        default_factory=lambda: int(os.environ.get("RISTO_MAX_RISULTATI_STORICI", "400"))
    )
    timeout_tool_s: float = field(default_factory=lambda: float(os.environ.get("RISTO_TIMEOUT_TOOL", "15")))
    cartella_log: Path = field(default_factory=lambda: Path(os.environ.get("RISTO_LOG_DIR", RADICE / "logs")))
    # Comando che avvia il server MCP (trasporto stdio).
    comando_server: list[str] = field(default_factory=lambda: [sys.executable, "-m", "mcp_server.server"])
    cartella_server: Path = RADICE
