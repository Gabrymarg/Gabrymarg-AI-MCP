"""Genera docs/tools.md interrogando il server MCP: la documentazione resta allineata al codice.

Uso: python docs/genera_doc_tool.py
Per ogni tool: descrizione, effetti sui dati (dalle annotazioni), schema d'ingresso e d'uscita,
un esempio di invocazione eseguito davvero su un database di prova e il relativo risultato.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

from mcp import Client, StdioServerParameters  # noqa: E402

from backend.seed import crea_database  # noqa: E402

ADESSO = "2026-12-03T11:00"

ESEMPI = {
    "orari_apertura": {},
    "cerca_menu": {"categoria": "Secondi", "escludi_allergeni": ["glutine", "latte"]},
    "dettaglio_piatto": {"id_articolo": 13},
    "verifica_disponibilita": {"data": "sabato", "ora": "20:30", "coperti": 4},
    "trova_prenotazioni": {"telefono": "333 1234567"},
    "crea_prenotazione": {"data": "domani", "ora": "20:30", "coperti": 2, "nome_cliente": "Marco Gallo",
                          "telefono": "340 555 1234", "note": "Tavolo tranquillo"},
    "modifica_prenotazione": {"id_prenotazione": 86, "telefono": "3331234567", "ora": "21:00", "coperti": 4},
    "cancella_prenotazione": {"id_prenotazione": 86, "telefono": "3331234567"},
    "crea_ordine_asporto": {"nome_cliente": "Paolo Riva", "telefono": "320 987 6543", "ora_ritiro": "20:30",
                            "righe": [{"id_articolo": 10, "quantita": 2}, {"id_articolo": 35, "quantita": 1}]},
    "stato_ordine": {"id_ordine": 1, "telefono": "347 111 2233"},
}


def effetti(a) -> str:
    if a.read_only_hint:
        return "Sola lettura (`readOnlyHint: true`): nessun effetto sui dati, non richiede conferma."
    testo = "**Scrittura** (`readOnlyHint: false`): modifica la base dati; l'harness chiede conferma all'utente."
    if a.destructive_hint:
        testo += " **Distruttivo** (`destructiveHint: true`): l'operazione non è annullabile."
    return testo


def blocco_json(dati) -> list[str]:
    return ["```json", json.dumps(dati, ensure_ascii=False, indent=2), "```"]


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "doc.db"
        os.environ["RISTO_ADESSO"] = ADESSO
        crea_database(db)
        env = {**os.environ, "RISTO_DB": str(db), "RISTO_ADESSO": ADESSO}
        params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"], cwd=str(RADICE), env=env)
        righe = [
            "# Documentazione dei tool MCP",
            "",
            "Generata automaticamente da `docs/genera_doc_tool.py` interrogando il server (`tools/list`).",
            f"Gli esempi sono stati eseguiti realmente su un database di prova (seed 42, orologio fissato a {ADESSO}).",
            "",
            "| Tool | Effetti | Parametri obbligatori |",
            "|---|---|---|",
        ]
        dettagli: list[str] = []
        async with Client(params) as c:
            for t in (await c.list_tools()).tools:
                a = t.annotations
                tipo = "lettura" if a.read_only_hint else ("scrittura distruttiva" if a.destructive_hint else "scrittura")
                righe.append(f"| `{t.name}` | {tipo} | {', '.join(t.input_schema.get('required', [])) or '-'} |")
                esempio = ESEMPI[t.name]
                r = await c.call_tool(t.name, esempio)
                risultato = r.structured_content if not r.is_error else r.content[0].text
                dettagli += [
                    "", f"## `{t.name}`", "", inspect.cleandoc(t.description or ""), "",
                    f"**Effetti sui dati:** {effetti(a)}", "",
                    "**Schema dei parametri di ingresso:**", "", *blocco_json(t.input_schema), "",
                    "**Schema di uscita:**", "", *blocco_json(t.output_schema), "",
                    "**Esempio di invocazione:**", "",
                    *blocco_json({"name": t.name, "arguments": esempio}), "",
                    "**Risultato:**", "", *blocco_json(risultato),
                ]
        (RADICE / "docs" / "tools.md").write_text("\n".join(righe + dettagli) + "\n", encoding="utf-8")
        print("Scritto docs/tools.md")


if __name__ == "__main__":
    asyncio.run(main())
