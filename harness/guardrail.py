"""Guardrail di coerenza: la risposta finale non deve affermare operazioni mai eseguite.

I modelli piccoli tendono a "dichiarare" una prenotazione o un ordine dopo aver solo
verificato la disponibilità, senza chiamare il tool di scrittura. L'harness confronta
la risposta con ciò che è realmente avvenuto nel turno: se il testo afferma
un'operazione completata ma nessun tool di scrittura è andato a buon fine, rimanda il
modello indietro con un avviso (una sola volta per turno).
"""

from __future__ import annotations

import re

_AFFERMAZIONI = [
    r"(?<!non )\b(ho|abbiamo)\s+(appena\s+)?(prenotato|registrato|confermato|cancellato|annullato|modificato|spostato|inviato|creato)\b",
    r"\b(prenotazione|ordine)\b[^.?!]{0,60}\b(è|e')\s+(stat[ao]\s+)?(confermat|registrat|effettuat|creat|cancellat|annullat|modificat|inviat)",
    r"\btutto\s+(pronto|fatto|a posto|confermato|prenotato)\b",
    r"\bnon c'è bisogno di confermare\b",
    r"\b(il suo|il tuo|vostro)\s+tavolo\s+è\s+(prenotato|riservato)\b",
]
_REGEX = [re.compile(p, re.IGNORECASE) for p in _AFFERMAZIONI]

AVVISO = (
    "[Controllo automatico dell'harness] In questo turno NESSUNA operazione di scrittura è stata eseguita: "
    "non esiste alcuna nuova prenotazione, modifica, cancellazione o ordine. "
    "Se il cliente vuole davvero procedere e hai tutti i dati necessari, chiama ORA il tool appropriato "
    "(il sistema chiederà conferma al cliente). Se mancano dati, chiedili. "
    "Se stavi solo riportando informazioni già lette da un tool, ripeti la risposta senza affermare "
    "di aver eseguito operazioni."
)


def afferma_operazione(testo: str) -> bool:
    return any(r.search(testo) for r in _REGEX)
