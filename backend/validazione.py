"""Validazione e normalizzazione dei dati in ingresso, comuni a tutti i servizi."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time, timedelta

from backend import clock
from backend.errori import ErroreDominio

GIORNI_SETTIMANA = ["lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica"]
RELATIVI = {"oggi": 0, "stasera": 0, "domani": 1, "dopodomani": 2}
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]
# Senza anno esplicito: una data passata da al massimo questi giorni resta nell'anno corrente
# (così "1 dicembre" detto il 3 dicembre risulta nel passato); oltre, si intende l'anno prossimo.
TOLLERANZA_PASSATO_GIORNI = 31


def _data_senza_anno(giorno: int, mese: int, oggi: date) -> date:
    candidata = date(oggi.year, mese, giorno)
    if candidata < oggi - timedelta(days=TOLLERANZA_PASSATO_GIORNI):
        candidata = date(oggi.year + 1, mese, giorno)
    return candidata


def _data_esplicita(parola: str, oggi: date) -> date | None:
    """'1 dicembre', 'sabato 5 dicembre', '5 dicembre 2026', '5/12', '05/12/2026', '5-12-26'."""
    parola = re.sub(r"^(" + "|".join(GIORNI_SETTIMANA) + r")\s+", "", parola)
    parola = re.sub(r"^(il|l')\s*", "", parola)
    m = re.fullmatch(r"(\d{1,2})\s+(" + "|".join(MESI) + r")(?:\s+(\d{4}))?", parola)
    if m:
        giorno, mese, anno = int(m.group(1)), MESI.index(m.group(2)) + 1, m.group(3)
    else:
        m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2}|\d{4}))?", parola)
        if not m:
            return None
        giorno, mese, anno = int(m.group(1)), int(m.group(2)), m.group(3)
    try:
        if anno:
            anno_n = int(anno) + (2000 if len(anno) == 2 else 0)
            return date(anno_n, mese, giorno)
        return _data_senza_anno(giorno, mese, oggi)
    except ValueError:
        return None


def _senza_accenti(testo: str) -> str:
    testo = unicodedata.normalize("NFKD", testo.strip().lower())
    return "".join(c for c in testo if not unicodedata.combining(c))


def parse_data(valore: str) -> date:
    """Accetta AAAA-MM-GG oppure espressioni relative ('oggi', 'domani', 'dopodomani', 'sabato', ...).

    Il calcolo delle date relative è deterministico: è più affidabile farlo qui che
    lasciarlo al modello linguistico (i modelli piccoli sbagliano spesso).
    """
    try:
        return date.fromisoformat(valore.strip())
    except (ValueError, AttributeError):
        pass
    if isinstance(valore, str):
        parola = _senza_accenti(valore).removeprefix("questo ").removeprefix("questa ").removeprefix("prossimo ")
        oggi = clock.adesso().date()
        if parola in RELATIVI:
            return oggi + timedelta(days=RELATIVI[parola])
        if parola in GIORNI_SETTIMANA:
            return oggi + timedelta(days=(GIORNI_SETTIMANA.index(parola) - oggi.weekday()) % 7)
        esplicita = _data_esplicita(parola, oggi)
        if esplicita:
            return esplicita
    raise ErroreDominio(
        "DATA_NON_VALIDA",
        f"La data '{valore}' non è valida: usare il formato AAAA-MM-GG (es. 2026-12-24), "
        "il giorno e il mese (es. '24 dicembre') oppure 'oggi', 'domani', 'dopodomani' "
        "o il nome del giorno (es. 'sabato').",
    )


def parse_ora(valore: str) -> time:
    try:
        ora = datetime.strptime(valore.strip(), "%H:%M").time()
    except (ValueError, AttributeError):
        raise ErroreDominio(
            "ORA_NON_VALIDA", f"L'ora '{valore}' non è valida: usare il formato HH:MM (es. 20:30)."
        ) from None
    return ora


def normalizza_telefono(valore: str) -> str:
    """Restituisce solo le cifre del numero, senza prefisso internazionale italiano."""
    cifre = re.sub(r"\D", "", valore or "")
    if cifre.startswith("0039"):
        cifre = cifre[4:]
    elif cifre.startswith("39") and len(cifre) > 10:
        cifre = cifre[2:]
    if not 6 <= len(cifre) <= 11:
        raise ErroreDominio(
            "TELEFONO_NON_VALIDO", f"Il numero di telefono '{valore}' non sembra valido."
        )
    return cifre


def stesso_telefono(a: str, b: str) -> bool:
    try:
        return normalizza_telefono(a) == normalizza_telefono(b)
    except ErroreDominio:
        return False


def testo_breve(valore: str | None, campo: str, massimo: int) -> str | None:
    if valore is None:
        return None
    valore = valore.strip()
    if len(valore) > massimo:
        raise ErroreDominio(
            "TESTO_TROPPO_LUNGO", f"Il campo '{campo}' supera i {massimo} caratteri consentiti."
        )
    return valore or None


def nome_cliente(valore: str) -> str:
    nome = testo_breve(valore, "nome_cliente", 80)
    if not nome:
        raise ErroreDominio("NOME_MANCANTE", "Il nome del cliente è obbligatorio.")
    return nome
