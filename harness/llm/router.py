"""Instradamento tra modelli: un modello locale per le richieste semplici, uno cloud per quelle delicate.

RouterProvider è a sua volta un LLMProvider (pattern Composite): il ciclo agentico non sa di parlare
con due modelli. A ogni chiamata sceglie il modello con regole esplicite e verificabili:

  1. CLOUD se, dopo l'ultimo messaggio dell'utente, l'harness ha dovuto correggere il modello
     (avviso del guardrail o chiamata malformata) o un tool ha restituito un errore: si "scala" al
     modello più capace proprio quando il compito si è rivelato difficile;
  2. CLOUD se la richiesta, o quella precedente a cui l'utente sta rispondendo, chiede di modificare
     dati (prenotare, cancellare, ordinare, aggiornare il magazzino...): le scritture sono le operazioni
     in cui un errore costa di più;
  3. CLOUD se la richiesta riguarda allergeni, intolleranze o diete: un errore è un rischio per la
     salute. La regola è nata da una prova reale, in cui il modello locale ha letto correttamente la
     scheda del tiramisù (glutine, latte, uova) e ha poi risposto che non conteneva glutine;
  4. CLOUD se la richiesta è lunga (più istruzioni nella stessa frase);
  5. LOCALE in tutti gli altri casi (menu, orari, disponibilità): gratuito e senza inviare la
     conversazione a un fornitore esterno.

Una volta passato al cloud, il turno ci resta fino alla risposta: non si torna al modello meno capace
proprio mentre si scrive la risposta finale. Se il modello scelto non risponde (servizio
irraggiungibile, limite del piano gratuito), si ripiega sull'altro. Il motivo di ogni scelta finisce nel
log, così il comportamento del router è analizzabile.
"""

from __future__ import annotations

import json
import re
from typing import Callable

from harness.llm.base import LLMProvider, LLMResponse, Messaggio, ToolSpec

INTENTO_SCRITTURA = re.compile(
    r"\b(prenot(?:a|are|ami|iamo|ate|i|o)\b|cancell\w*|annull\w*|modific\w*|spost\w*|disdi\w*"
    r"|vo(?:rrei|rremmo|levo|levamo)\s+(?:venire|un\s+tavolo|mangiare\s+da\s+voi)"
    r"|ordin(?:a|are|o|iamo)\b|vorrei\s+(?:ordinare|prenotare|\d)|da\s+asporto"
    r"|aggiung\w*|segn[ao]\w*|togli\w*|rimett\w*|carico|inventario|arrivat[oaie])",
    re.IGNORECASE,
)
TEMA_SALUTE = re.compile(
    r"\b(allerg\w*|intolleran\w*|celiac\w*|glutine|lattosio|senza\s+latte|uov[ao]|arachid\w*|frutta\s+a\s+guscio"
    r"|crostace\w*|mollusch\w*|sesamo|sedano|senape|soia|lupin\w*|solfit\w*|vegan\w*|vegetarian\w*|incint\w*)",
    re.IGNORECASE,
)
# Un numero di telefono nella richiesta indica che l'utente sta dando i propri dati per un'operazione.
TELEFONO = re.compile(r"(?:\+39\s?)?3\d{2}[\s.-]?\d{3}[\s.-]?\d{3,4}\b")
LUNGHEZZA_COMPLESSA = 280


def scegli(messaggi: list[Messaggio]) -> tuple[str, str]:
    """Restituisce ("locale" | "cloud", motivo)."""
    indici_utente = [i for i, m in enumerate(messaggi) if m.ruolo == "user"]
    if not indici_utente:
        return "locale", "nessuna richiesta dell'utente"
    ultimo = indici_utente[-1]
    for m in messaggi[ultimo + 1:]:
        if m.ruolo == "system":
            return "cloud", "l'harness ha dovuto correggere il modello in questo turno"
        if m.ruolo == "tool":
            try:
                esito = json.loads(m.contenuto)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(esito, dict) and esito.get("ok") is False and not esito.get("annullato_da_utente"):
                return "cloud", "un tool ha restituito un errore in questo turno"
    richiesta = messaggi[ultimo].contenuto
    if INTENTO_SCRITTURA.search(richiesta):
        return "cloud", "richiesta di modifica dei dati"
    if TELEFONO.search(richiesta):
        return "cloud", "dati personali forniti per un'operazione"
    # L'utente sta rispondendo a una domanda dell'assistente su un'operazione di scrittura
    # (es. "Mario Rossi, 333 1234567" dopo "Mi dice nome e telefono per la prenotazione?").
    # Se invece fa a sua volta una domanda, è una richiesta nuova e si valuta da sola.
    if len(indici_utente) > 1 and not richiesta.rstrip().endswith("?"):
        precedente = messaggi[indici_utente[-2]].contenuto
        risposta_assistente = next(
            (m.contenuto for m in reversed(messaggi[:ultimo]) if m.ruolo == "assistant" and m.contenuto), ""
        )
        if INTENTO_SCRITTURA.search(precedente) and risposta_assistente.rstrip().endswith("?"):
            return "cloud", "seguito di una richiesta di modifica dei dati"
    if TEMA_SALUTE.search(richiesta):
        return "cloud", "domanda su allergeni o diete (rischio per la salute)"
    if len(richiesta) > LUNGHEZZA_COMPLESSA:
        return "cloud", "richiesta lunga o con più istruzioni"
    return "locale", "richiesta di sola consultazione"


class RouterProvider(LLMProvider):
    nome = "router"

    def __init__(self, locale: LLMProvider, cloud: LLMProvider):
        super().__init__(f"{locale.modello} | {cloud.modello}")
        self.modelli = {"locale": locale, "cloud": cloud}
        self.notifica_attesa: Callable[[float, int], None] | None = None
        self.scelte = {"locale": 0, "cloud": 0}
        self._turno_in_cloud: int | None = None  # posizione della richiesta il cui turno è passato al cloud

    def chat(self, messaggi: list[Messaggio], strumenti: list[ToolSpec]) -> LLMResponse:
        destinazione, motivo = scegli(messaggi)
        turno = max((i for i, m in enumerate(messaggi) if m.ruolo == "user"), default=-1)
        if destinazione == "locale" and self._turno_in_cloud == turno:
            destinazione, motivo = "cloud", "il turno è già passato al modello cloud"
        altro = "cloud" if destinazione == "locale" else "locale"
        try:
            r = self._chiedi(destinazione, messaggi, strumenti)
        except Exception as e:  # modello scelto non disponibile: si ripiega sull'altro
            motivo = f"{motivo}; ripiego: {destinazione} non disponibile ({type(e).__name__})"
            destinazione = altro
            r = self._chiedi(destinazione, messaggi, strumenti)
        self.scelte[destinazione] += 1
        if destinazione == "cloud":
            self._turno_in_cloud = turno
        r.instradamento = f"{destinazione}: {motivo}"
        return r

    def _chiedi(self, destinazione: str, messaggi: list[Messaggio], strumenti: list[ToolSpec]) -> LLMResponse:
        provider = self.modelli[destinazione]
        provider.notifica_flusso = self.notifica_flusso
        if hasattr(provider, "notifica_attesa"):
            provider.notifica_attesa = self.notifica_attesa
        return provider.chat(messaggi, strumenti)

    def descrizione(self) -> str:
        return f"router({self.modelli['locale'].descrizione()}, {self.modelli['cloud'].descrizione()})"
