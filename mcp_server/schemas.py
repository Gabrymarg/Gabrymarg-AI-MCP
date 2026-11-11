"""Schemi Pydantic di ingresso/uscita dei tool MCP.

Da questi modelli l'SDK MCP genera automaticamente il JSON Schema (inputSchema /
outputSchema) pubblicato nella lista dei tool: è il "contratto" tra sistema e agente.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RigaOrdineIn(BaseModel):
    id_articolo: int = Field(description="Id del piatto, ottenuto da cerca_menu.")
    quantita: int = Field(default=1, ge=1, le=20, description="Numero di porzioni.")
    note: str | None = Field(default=None, max_length=120, description="Richieste particolari sul piatto.")


class Piatto(BaseModel):
    id_articolo: int
    nome: str
    categoria: str
    prezzo: float = Field(description="Prezzo in euro.")
    allergeni: list[str] = Field(description="Codici degli allergeni presenti.")
    vegetariano: bool
    asporto: bool = Field(description="True se ordinabile da asporto.")
    esaurito: bool = Field(description="True se oggi non è più disponibile.")


class RisultatoMenu(BaseModel):
    numero_risultati: int
    piatti: list[Piatto]


class DettaglioPiatto(BaseModel):
    id_articolo: int
    nome: str
    categoria: str
    descrizione: str
    prezzo: float
    ingredienti: list[str]
    allergeni: list[str]
    vegetariano: bool
    asporto: bool
    porzioni_disponibili: int = Field(description="Porzioni ancora preparabili con le scorte attuali (0 = esaurito).")


class Disponibilita(BaseModel):
    data: str
    ora: str
    coperti: int
    disponibile: bool
    turno: str = Field(description="'pranzo' o 'cena'.")
    sala: str | None = Field(default=None, description="Sala indicativa, se disponibile.")
    orari_alternativi: list[str] | None = Field(
        default=None, description="Altri orari liberi nello stesso turno, se l'orario richiesto non è disponibile."
    )


class Prenotazione(BaseModel):
    id_prenotazione: int
    data: str
    ora: str
    coperti: int
    nome_cliente: str
    telefono: str
    note: str | None
    stato: str
    tavolo: str
    sala: str


class ElencoPrenotazioni(BaseModel):
    numero_risultati: int
    prenotazioni: list[Prenotazione]


class RigaOrdine(BaseModel):
    id_articolo: int
    nome: str
    quantita: int
    prezzo_unitario: float
    note: str | None


class Ordine(BaseModel):
    id_ordine: int
    nome_cliente: str
    data_ritiro: str
    ora_ritiro: str
    stato: str = Field(description="ricevuto | in_preparazione | pronto | ritirato | annullato")
    totale: float
    note: str | None
    righe: list[RigaOrdine]


class OrariApertura(BaseModel):
    oggi: str = Field(description="Data e ora attuali (AAAA-MM-GGTHH:MM).")
    settimana: list[str] = Field(description="Orari per ogni giorno della settimana.")
