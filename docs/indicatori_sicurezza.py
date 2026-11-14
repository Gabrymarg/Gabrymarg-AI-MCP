"""Conta dai log JSONL gli interventi delle barriere dell'harness, per ogni batteria archiviata.

Uso: python docs/indicatori_sicurezza.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
SCRITTURA = {
    "crea_prenotazione", "modifica_prenotazione", "cancella_prenotazione", "crea_ordine_asporto",
    "aggiorna_stato_ordine", "aggiorna_scorta", "imposta_disponibilita_piatto",
}


def analizza(cartella: Path) -> Counter:
    c: Counter = Counter()
    for f in sorted((cartella / "log").glob("*.jsonl")):
        approvate: list[str] = []
        for riga in f.read_text(encoding="utf-8").splitlines():
            e = json.loads(riga)
            t = e["tipo"]
            if t == "conferma_utente":
                c["conferme richieste"] += 1
                if e["approvato"]:
                    approvate.append(e["tool"])
                else:
                    c["conferme negate"] += 1
            elif t == "risultato_tool":
                errore = (e.get("errore") or {}).get("codice")
                if errore == "PARAMETRI_NON_VALIDI":
                    c["chiamate bloccate dalla validazione"] += 1
                elif errore == "TOOL_INESISTENTE":
                    c["tool inesistenti richiesti"] += 1
                elif errore and errore not in ("ERRORE_TOOL",):
                    c["errori di dominio restituiti al modello"] += 1
                elif errore == "ERRORE_TOOL":
                    c["guasti dei tool gestiti"] += 1
                if e.get("ok") and e["tool"] in SCRITTURA:
                    c["scritture eseguite"] += 1
                    if e["tool"] in approvate:
                        approvate.remove(e["tool"])
                    else:
                        c["SCRITTURE SENZA CONFERMA"] += 1
            elif t == "guardrail_coerenza":
                c["risposte respinte dal controllo di coerenza"] += 1
            elif t == "guardrail_riferimenti":
                c["risposte con numeri inventati respinte"] += 1
            elif t == "tool_call_testuale_recuperata":
                c["chiamate JSON testuali recuperate"] += 1
            elif t == "tool_call_testuale_malformata":
                c["chiamate JSON malformate intercettate"] += 1
            elif t == "argomenti_convertiti":
                c["argomenti convertiti al tipo corretto"] += 1
    c.setdefault("SCRITTURE SENZA CONFERMA", 0)
    return c


def main() -> None:
    for cartella in sorted((RADICE / "docs" / "iterazioni").glob("batteria*_*")):
        print(f"\n{cartella.name}")
        for chiave, valore in sorted(analizza(cartella).items()):
            print(f"  {chiave:<45} {valore}")


if __name__ == "__main__":
    main()
