import sys
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

from backend.db import connetti  # noqa: E402
from backend.seed import crea_database  # noqa: E402

ADESSO = "2026-12-03T11:00"  # giovedì


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Database nuovo e popolato per ogni test, con orologio fissato."""
    monkeypatch.setenv("RISTO_ADESSO", ADESSO)
    percorso = tmp_path / "test.db"
    monkeypatch.setenv("RISTO_DB", str(percorso))
    info = crea_database(percorso)
    conn = connetti(percorso)
    yield conn, info
    conn.close()


def id_piatto(conn, nome):
    return conn.execute("SELECT id_articolo FROM ARTICOLI WHERE nome = ?", (nome,)).fetchone()[0]
