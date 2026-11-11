"""Orologio del sistema.

Tutte le regole che dipendono dal "momento attuale" (prenotazioni nel passato,
orario minimo di ritiro, "domani") leggono l'ora da qui. Impostando la variabile
d'ambiente RISTO_ADESSO (es. "2026-12-03T11:00") l'orologio viene fissato:
serve per rendere riproducibili il seed e gli scenari di test.
"""

from __future__ import annotations

import os
from datetime import datetime


def adesso() -> datetime:
    fisso = os.environ.get("RISTO_ADESSO")
    if fisso:
        return datetime.fromisoformat(fisso)
    return datetime.now().replace(second=0, microsecond=0)
