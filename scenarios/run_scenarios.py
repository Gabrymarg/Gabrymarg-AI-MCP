"""Esegue gli scenari di test sull'agente reale e produce un report.

Uso:
  python scenarios/run_scenarios.py [--modello qwen2.5:3b] [--provider ollama] [--solo S01,S05]

Per ogni scenario: database nuovo, orologio fissato, conferme predefinite, eventuali guasti
simulati. Al termine verifica tool invocati, stato del database e testo della risposta.
Output in scenarios/risultati/<modello>/: report.md, risultati.json e i log JSONL.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

from backend.db import connetti  # noqa: E402
from backend.seed import crea_database  # noqa: E402
from harness.agent import Agent  # noqa: E402
from harness.config import Config  # noqa: E402
from harness.confirm import conferma_scriptata  # noqa: E402
from harness.llm import crea_provider  # noqa: E402
from harness.logger import LoggerJSONL  # noqa: E402
from harness.mcp_client import ClienteMCP  # noqa: E402


@dataclass
class Risultato:
    id: str
    titolo: str
    tipo: str
    turni: list[str]
    atteso: str
    risposte: list[str] = field(default_factory=list)
    motivi_arresto: list[str] = field(default_factory=list)
    tool_invocati: list[str] = field(default_factory=list)
    scritture_eseguite: list[str] = field(default_factory=list)
    conferme_richieste: int = 0
    iterazioni: int = 0
    chiamate_modello: int = 0
    token_input: int = 0
    token_output: int = 0
    durata_s: float = 0.0
    controlli_falliti: list[str] = field(default_factory=list)
    log: str = ""
    estratto_log: list[str] = field(default_factory=list)

    @property
    def superato(self) -> bool:
        return not self.controlli_falliti


def estratto(eventi: list[dict[str, Any]]) -> list[str]:
    """Righe sintetiche del log, per il report."""
    righe = []
    for e in eventi:
        t, it = e["tipo"], e.get("iterazione")
        if t == "richiesta_utente":
            righe.append(f"[turno {e['turno']}] utente: {e['testo']}")
        elif t == "risposta_modello":
            chiamate = ", ".join(f"{c['nome']}({json.dumps(c['argomenti'], ensure_ascii=False)})" for c in e["tool_calls"])
            cosa = f"tool_calls: {chiamate}" if chiamate else f"testo: {e['testo'][:160]!r}"
            righe.append(f"  it.{it} modello ({e['token_input']}+{e['token_output']} token, {e['durata_ms']} ms) -> {cosa}")
        elif t == "conferma_utente":
            righe.append(f"  it.{it} conferma {e['tool']}: {'APPROVATA' if e['approvato'] else 'NEGATA'}")
        elif t == "risultato_tool":
            if e.get("ok"):
                righe.append(f"  it.{it} {e['tool']} -> ok " + json.dumps(e.get("risultato"), ensure_ascii=False)[:160])
            elif e.get("annullato_da_utente"):
                righe.append(f"  it.{it} {e['tool']} -> annullato dall'utente")
            else:
                err = e.get("errore") or {}
                righe.append(f"  it.{it} {e['tool']} -> ERRORE {err.get('codice')}: {str(err.get('messaggio'))[:120]}")
        elif t == "fine_turno":
            righe.append(f"  fine turno: {e['motivo_arresto']} ({e['token_totali']} token, {e['durata_ms']} ms)")
    return righe


async def esegui_scenario(s: dict, adesso: str, modello_db: Path, cartella: Path, cfg: Config) -> Risultato:
    db = cartella / "db" / f"{s['id']}.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(modello_db, db)
    env = {"RISTO_DB": str(db), "RISTO_ADESSO": adesso, "RISTO_GUASTI": ",".join(s.get("guasti", []))}
    conferme = [str(c).lower() in {"s", "si", "sì", "true"} for c in s.get("conferme", [])]

    r = Risultato(s["id"], s["titolo"], s["tipo"], s["turni"], s["atteso"].strip())
    log = LoggerJSONL(cartella / "log", prefisso=s["id"])
    r.log = str(log.percorso.relative_to(cartella))
    llm = crea_provider(cfg.provider, cfg.modello)
    inizio = time.perf_counter()
    try:
        async with ClienteMCP(cfg.comando_server, cfg.cartella_server, env=env) as cliente:
            agente = Agent(llm, cliente, conferma_scriptata(conferme), log, cfg)
            await agente.avvia()
            for testo in s["turni"]:
                esito = await agente.esegui_turno(testo)
                r.risposte.append(esito.risposta)
                r.motivi_arresto.append(esito.motivo_arresto)
                r.tool_invocati += esito.tool_invocati
                r.iterazioni += esito.iterazioni
                r.chiamate_modello += esito.chiamate_modello
                r.token_input += esito.uso.token_input
                r.token_output += esito.uso.token_output
    finally:
        log.chiudi()
    r.durata_s = round(time.perf_counter() - inizio, 1)
    r.scritture_eseguite = [
        e["tool"] for e in log.eventi
        if e["tipo"] == "risultato_tool" and e.get("ok") and e["tool"] in {n for n, sp in agente.strumenti.items() if sp.scrittura}
    ]
    r.conferme_richieste = sum(1 for e in log.eventi if e["tipo"] == "conferma_utente")
    r.estratto_log = estratto(log.eventi)
    verifica(s.get("verifiche", {}), r, db)
    return r


def verifica(v: dict, r: Risultato, db: Path) -> None:
    for tool in v.get("tool_attesi", []):
        if tool not in r.tool_invocati:
            r.controlli_falliti.append(f"tool atteso non invocato: {tool}")
    uno_tra = v.get("tool_almeno_uno_tra", [])
    if uno_tra and not set(uno_tra) & set(r.tool_invocati):
        r.controlli_falliti.append(f"nessuno di questi tool è stato invocato: {uno_tra}")
    for tool in v.get("scritture_vietate", []):
        if tool in r.scritture_eseguite:
            r.controlli_falliti.append(f"scrittura vietata eseguita: {tool}")
    conn = connetti(db)
    try:
        for c in v.get("db", []):
            valore = conn.execute(c["sql"]).fetchone()[0]
            if valore != c["atteso"]:
                r.controlli_falliti.append(f"database: atteso {c['atteso']}, trovato {valore} ({c['sql']})")
    finally:
        conn.close()
    parole = v.get("risposta_contiene", [])
    finale = (r.risposte[-1] if r.risposte else "").lower()
    if parole and not any(p.lower() in finale for p in parole):
        r.controlli_falliti.append(f"la risposta finale non contiene nessuna di: {parole}")
    for vietata in v.get("risposta_non_contiene", []):
        if vietata.lower() in finale:
            r.controlli_falliti.append(f"la risposta finale contiene un'affermazione errata: '{vietata}'")


def scrivi_report(risultati: list[Risultato], cfg: Config, cartella: Path) -> Path:
    superati = sum(r.superato for r in risultati)
    tot_in = sum(r.token_input for r in risultati)
    tot_out = sum(r.token_output for r in risultati)
    righe = [
        f"# Report scenari - modello `{cfg.provider}:{cfg.modello}`",
        "",
        f"Scenari superati: **{superati}/{len(risultati)}**. Token totali: {tot_in} input + {tot_out} output = "
        f"{tot_in + tot_out} (media {(tot_in + tot_out) // max(1, len(risultati))} per scenario). "
        f"Tempo totale: {sum(r.durata_s for r in risultati):.0f} s.",
        "",
        "| ID | Scenario | Tipo | Esito | Tool invocati | Iter. | Token in | Token out | Tempo (s) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in risultati:
        righe.append(
            f"| {r.id} | {r.titolo} | {r.tipo} | {'SUPERATO' if r.superato else 'NON SUPERATO'} | "
            f"{', '.join(r.tool_invocati) or '-'} | {r.iterazioni} | {r.token_input} | {r.token_output} | {r.durata_s} |"
        )
    for r in risultati:
        righe += [
            "",
            f"## {r.id} - {r.titolo} ({'SUPERATO' if r.superato else 'NON SUPERATO'})",
            "",
            "**Richiesta:** " + " / ".join(f"\"{t}\"" for t in r.turni),
            "",
            f"**Esito atteso:** {r.atteso}",
            "",
            "**Esito ottenuto:** " + " / ".join(f"\"{x}\"" for x in r.risposte),
            "",
            f"Arresto: {', '.join(r.motivi_arresto)}; conferme richieste: {r.conferme_richieste}; "
            f"scritture eseguite: {', '.join(r.scritture_eseguite) or 'nessuna'}.",
        ]
        if r.controlli_falliti:
            righe += ["", "**Controlli falliti:**"] + [f"- {c}" for c in r.controlli_falliti]
        righe += ["", f"Estratto del log (`{r.log}`):", "", "```"] + r.estratto_log + ["```"]
    percorso = cartella / "report.md"
    percorso.write_text("\n".join(righe) + "\n", encoding="utf-8")
    return percorso


async def main_async(args: argparse.Namespace) -> None:
    dati = yaml.safe_load((Path(__file__).parent / "scenari.yaml").read_text(encoding="utf-8"))
    cfg = Config()
    cfg.provider = args.provider or cfg.provider
    cfg.modello = args.modello or cfg.modello
    nome_cartella = re.sub(r"[^\w.-]", "_", f"{cfg.provider}_{cfg.modello}")
    cartella = Path(args.uscita or Path(__file__).parent / "risultati" / nome_cartella)
    if cartella.exists():
        shutil.rmtree(cartella)
    cartella.mkdir(parents=True)

    os.environ["RISTO_ADESSO"] = dati["adesso"]
    modello_db = cartella / "db" / "_modello.db"
    info = crea_database(modello_db)
    print(f"Database di partenza: {info}")

    scelti = set(args.solo.split(",")) if args.solo else None
    risultati = []
    for s in dati["scenari"]:
        if scelti and s["id"] not in scelti:
            continue
        print(f"{s['id']} {s['titolo']}...", end=" ", flush=True)
        r = await esegui_scenario(s, dati["adesso"], modello_db, cartella, cfg)
        risultati.append(r)
        print(f"{'OK' if r.superato else 'KO'} ({r.durata_s} s, {r.token_input + r.token_output} token)")
        for c in r.controlli_falliti:
            print(f"    - {c}")

    (cartella / "risultati.json").write_text(
        json.dumps([{**r.__dict__, "superato": r.superato} for r in risultati], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = scrivi_report(risultati, cfg, cartella)
    print(f"\nSuperati {sum(r.superato for r in risultati)}/{len(risultati)}. Report: {report}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Esegue gli scenari di test dell'agente")
    p.add_argument("--provider", choices=["ollama", "openai", "groq"])
    p.add_argument("--modello")
    p.add_argument("--solo", help="elenco di id separati da virgola, es. S01,S05")
    p.add_argument("--uscita", help="cartella di output")
    asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    main()
