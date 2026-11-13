"""Recupero delle chiamate di tool scritte come testo.

Alcuni modelli piccoli (es. llama3.2 via Ollama), invece di usare il meccanismo strutturato
di tool calling, scrivono la chiamata nel testo della risposta, per esempio:
    {"name": "verifica_disponibilita", "parameters": {"data": "domani", ...}}
Senza questo controllo l'harness consegnerebbe al cliente il JSON grezzo.

- Se il testo è una chiamata JSON valida a un tool esistente, viene convertita in una
  ToolCall vera: passa comunque da validazione dello schema e conferma umana.
- Se sembra una chiamata ma è malformata, l'harness la segnala come tale e il ciclo
  chiede al modello di riprovare (o si arresta), senza mostrarla al cliente.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Literal

from harness.llm.base import ToolCall

Stato = Literal["nessuna", "recuperata", "malformata"]

AVVISO_MALFORMATA = (
    "NOTA INTERNA DEL SISTEMA (non è un messaggio del cliente). La tua ultima risposta conteneva una "
    "chiamata di tool scritta come testo e malformata: il cliente non l'ha vista. Se devi usare un tool, "
    "usa il meccanismo di chiamata dei tool; altrimenti rispondi al cliente in italiano, in testo normale."
)


def pulisci_risposta(testo: str) -> str:
    """Rimuove il nome di ruolo ("assistant") che alcuni modelli lasciano trapelare all'inizio del testo."""
    return re.sub(r"^\s*(assistant|assistente)\s*:?\s*\n+", "", testo or "", flags=re.IGNORECASE)


def _ripara_json(testo: str) -> str:
    """Corregge errori di sintassi ricorrenti nei JSON scritti dai modelli piccoli."""
    testo = re.sub(r'"(parameters|arguments)"?\s*\{', r'"\1":{', testo)  # "parameters{  ->  "parameters":{
    testo = re.sub(r",\s*([}\]])", r"\1", testo)  # virgole finali
    return testo


def _ripulisci(testo: str) -> str:
    testo = testo.strip()
    recinto = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", testo, flags=re.S)
    return recinto.group(1).strip() if recinto else testo


def _sembra_chiamata(testo: str, nomi_tool: set[str]) -> bool:
    return testo.startswith("{") and '"name"' in testo or any(f'"{n}"' in testo for n in nomi_tool) and "{" in testo


def estrai(testo: str, nomi_tool: set[str]) -> tuple[Stato, ToolCall | None]:
    pulito = _ripulisci(testo)
    if not _sembra_chiamata(pulito, nomi_tool):
        return "nessuna", None
    try:
        dati: Any = json.loads(pulito)
    except json.JSONDecodeError:
        try:
            dati = json.loads(_ripara_json(pulito))
        except json.JSONDecodeError:
            return "malformata", None
    if isinstance(dati, dict) and isinstance(dati.get("function"), dict):
        dati = dati["function"]
    if not isinstance(dati, dict):
        return "malformata", None
    nome = dati.get("name")
    argomenti = dati.get("parameters", dati.get("arguments", {}))
    if isinstance(argomenti, str):
        try:
            argomenti = json.loads(argomenti)
        except json.JSONDecodeError:
            return "malformata", None
    if nome not in nomi_tool or not isinstance(argomenti, dict):
        return "malformata", None
    return "recuperata", ToolCall(id=uuid.uuid4().hex[:8], nome=nome, argomenti=argomenti)
