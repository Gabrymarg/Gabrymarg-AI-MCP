"""Accesso alla base dati SQLite."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

RADICE = Path(__file__).resolve().parent.parent
SCHEMA = Path(__file__).resolve().parent / "schema.sql"
DB_PREDEFINITO = RADICE / "data" / "risto.db"


def percorso_db() -> Path:
    return Path(os.environ.get("RISTO_DB", DB_PREDEFINITO))


def connetti(percorso: Path | str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(percorso or percorso_db(), timeout=2.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connessione(percorso: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Apre una connessione, esegue commit se il blocco termina senza errori, rollback altrimenti."""
    conn = connetti(percorso)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def crea_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
