from jsonschema import Draft202012Validator

from harness.schema_utils import compatta_schema
from mcp_server import server


def _schema(nome):
    return next(t for t in server.mcp._tool_manager.list_tools() if t.name == nome).parameters


def test_compatta_rimuove_null_title_e_ref():
    originale = _schema("crea_ordine_asporto")
    compatto = compatta_schema(originale)
    testo = str(compatto)
    assert "title" not in testo and "$ref" not in testo and "anyOf" not in testo
    assert compatto["properties"]["righe"]["items"]["properties"]["id_articolo"]["type"] == ["integer", "null"]
    # I campi facoltativi ammettono ancora null: i fornitori che validano lo schema non devono rifiutarli.
    assert compatto["properties"]["note"]["type"] == ["string", "null"]
    assert compatto["required"] == originale["required"]


def test_null_ammesso_nei_facoltativi_dello_schema_compatto():
    """Regressione: Groq rifiutava (HTTP 400) le chiamate con null nei parametri facoltativi."""
    compatto = compatta_schema(_schema("cerca_menu"))
    argomenti_con_null = {"testo": None, "categoria": None, "escludi_allergeni": None}
    assert not list(Draft202012Validator(compatto).iter_errors(argomenti_con_null))


def test_conversione_tipi_secondo_schema():
    from harness.schema_utils import converti_argomenti

    schema = _schema("verifica_disponibilita")
    assert converti_argomenti({"data": "domani", "ora": "20:00", "coperti": "2"}, schema)["coperti"] == 2
    menu_schema = _schema("cerca_menu")
    convertiti = converti_argomenti({"escludi_allergeni": "['glutine']", "solo_vegetariani": "true"}, menu_schema)
    assert convertiti == {"escludi_allergeni": ["glutine"], "solo_vegetariani": True}
    assert converti_argomenti({"escludi_allergeni": "latte"}, menu_schema) == {"escludi_allergeni": ["latte"]}
    ordine = converti_argomenti(
        {"righe": [{"nome": "carbonara", "quantita": "2"}], "data_ritiro": "", "nome_cliente": "A",
         "telefono": "3", "ora_ritiro": "20:00"},
        _schema("crea_ordine_asporto"),
    )
    assert ordine["righe"][0]["quantita"] == 2 and "data_ritiro" not in ordine


def test_conversione_non_maschera_valori_errati():
    from harness.schema_utils import converti_argomenti

    schema = _schema("verifica_disponibilita")
    convertiti = converti_argomenti({"data": "domani", "ora": "20:00", "coperti": "tanti"}, schema)
    assert list(Draft202012Validator(schema).iter_errors(convertiti))


def test_argomenti_validi_restano_validi():
    originale = _schema("crea_ordine_asporto")
    argomenti = {"nome_cliente": "A", "telefono": "333", "ora_ritiro": "20:00",
                 "righe": [{"id_articolo": 1, "quantita": 2}]}
    assert not list(Draft202012Validator(originale).iter_errors(argomenti))
    assert not list(Draft202012Validator(compatta_schema(originale)).iter_errors(argomenti))
