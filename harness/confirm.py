"""Human-in-the-loop: conferma dell'utente prima dei tool con effetti di scrittura."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable, Iterable

from harness.llm.base import ToolSpec

# Una funzione di conferma riceve il tool e gli argomenti e restituisce True se l'utente approva.
FunzioneConferma = Callable[[ToolSpec, dict[str, Any]], bool]

ETICHETTE = {
    "crea_prenotazione": "Nuova prenotazione",
    "modifica_prenotazione": "Modifica della prenotazione",
    "cancella_prenotazione": "CANCELLAZIONE della prenotazione",
    "crea_ordine_asporto": "Nuovo ordine da asporto",
}


GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


def _con_giorno(valore: Any) -> str:
    """'2026-12-11' -> '2026-12-11 (venerdì)': rende visibile un errore sul giorno a chi conferma."""
    try:
        return f"{valore} ({GIORNI[date.fromisoformat(str(valore)).weekday()]})"
    except ValueError:
        return str(valore)


def riepilogo(spec: ToolSpec, argomenti: dict[str, Any]) -> str:
    righe = [f"{ETICHETTE.get(spec.nome, spec.nome)}:"]
    for chiave, valore in argomenti.items():
        if valore in (None, "", []):
            continue
        if chiave == "righe" and isinstance(valore, list):
            for r in valore:
                piatto = r.get("nome") or f"piatto n. {r.get('id_articolo')}"
                righe.append(f"   - {r.get('quantita', 1)} x {piatto}"
                             + (f" ({r['note']})" if r.get("note") else ""))
            continue
        righe.append(f"   {chiave.replace('_', ' ')}: {_con_giorno(valore) if 'data' in chiave else valore}")
    if spec.distruttivo:
        righe.append("   ATTENZIONE: l'operazione non è annullabile.")
    return "\n".join(righe)


def conferma_interattiva(spec: ToolSpec, argomenti: dict[str, Any]) -> bool:
    print("\n" + riepilogo(spec, argomenti))
    try:
        risposta = input("   Confermi? [s/N] ").strip().lower()
    except EOFError:
        return False
    return risposta in {"s", "si", "sì", "y", "yes"}


def conferma_scriptata(risposte: Iterable[bool]) -> FunzioneConferma:
    """Conferme predefinite (scenari di test). Se finiscono, nega per sicurezza."""
    coda = list(risposte)

    def conferma(spec: ToolSpec, argomenti: dict[str, Any]) -> bool:
        return coda.pop(0) if coda else False

    return conferma
