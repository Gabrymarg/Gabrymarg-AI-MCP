"""Guardrail di coerenza: la risposta finale non deve affermare operazioni mai eseguite.

I modelli piccoli tendono a "dichiarare" una prenotazione o un ordine dopo aver solo
verificato la disponibilità, senza chiamare il tool di scrittura. L'harness confronta
la risposta con ciò che è realmente avvenuto nel turno: se il testo afferma
un'operazione completata ma nessun tool di scrittura è andato a buon fine, rimanda il
modello indietro con un avviso (una sola volta per turno).
"""

from __future__ import annotations

import json
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
    "NOTA INTERNA DEL SISTEMA (non è un messaggio del cliente: il cliente non la vede e non va citata). "
    "La tua ultima risposta NON è stata inviata al cliente perché afferma un'operazione mai eseguita: "
    "in questo turno nessuna prenotazione, modifica, cancellazione o ordine è stato registrato. "
    "Scegli UNA azione: (a) se hai tutti i dati, chiama ora il tool di scrittura appropriato "
    "(il sistema chiederà conferma al cliente); (b) se mancano dati, chiedili al cliente; "
    "(c) se stavi solo riportando informazioni lette da un tool, riscrivi la risposta per il cliente "
    "senza dire di aver registrato nulla."
)


def afferma_operazione(testo: str) -> bool:
    return any(r.search(testo) for r in _REGEX)


# ---------------------------------------------------------------------------- riferimenti verificati
#
# Secondo controllo, strutturato: ogni numero di prenotazione o d'ordine citato nella risposta deve
# comparire nei risultati dei tool della conversazione (o essere stato scritto dall'utente). Un numero
# che non viene da nessuna fonte è inventato: il cliente si presenterebbe con una prenotazione inesistente.

_TIPI = {"prenotazion": "prenotazione", "ordin": "ordine"}
_RIFERIMENTO = re.compile(
    r"\b(prenotazion[ei]|ordin[ei])\b"                      # prenotazione / ordine
    r"(?:\s+(?:n\.?|nr\.?|numero|num\.?|#|n°|nº))?"          # n. / numero / #
    r"(?:\s*(?:è|e'|:)\s*(?:il|la|lo)?)?"                    # "è la", ":"
    r"\s*#?\s*(\d{1,6})\b"
    r"(?!\s*(?:person|copert|porzion|pezz|piatt|post|or[ae]\b|minut|x\b|€|euro))",
    re.IGNORECASE,
)
_NUMERO_DEL = re.compile(
    r"\bnumero\s+(?:della|del|dell')?\s*(?:tua|sua|vostra|vostro|tuo|suo)?\s*(prenotazione|ordine)"
    r"\s*(?:è|e'|:)?\s*(?:il|la)?\s*#?\s*(\d{1,6})\b",
    re.IGNORECASE,
)
_CHIAVI_ID = {"id_prenotazione": "prenotazione", "id_ordine": "ordine"}


def riferimenti_citati(testo: str) -> set[tuple[str, int]]:
    """Coppie (tipo, numero) citate nel testo, es. {("prenotazione", 186)}."""
    trovati = set()
    for regex in (_RIFERIMENTO, _NUMERO_DEL):
        for parola, numero in regex.findall(testo):
            tipo = next(t for radice, t in _TIPI.items() if parola.lower().startswith(radice))
            trovati.add((tipo, int(numero)))
    return trovati


def _id_nel_risultato(dato, trovati: set[tuple[str, int]]) -> None:
    if isinstance(dato, dict):
        for chiave, valore in dato.items():
            if chiave in _CHIAVI_ID and isinstance(valore, int):
                trovati.add((_CHIAVI_ID[chiave], valore))
            else:
                _id_nel_risultato(valore, trovati)
    elif isinstance(dato, list):
        for elemento in dato:
            _id_nel_risultato(elemento, trovati)


def riferimenti_noti(messaggi) -> tuple[set[tuple[str, int]], set[int]]:
    """Riferimenti presenti nei risultati dei tool e numeri scritti dall'utente nella conversazione."""
    dai_tool: set[tuple[str, int]] = set()
    dall_utente: set[int] = set()
    for m in messaggi:
        if m.ruolo == "tool":
            try:
                _id_nel_risultato(json.loads(m.contenuto), dai_tool)
            except (json.JSONDecodeError, TypeError):
                pass
        elif m.ruolo == "user":
            dall_utente.update(int(n) for n in re.findall(r"\d{1,6}", m.contenuto))
    return dai_tool, dall_utente


def riferimenti_inventati(testo: str, messaggi) -> list[str]:
    dai_tool, dall_utente = riferimenti_noti(messaggi)
    return sorted(
        f"{tipo} n. {numero}"
        for tipo, numero in riferimenti_citati(testo)
        if (tipo, numero) not in dai_tool and numero not in dall_utente
    )


def avviso_riferimenti(inventati: list[str]) -> str:
    return (
        "NOTA INTERNA DEL SISTEMA (non è un messaggio del cliente: il cliente non la vede e non va citata). "
        f"La tua ultima risposta NON è stata inviata al cliente perché cita {', '.join(inventati)}, "
        "ma nessun risultato dei tool contiene questo numero: è un dato inventato. "
        "Usa solo i numeri restituiti dai tool. Se ti serve un numero, ottienilo con il tool appropriato "
        "(es. trova_prenotazioni, stato_ordine); altrimenti riscrivi la risposta senza citarlo."
    )
