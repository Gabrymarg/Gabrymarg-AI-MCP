"""Semplificazione dei JSON Schema prima di inviarli al modello.

Lo schema generato da Pydantic è corretto ma verboso (title ovunque, anyOf con null per
ogni parametro facoltativo, $ref verso $defs). Ogni token dello schema viene rielaborato
dal modello a ogni chiamata: compattarlo riduce i costi e aiuta i modelli piccoli.
La validazione degli argomenti usa comunque lo schema ORIGINALE del server.
"""

from __future__ import annotations

import copy
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
    if "properties" in nodo:
        nodo["properties"] = {k: _semplifica(v) for k, v in nodo["properties"].items()}
    return {k: (_semplifica(v) if k != "properties" else v) for k, v in nodo.items()}


def compatta_schema(schema: dict[str, Any]) -> dict[str, Any]:
    return _semplifica(_risolvi_ref(schema, schema.get("$defs", {})))
