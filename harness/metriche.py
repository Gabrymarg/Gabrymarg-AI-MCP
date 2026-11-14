"""Metriche di esercizio calcolate dai log JSONL dell'harness.

Trasforma i log in indicatori per l'amministratore: volumi, token e costo stimato, tempi di risposta,
esiti dei turni, strumenti più usati, interventi delle barriere di sicurezza e scelte del router.
Il calcolo è fatto a ogni richiesta leggendo i file: per i volumi di un singolo ristorante
(decine di conversazioni al giorno) non serve un database dedicato.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# Listino del piano a consumo di Groq (dollari per milione di token, input / output), novembre 2026.
# Da aggiornare se cambia: https://console.groq.com/docs/models
LISTINO = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
}

ETICHETTE_ARRESTO = {
    "risposta_finale": "Risposta completata",
    "max_iterazioni": "Limite di iterazioni",
    "loop_rilevato": "Ciclo ripetitivo interrotto",
    "troppi_errori": "Troppi errori dei tool",
    "errore_modello": "Modello non disponibile",
    "contesto_troppo_lungo": "Conversazione troppo lunga",
    "limite_fornitore": "Limite del piano gratuito",
    "riferimento_non_verificato": "Numero non verificato bloccato",
}


def _modello_pulito(nome: str | None) -> str:
    """'groq:openai/gpt-oss-120b' -> 'openai/gpt-oss-120b'; 'ollama:qwen2.5:3b' -> 'qwen2.5:3b'."""
    if not nome:
        return "sconosciuto"
    for prefisso in ("groq:", "ollama:", "openai:"):
        if nome.startswith(prefisso):
            return nome[len(prefisso):]
    return nome


def _percentile(valori: list[float], p: float) -> float:
    if not valori:
        return 0
    ordinati = sorted(valori)
    return ordinati[min(len(ordinati) - 1, int(round(p * (len(ordinati) - 1))))]


def analizza(cartella: Path) -> dict[str, Any]:
    sessioni = turni = 0
    per_modello: dict[str, Counter] = defaultdict(Counter)
    durate_turno: list[float] = []
    arresti: Counter = Counter()
    strumenti: Counter = Counter()
    sicurezza: Counter = Counter()
    router: Counter = Counter()
    turni_per_ruolo: Counter = Counter()
    giorni: Counter = Counter()
    primo = ultimo = None

    for f in sorted(cartella.glob("*.jsonl")):
        modello_sessione, ruolo, scritture, approvate = None, None, set(), Counter()
        try:
            righe = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for riga in righe:
            try:
                e = json.loads(riga)
            except json.JSONDecodeError:
                continue
            tipo, ts = e.get("tipo"), e.get("ts")
            if ts:
                primo = min(primo or ts, ts)
                ultimo = max(ultimo or ts, ts)
            if tipo == "avvio":
                sessioni += 1
                modello_sessione = e.get("modello")
                ruolo = e.get("ruolo") or "ospite"
                scritture = {s["nome"] for s in e.get("strumenti", []) if s.get("scrittura")}
            elif tipo == "risposta_modello":
                modello = _modello_pulito(e.get("modello") or modello_sessione)
                m = per_modello[modello]
                m["chiamate"] += 1
                m["token_input"] += e.get("token_input") or 0
                m["token_output"] += e.get("token_output") or 0
                m["durata_ms"] += e.get("durata_ms") or 0
                if instradamento := e.get("instradamento"):
                    destinazione, _, motivo = instradamento.partition(": ")
                    if "ripiego" in motivo:
                        motivo = "ripiego: l'altro modello non rispondeva"
                    router[(destinazione, motivo)] += 1
            elif tipo == "fine_turno":
                turni += 1
                durate_turno.append((e.get("durata_ms") or 0) / 1000)
                arresti[e.get("motivo_arresto", "sconosciuto")] += 1
                turni_per_ruolo[ruolo or "ospite"] += 1
                if ts:
                    giorni[ts[:10]] += 1
            elif tipo == "chiamata_tool":
                strumenti[e.get("tool", "?")] += 1
            elif tipo == "conferma_utente":
                sicurezza["conferme_richieste"] += 1
                if e.get("approvato"):
                    approvate[e.get("tool")] += 1
                else:
                    sicurezza["conferme_negate"] += 1
            elif tipo == "risultato_tool":
                codice = (e.get("errore") or {}).get("codice")
                if codice == "PERMESSO_NEGATO":
                    sicurezza["permessi_negati"] += 1
                elif codice in ("PARAMETRI_NON_VALIDI", "TOOL_INESISTENTE"):
                    sicurezza["chiamate_bloccate"] += 1
                elif codice:
                    sicurezza["errori_gestiti"] += 1
                if e.get("ok") and e.get("tool") in scritture:
                    sicurezza["scritture_eseguite"] += 1
                    if approvate[e["tool"]] > 0:
                        approvate[e["tool"]] -= 1
                    else:
                        sicurezza["scritture_senza_conferma"] += 1
            elif tipo == "guardrail_coerenza":
                sicurezza["risposte_respinte_coerenza"] += 1
            elif tipo == "guardrail_riferimenti":
                sicurezza["numeri_inventati_bloccati"] += 1
            elif tipo in ("tool_call_testuale_recuperata", "tool_call_testuale_malformata", "argomenti_convertiti"):
                sicurezza["correzioni_formato"] += 1

    modelli = []
    for nome, m in sorted(per_modello.items(), key=lambda x: -x[1]["chiamate"]):
        prezzo = LISTINO.get(nome)
        costo = (m["token_input"] * prezzo[0] + m["token_output"] * prezzo[1]) / 1e6 if prezzo else 0.0
        modelli.append({
            "modello": nome,
            "locale": prezzo is None and nome not in ("sconosciuto", "router"),
            "chiamate": m["chiamate"],
            "token_input": m["token_input"],
            "token_output": m["token_output"],
            "secondi_medi": round(m["durata_ms"] / m["chiamate"] / 1000, 1) if m["chiamate"] else 0,
            "costo_usd": round(costo, 4),
        })
    token = sum(m["token_input"] + m["token_output"] for m in modelli)
    costo = sum(m["costo_usd"] for m in modelli)
    for chiave in ("conferme_richieste", "conferme_negate", "permessi_negati", "chiamate_bloccate", "errori_gestiti",
                   "scritture_eseguite", "scritture_senza_conferma", "risposte_respinte_coerenza",
                   "numeri_inventati_bloccati", "correzioni_formato"):
        sicurezza.setdefault(chiave, 0)
    return {
        "periodo": {"dal": primo, "al": ultimo},
        "sessioni": sessioni,
        "turni": turni,
        "token_totali": token,
        "token_per_turno": round(token / turni) if turni else 0,
        "costo_usd": round(costo, 4),
        "costo_per_turno_usd": round(costo / turni, 5) if turni else 0,
        "tempo_turno_s": {
            "mediana": round(statistics.median(durate_turno), 1) if durate_turno else 0,
            "p90": round(_percentile(durate_turno, 0.9), 1),
        },
        "completati_pct": round(100 * arresti["risposta_finale"] / turni) if turni else 0,
        "arresti": [{"motivo": k, "etichetta": ETICHETTE_ARRESTO.get(k, k), "turni": v} for k, v in arresti.most_common()],
        "modelli": modelli,
        "strumenti": [{"nome": k, "chiamate": v} for k, v in strumenti.most_common()],
        "sicurezza": dict(sicurezza),
        "router": [{"destinazione": d, "motivo": m, "chiamate": v} for (d, m), v in router.most_common()],
        "turni_per_ruolo": dict(turni_per_ruolo),
        "turni_per_giorno": dict(sorted(giorni.items())),
    }
