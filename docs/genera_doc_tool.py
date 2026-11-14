"""Genera docs/tools.md interrogando il server MCP: la documentazione resta allineata al codice.

Uso: python docs/genera_doc_tool.py
Avvia il server via HTTP su un database di prova e lo interroga come amministratore (unico ruolo
che può usare tutti i tool). Per ogni tool riporta: ruoli autorizzati, descrizione, effetti sui dati
(dalle annotazioni), schema d'ingresso e d'uscita, un esempio eseguito davvero e il risultato.
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

from mcp import Client  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402
from mcp.shared._httpx_utils import create_mcp_http_client  # noqa: E402

from backend import permessi  # noqa: E402
from backend.seed import crea_database  # noqa: E402
from scenarios.run_scenarios import server_http, token_utente  # noqa: E402

ADESSO = "2026-12-03T11:00"

ESEMPI = {
    "mio_profilo": {},
    "orari_apertura": {},
    "cerca_menu": {"categoria": "Secondi", "escludi_allergeni": ["glutine", "latte"]},
    "dettaglio_piatto": {"nome": "tagliolini al tartufo"},
    "verifica_disponibilita": {"data": "sabato", "ora": "20:30", "coperti": 4},
    "orari_disponibili": {"data": "sabato", "coperti": 4},
    "trova_prenotazioni": {"telefono": "333 1234567"},
    "prenotazioni_del_giorno": {"data": "domani"},
    "crea_prenotazione": {"data": "domani", "ora": "20:30", "coperti": 2, "nome_cliente": "Marco Gallo",
                          "telefono": "340 555 1234", "note": "Tavolo tranquillo"},
    "modifica_prenotazione": {"id_prenotazione": 86, "ora": "21:00", "coperti": 4},
    "cancella_prenotazione": {"id_prenotazione": 86},
    "crea_ordine_asporto": {"nome_cliente": "Paolo Riva", "telefono": "320 987 6543", "ora_ritiro": "20:30",
                            "righe": [{"nome": "carbonara", "quantita": 2}, {"nome": "tiramisù", "quantita": 1}]},
    "stato_ordine": {"id_ordine": 1},
    "ordini_da_preparare": {},
    "aggiorna_stato_ordine": {"id_ordine": 1, "nuovo_stato": "pronto"},
    "giacenze_ingredienti": {"solo_sotto_scorta": True},
    "aggiorna_scorta": {"ingrediente": "tartufo nero", "quantita": 200, "modalita": "aggiungi"},
    "imposta_disponibilita_piatto": {"nome": "branzino al forno", "disponibile": False},
}

RUOLI_LEGGIBILI = {"ospite": "ospite", "cliente": "cliente", "sala": "sala", "cucina": "cucina", "admin": "admin"}


def effetti(a) -> str:
    if a.read_only_hint:
        return "Sola lettura (`readOnlyHint: true`): nessun effetto sui dati, non richiede conferma."
    testo = "**Scrittura** (`readOnlyHint: false`): modifica la base dati; l'harness chiede conferma all'utente."
    if a.destructive_hint:
        testo += " **Distruttivo** (`destructiveHint: true`): l'operazione non è annullabile."
    return testo


def ruoli(nome: str) -> str:
    return ", ".join(r for r in RUOLI_LEGGIBILI if permessi.puo(r, nome))


def blocco_json(dati) -> list[str]:
    return ["```json", json.dumps(dati, ensure_ascii=False, indent=2), "```"]


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "doc.db"
        os.environ["RISTO_ADESSO"] = ADESSO
        crea_database(db)
        env = {"RISTO_DB": str(db), "RISTO_ADESSO": ADESSO}
        with server_http(env) as url:
            intestazioni = {"Authorization": f"Bearer {token_utente(db, 'admin')}"}
            trasporto = streamable_http_client(url, http_client=create_mcp_http_client(headers=intestazioni))
            righe = [
                "# Documentazione dei tool MCP",
                "",
                "Generata automaticamente da `docs/genera_doc_tool.py` interrogando il server (`tools/list`).",
                f"Gli esempi sono stati eseguiti realmente via HTTP, come amministratore, su un database di prova "
                f"(seed 42, orologio fissato a {ADESSO}). I ruoli autorizzati provengono da `backend/permessi.py` "
                "e sono verificati dal server a ogni chiamata.",
                "",
                "| Tool | Effetti | Ruoli autorizzati | Parametri obbligatori |",
                "|---|---|---|---|",
            ]
            dettagli: list[str] = []
            async with Client(trasporto, cache=None) as c:
                for t in (await c.list_tools()).tools:
                    a = t.annotations
                    tipo = "lettura" if a.read_only_hint else ("scrittura distruttiva" if a.destructive_hint else "scrittura")
                    obbligatori = ", ".join(t.input_schema.get("required", [])) or "-"
                    righe.append(f"| `{t.name}` | {tipo} | {ruoli(t.name)} | {obbligatori} |")
                    esempio = ESEMPI[t.name]
                    r = await c.call_tool(t.name, esempio)
                    risultato = r.structured_content if not r.is_error else r.content[0].text
                    dettagli += [
                        "", f"## `{t.name}`", "", inspect.cleandoc(t.description or ""), "",
                        f"**Effetti sui dati:** {effetti(a)}", "",
                        f"**Ruoli autorizzati:** {ruoli(t.name)}.", "",
                        "**Schema dei parametri di ingresso:**", "", *blocco_json(t.input_schema), "",
                        "**Schema di uscita:**", "", *blocco_json(t.output_schema), "",
                        "**Esempio di invocazione:**", "",
                        *blocco_json({"name": t.name, "arguments": esempio}), "",
                        "**Risultato:**", "", *blocco_json(risultato),
                    ]
        (RADICE / "docs" / "tools.md").write_text("\n".join(righe + dettagli) + "\n", encoding="utf-8")
        print(f"Scritto docs/tools.md ({len(ESEMPI)} tool)")


if __name__ == "__main__":
    asyncio.run(main())
