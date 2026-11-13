"""Semplificazione dei JSON Schema prima di inviarli al modello.

Lo schema generato da Pydantic è corretto ma verboso (title ovunque, anyOf con null per
ogni parametro facoltativo, $ref verso $defs). Ogni token dello schema viene rielaborato
dal modello a ogni chiamata: compattarlo riduce i costi e aiuta i modelli piccoli.
La validazione degli argomenti usa comunque lo schema ORIGINALE del server.
"""

from __future__ import annotations

import ast
import copy
import json
import re
from typing import Any


def _risolvi_ref(nodo: Any, defs: dict[str, Any]) -> Any:
    if isinstance(nodo, dict):
        if "$ref" in nodo:
            nome = nodo["$ref"].rsplit("/", 1)[-1]
            risolto = _risolvi_ref(copy.deepcopy(defs[nome]), defs)
            extra = {k: v for k, v in nodo.items() if k != "$ref"}
            return {**risolto, **extra}
        return {k: _risolvi_ref(v, defs) for k, v in nodo.items()}
    if isinstance(nodo, list):
        return [_risolvi_ref(v, defs) for v in nodo]
    return nodo


def _semplifica(nodo: Any) -> Any:
    if isinstance(nodo, list):
        return [_semplifica(v) for v in nodo]
    if not isinstance(nodo, dict):
        return nodo
    nodo = {k: v for k, v in nodo.items() if k not in {"title", "$defs"}}
    if nodo.get("default", ...) is None:
        del nodo["default"]
    varianti = nodo.get("anyOf")
    if isinstance(varianti, list):
        non_null = [v for v in varianti if v != {"type": "null"}]
        if len(non_null) == 1:
            del nodo["anyOf"]
            nodo = {**non_null[0], **nodo}
            # Il valore null resta ammesso ("type": [T, "null"]): alcuni fornitori (es. Groq) validano
            # le chiamate generate dal modello rispetto allo schema e rifiutano un null non dichiarato.
            if len(non_null) < len(varianti) and isinstance(nodo.get("type"), str):
                nodo["type"] = [nodo["type"], "null"]
    if "properties" in nodo:
        nodo["properties"] = {k: _semplifica(v) for k, v in nodo["properties"].items()}
    return {k: (_semplifica(v) if k != "properties" else v) for k, v in nodo.items()}


def compatta_schema(schema: dict[str, Any]) -> dict[str, Any]:
    return _semplifica(_risolvi_ref(schema, schema.get("$defs", {})))


# --------------------------------------------------------------------------- conversione dei tipi

def _tipi(schema: dict[str, Any]) -> set[str]:
    if "anyOf" in schema:
        return {t for s in schema["anyOf"] for t in _tipi(s)}
    tipo = schema.get("type")
    return set(tipo) if isinstance(tipo, list) else {tipo} if tipo else set()


def _sotto_schema(schema: dict[str, Any], tipo: str) -> dict[str, Any]:
    for s in schema.get("anyOf", [schema]):
        if tipo in _tipi(s):
            return s
    return schema


def _converti_valore(valore: Any, schema: dict[str, Any]) -> Any:
    tipi = _tipi(schema)
    if isinstance(valore, str):
        testo = valore.strip()
        if "integer" in tipi and re.fullmatch(r"[+-]?\d+", testo):
            return int(testo)
        if "number" in tipi and re.fullmatch(r"[+-]?\d+([.,]\d+)?", testo):
            return float(testo.replace(",", "."))
        if "boolean" in tipi and testo.lower() in {"true", "false", "sì", "si", "no"}:
            return testo.lower() in {"true", "sì", "si"}
        if "array" in tipi and "string" not in tipi:
            for lettore in (json.loads, ast.literal_eval):
                try:
                    letto = lettore(testo)
                    if isinstance(letto, list):
                        return _converti_valore(letto, schema)
                except (ValueError, SyntaxError, json.JSONDecodeError):
                    pass
            return [testo] if testo else []
        return valore
    if isinstance(valore, list) and "array" in tipi:
        elementi = _sotto_schema(schema, "array").get("items", {})
        return [_converti_valore(v, elementi) for v in valore]
    if isinstance(valore, dict) and "object" in tipi:
        return converti_argomenti(valore, _sotto_schema(schema, "object"))
    return valore


def converti_argomenti(argomenti: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Adatta gli argomenti ai tipi dichiarati dallo schema, prima della validazione.

    I modelli piccoli passano spesso numeri come testo ("2") o liste come stringhe
    ("['glutine']"). La conversione è conservativa: se un valore non è convertibile resta
    invariato e sarà la validazione a rifiutarlo. Le stringhe vuote nei campi facoltativi
    vengono eliminate (equivalgono a "non indicato").
    """
    schema = _risolvi_ref(schema, schema.get("$defs", {}))
    proprieta = schema.get("properties", {})
    obbligatori = set(schema.get("required", []))
    risultato = {}
    for chiave, valore in argomenti.items():
        if chiave in proprieta and valore == "" and chiave not in obbligatori:
            continue
        risultato[chiave] = _converti_valore(valore, proprieta[chiave]) if chiave in proprieta else valore
    return risultato
