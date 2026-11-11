"""Interfaccia a riga di comando dell'assistente.

Uso:  python -m harness.cli [--provider ollama|openai] [--modello qwen2.5:3b] [--verboso]

Comandi in chat:  /nuova (nuova conversazione)   /token (consumo della sessione)   /esci
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from harness.agent import Agent
from harness.config import Config
from harness.confirm import conferma_interattiva
from harness.llm import crea_provider
from harness.logger import LoggerJSONL
from harness.mcp_client import ClienteMCP, ServerNonDisponibile


class EsecutoreVerboso:
    """Avvolge il client MCP per mostrare a video i tool invocati (utile per gli screenshot)."""

    def __init__(self, cliente: ClienteMCP, verboso: bool):
        self.cliente, self.verboso = cliente, verboso

    async def elenco_strumenti(self):
        return await self.cliente.elenco_strumenti()

    async def chiama(self, nome, argomenti, timeout_s):
        args = ", ".join(f"{k}={v!r}" for k, v in argomenti.items())
        print(f"   [tool] {nome}({args})")
        esito = await self.cliente.chiama(nome, argomenti, timeout_s)
        if not esito.ok:
            print(f"   [tool] -> errore {esito.errore.get('codice')}: {esito.errore.get('messaggio')}")
        elif self.verboso:
            print("   [tool] -> " + json.dumps(esito.contenuto, ensure_ascii=False)[:400])
        return esito


async def main_async(args: argparse.Namespace) -> int:
    cfg = Config()
    if args.provider:
        cfg.provider = args.provider
    if args.modello:
        cfg.modello = args.modello
    llm = crea_provider(cfg.provider, cfg.modello)
    log = LoggerJSONL(cfg.cartella_log)

    try:
        async with ClienteMCP(cfg.comando_server, cfg.cartella_server) as cliente:
            agente = Agent(llm, EsecutoreVerboso(cliente, args.verboso), conferma_interattiva, log, cfg)
            await agente.avvia()
            print(f"Osteria del Borgo - assistente virtuale ({llm.descrizione()}, {len(agente.strumenti)} tool)")
            print(f"Log: {log.percorso}")
            print("Scrivi la tua richiesta. Comandi: /nuova  /token  /esci\n")
            while True:
                try:
                    testo = input("Tu> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if not testo:
                    continue
                if testo == "/esci":
                    break
                if testo == "/nuova":
                    agente.nuova_conversazione()
                    print("(nuova conversazione)\n")
                    continue
                if testo == "/token":
                    u = agente.uso_sessione
                    print(f"(token sessione: input {u.token_input}, output {u.token_output}, totale {u.totale})\n")
                    continue
                try:
                    esito = await agente.esegui_turno(testo)
                except KeyboardInterrupt:
                    log.registra("interruzione_utente", agente.turno)
                    print("\n(interrotto)\n")
                    continue
                print(f"\nAssistente> {esito.risposta}")
                print(
                    f"   ({esito.motivo_arresto}, {esito.iterazioni} iter., {esito.uso.totale} token, "
                    f"{esito.durata_ms / 1000:.1f} s)\n"
                )
    except ServerNonDisponibile as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        return 1
    finally:
        log.chiudi()
    return 0


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Assistente virtuale di Osteria del Borgo")
    parser.add_argument("--provider", choices=["ollama", "openai"])
    parser.add_argument("--modello")
    parser.add_argument("--verboso", action="store_true", help="mostra anche i risultati dei tool")
    sys.exit(asyncio.run(main_async(parser.parse_args())))


if __name__ == "__main__":
    main()
