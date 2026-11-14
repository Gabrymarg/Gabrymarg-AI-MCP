"""Metriche del cruscotto calcolate dai log JSONL."""

import json

from harness.metriche import analizza


def _scrivi(cartella, nome, eventi):
    (cartella / nome).write_text("\n".join(json.dumps(e) for e in eventi), encoding="utf-8")


def test_metriche_da_log(tmp_path):
    avvio = {"tipo": "avvio", "ts": "2026-12-03T11:00:00", "modello": "groq:openai/gpt-oss-120b", "ruolo": "cliente",
             "strumenti": [{"nome": "crea_prenotazione", "scrittura": True}, {"nome": "cerca_menu", "scrittura": False}]}
    _scrivi(tmp_path, "a.jsonl", [
        avvio,
        {"tipo": "risposta_modello", "token_input": 1_000_000, "token_output": 100_000, "durata_ms": 2000},
        {"tipo": "chiamata_tool", "tool": "crea_prenotazione"},
        {"tipo": "conferma_utente", "tool": "crea_prenotazione", "approvato": True},
        {"tipo": "risultato_tool", "tool": "crea_prenotazione", "ok": True},
        {"tipo": "fine_turno", "ts": "2026-12-03T11:00:05", "motivo_arresto": "risposta_finale", "durata_ms": 5000},
        {"tipo": "risultato_tool", "tool": "aggiorna_scorta", "ok": False, "errore": {"codice": "PERMESSO_NEGATO"}},
        {"tipo": "guardrail_riferimenti", "riferimenti": ["ordine n. 9"]},
        {"tipo": "fine_turno", "ts": "2026-12-03T11:01:00", "motivo_arresto": "riferimento_non_verificato", "durata_ms": 9000},
    ])
    _scrivi(tmp_path, "b.jsonl", [
        {**avvio, "modello": "router(ollama:qwen2.5:3b, groq:openai/gpt-oss-120b)"},
        {"tipo": "risposta_modello", "modello": "qwen2.5:3b", "instradamento": "locale: richiesta di sola consultazione",
         "token_input": 5000, "token_output": 20, "durata_ms": 30000},
        # scrittura riuscita senza conferma: deve risultare nell'indicatore (non dovrebbe mai accadere)
        {"tipo": "risultato_tool", "tool": "crea_prenotazione", "ok": True},
        {"tipo": "fine_turno", "ts": "2026-12-04T20:00:00", "motivo_arresto": "risposta_finale", "durata_ms": 31000},
    ])
    m = analizza(tmp_path)
    assert m["sessioni"] == 2 and m["turni"] == 3 and m["completati_pct"] == 67
    assert m["costo_usd"] == round(0.15 + 0.06, 4)  # 1M input a 0,15 $ + 100k output a 0,60 $/M
    modelli = {x["modello"]: x for x in m["modelli"]}
    assert modelli["qwen2.5:3b"]["locale"] and modelli["qwen2.5:3b"]["costo_usd"] == 0
    s = m["sicurezza"]
    assert s["scritture_eseguite"] == 2 and s["scritture_senza_conferma"] == 1
    assert s["permessi_negati"] == 1 and s["numeri_inventati_bloccati"] == 1
    assert m["router"] == [{"destinazione": "locale", "motivo": "richiesta di sola consultazione", "chiamate": 1}]
    assert m["turni_per_giorno"] == {"2026-12-03": 2, "2026-12-04": 1}


def test_cartella_vuota(tmp_path):
    m = analizza(tmp_path)
    assert m["turni"] == 0 and m["costo_usd"] == 0 and m["sicurezza"]["scritture_senza_conferma"] == 0
