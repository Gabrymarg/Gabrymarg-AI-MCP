from jsonschema import Draft202012Validator

from harness.schema_utils import compatta_schema
from mcp_server import server


def _schema(nome):
    return next(t for t in server.mcp._tool_manager.list_tools() if t.name == nome).parameters


def test_compatta_rimuove_null_title_e_ref():
    originale = _schema("crea_ordine_asporto")
    compatto = compatta_schema(originale)
    testo = str(compatto)
    assert "title" not in testo and "$ref" not in testo and "'null'" not in testo
    assert compatto["properties"]["righe"]["items"]["properties"]["id_articolo"]["type"] == "integer"
    assert compatto["properties"]["note"]["type"] == "string"
    assert compatto["required"] == originale["required"]


def test_argomenti_validi_restano_validi():
    originale = _schema("crea_ordine_asporto")
    argomenti = {"nome_cliente": "A", "telefono": "333", "ora_ritiro": "20:00",
                 "righe": [{"id_articolo": 1, "quantita": 2}]}
    assert not list(Draft202012Validator(originale).iter_errors(argomenti))
    assert not list(Draft202012Validator(compatta_schema(originale)).iter_errors(argomenti))
