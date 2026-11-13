"""Confronta le batterie di scenari archiviate in docs/iterazioni/ e produce docs/confronto_batterie.md.

Uso: python docs/confronta_batterie.py
"""

from __future__ import annotations

import json
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
MODELLI = {
    "ollama_qwen2.5_3b": "qwen2.5:3b (locale)",
    "ollama_llama3.2": "llama3.2 3B (locale)",
    "groq_openai_gpt-oss-120b": "gpt-oss-120b (cloud, Groq)",
}
DESCRIZIONI = {
    1: "Base: prompt con regole, schemi compatti, controllo di coerenza",
    2: "+ date risolte dal back-end, piatti per nome, conferma con nomi, prompt anti-invenzione",
    3: "+ esempi con segnaposto astratti, recupero chiamate JSON testuali",
    4: "+ conversione dei tipi, riparazione JSON, giorno della settimana nella conferma",
}


def carica() -> dict[int, dict[str, list[dict]]]:
    batterie: dict[int, dict[str, list[dict]]] = {}
    for cartella in sorted((RADICE / "docs" / "iterazioni").glob("batteria*_*")):
        numero = int(cartella.name[len("batteria")].strip())
        modello = cartella.name.split("_", 1)[1]
        batterie.setdefault(numero, {})[modello] = json.loads((cartella / "risultati.json").read_text(encoding="utf-8"))
    return batterie


def main() -> None:
    batterie = carica()
    numeri = sorted(batterie)
    righe = ["# Confronto tra le batterie di scenari", "", "Generato da `docs/confronta_batterie.py`.", ""]
    righe += ["| Batteria | Modifiche | " + " | ".join(MODELLI.values()) + " |", "|---|---|" + "---|" * len(MODELLI)]
    for n in numeri:
        celle = []
        for m in MODELLI:
            ris = batterie[n].get(m)
            celle.append(f"{sum(r['superato'] for r in ris)}/{len(ris)}" if ris else "-")
        righe.append(f"| {n} | {DESCRIZIONI.get(n, '')} | " + " | ".join(celle) + " |")

    righe += ["", "## Costi medi per scenario", "", "| Batteria | Modello | Token input | Token output | Tempo medio (s) |",
              "|---|---|---|---|---|"]
    for n in numeri:
        for m, etichetta in MODELLI.items():
            ris = batterie[n].get(m)
            if ris:
                k = len(ris)
                righe.append(
                    f"| {n} | {etichetta} | {sum(r['token_input'] for r in ris) // k} | "
                    f"{sum(r['token_output'] for r in ris) // k} | {sum(r['durata_s'] for r in ris) / k:.0f} |"
                )

    for m, etichetta in MODELLI.items():
        righe += ["", f"## Esito per scenario: {etichetta}", "",
                  "| Scenario | " + " | ".join(f"B{n}" for n in numeri) + " |", "|---|" + "---|" * len(numeri)]
        primo = next((batterie[n][m] for n in numeri if m in batterie[n]), None)
        if primo is None:
            continue
        for i, s in enumerate(primo):
            esiti = []
            for n in numeri:
                ris = batterie[n].get(m)
                esiti.append(("✅" if ris[i]["superato"] else "❌") if ris else "-")
            righe.append(f"| {s['id']} {s['titolo']} | " + " | ".join(esiti) + " |")

    uscita = RADICE / "docs" / "confronto_batterie.md"
    uscita.write_text("\n".join(righe) + "\n", encoding="utf-8")
    print(f"Scritto {uscita}")


if __name__ == "__main__":
    main()
