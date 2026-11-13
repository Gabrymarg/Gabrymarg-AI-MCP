"""Genera i PNG dei diagrammi PlantUML tramite il server pubblico plantuml.com.

Uso: python docs/diagrammi/genera_png.py
(In alternativa, con Java installato: java -jar plantuml.jar docs/diagrammi/*.puml)
"""

from __future__ import annotations

import string
import zlib
from pathlib import Path

import httpx

CARTELLA = Path(__file__).resolve().parent
SERVER = "https://www.plantuml.com/plantuml/png/"
ALFABETO = string.digits + string.ascii_uppercase + string.ascii_lowercase + "-_"


def codifica(testo: str) -> str:
    """Codifica PlantUML: deflate grezzo + base64 con alfabeto proprio."""
    compresso = zlib.compress(testo.encode("utf-8"), 9)[2:-4]
    out = []
    for i in range(0, len(compresso), 3):
        blocco = compresso[i:i + 3].ljust(3, b"\0")
        n = (blocco[0] << 16) | (blocco[1] << 8) | blocco[2]
        out.append("".join(ALFABETO[(n >> s) & 0x3F] for s in (18, 12, 6, 0)))
    return "".join(out)


def main() -> None:
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for sorgente in sorted(CARTELLA.glob("*.puml")):
            r = client.get(SERVER + codifica(sorgente.read_text(encoding="utf-8")))
            if r.status_code != 200 or not r.content.startswith(b"\x89PNG"):
                print(f"ERRORE {sorgente.name}: HTTP {r.status_code}")
                continue
            destinazione = sorgente.with_suffix(".png")
            destinazione.write_bytes(r.content)
            print(f"{destinazione.name}: {len(r.content) // 1024} KB")


if __name__ == "__main__":
    main()
