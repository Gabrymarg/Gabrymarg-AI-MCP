"""Token di accesso firmati (HMAC-SHA256) con scadenza.

La web app emette il token al login; il server MCP lo verifica a ogni richiesta con la stessa
chiave segreta. Il token contiene id utente, ruolo e scadenza: non è cifrato (non contiene
segreti) ma è firmato, quindi non può essere alterato (es. cambiando il ruolo) senza la chiave.

La chiave si legge da RISTO_SECRET; se manca viene generata una volta in data/.secret
(escluso da git).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from backend.db import RADICE

DURATA_PREDEFINITA_S = 8 * 3600
FILE_SEGRETO = RADICE / "data" / ".secret"


def _chiave() -> bytes:
    valore = os.environ.get("RISTO_SECRET")
    if valore:
        return valore.encode("utf-8")
    if not FILE_SEGRETO.exists():
        FILE_SEGRETO.parent.mkdir(parents=True, exist_ok=True)
        FILE_SEGRETO.write_text(secrets.token_hex(32), encoding="utf-8")
    return FILE_SEGRETO.read_text(encoding="utf-8").strip().encode("utf-8")


def _b64(dati: bytes) -> str:
    return base64.urlsafe_b64encode(dati).rstrip(b"=").decode("ascii")


def _da_b64(testo: str) -> bytes:
    return base64.urlsafe_b64decode(testo + "=" * (-len(testo) % 4))


def emetti(id_utente: int, ruolo: str, durata_s: int = DURATA_PREDEFINITA_S) -> str:
    adesso = int(time.time())
    contenuto = {"sub": id_utente, "ruolo": ruolo, "iat": adesso, "exp": adesso + durata_s, "jti": secrets.token_hex(8)}
    corpo = _b64(json.dumps(contenuto, separators=(",", ":")).encode("utf-8"))
    firma = _b64(hmac.new(_chiave(), corpo.encode("ascii"), hashlib.sha256).digest())
    return f"{corpo}.{firma}"


def verifica(token: str | None) -> dict[str, Any] | None:
    """Restituisce il contenuto del token se la firma è valida e non è scaduto, altrimenti None."""
    if not token or token.count(".") != 1:
        return None
    corpo, firma = token.split(".")
    attesa = _b64(hmac.new(_chiave(), corpo.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(firma, attesa):
        return None
    try:
        contenuto = json.loads(_da_b64(corpo))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(contenuto, dict) or contenuto.get("exp", 0) < time.time():
        return None
    return contenuto


def percorso_segreto() -> Path:
    return FILE_SEGRETO
