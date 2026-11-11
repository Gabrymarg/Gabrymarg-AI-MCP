"""Orari di apertura del ristorante."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


@dataclass(frozen=True)
class Turno:
    nome: str
    apertura: time
    chiusura: time

    def contiene(self, ora: time, margine_finale_min: int = 0) -> bool:
        limite = (datetime.combine(date.min, self.chiusura) - timedelta(minutes=margine_finale_min)).time()
        return self.apertura <= ora <= limite

    def descrizione(self) -> str:
        return f"{self.nome} {self.apertura:%H:%M}-{self.chiusura:%H:%M}"


def turni_del_giorno(conn: sqlite3.Connection, giorno: date) -> list[Turno]:
    righe = conn.execute(
        "SELECT turno, apertura, chiusura FROM ORARI_APERTURA WHERE giorno_settimana = ? ORDER BY apertura",
        (giorno.weekday(),),
    ).fetchall()
    return [
        Turno(r["turno"], time.fromisoformat(r["apertura"]), time.fromisoformat(r["chiusura"]))
        for r in righe
    ]


def descrizione_orari(conn: sqlite3.Connection, giorno: date) -> str:
    turni = turni_del_giorno(conn, giorno)
    nome_giorno = GIORNI[giorno.weekday()]
    if not turni:
        return f"{nome_giorno} il ristorante è chiuso"
    return f"{nome_giorno}: " + ", ".join(t.descrizione() for t in turni)
