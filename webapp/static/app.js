// Osteria del Borgo - logica dell'interfaccia.
// Tutto il testo proveniente dal server viene inserito con textContent (mai come HTML).

"use strict";

const $ = (id) => document.getElementById(id);
const stato = { profilo: null, occupato: false, tokenSessione: 0 };

const ETICHETTE_TOOL = {
  orari_apertura: "Orari di apertura",
  cerca_menu: "Ricerca nel menu",
  dettaglio_piatto: "Dettaglio piatto",
  verifica_disponibilita: "Verifica disponibilità",
  orari_disponibili: "Orari disponibili",
  trova_prenotazioni: "Ricerca prenotazioni",
  crea_prenotazione: "Nuova prenotazione",
  modifica_prenotazione: "Modifica prenotazione",
  cancella_prenotazione: "Cancellazione prenotazione",
  prenotazioni_del_giorno: "Quadro della sala",
  crea_ordine_asporto: "Nuovo ordine da asporto",
  stato_ordine: "Stato ordine",
  ordini_da_preparare: "Ordini da preparare",
  aggiorna_stato_ordine: "Aggiornamento stato ordine",
  aggiorna_scorta: "Aggiornamento scorta",
  imposta_disponibilita_piatto: "Disponibilità piatto",
};

// ------------------------------------------------------------------ utilità

function crea(tag, classe, testo) {
  const el = document.createElement(tag);
  if (classe) el.className = classe;
  if (testo !== undefined) el.textContent = testo;
  return el;
}

async function api(percorso, opzioni = {}) {
  const risposta = await fetch(percorso, {
    method: opzioni.metodo || (opzioni.corpo ? "POST" : "GET"),
    headers: opzioni.corpo ? { "Content-Type": "application/json" } : {},
    body: opzioni.corpo ? JSON.stringify(opzioni.corpo) : undefined,
    credentials: "same-origin",
  });
  if (risposta.status === 401 && percorso !== "/api/login") {
    mostraAccesso();
    throw new Error("Sessione scaduta: effettua di nuovo l'accesso.");
  }
  if (!risposta.ok) {
    let messaggio = `Errore ${risposta.status}`;
    try { messaggio = (await risposta.json()).detail || messaggio; } catch (_) { /* risposta non JSON */ }
    throw new Error(typeof messaggio === "string" ? messaggio : "Dati non validi.");
  }
  return risposta;
}

// ------------------------------------------------------------------ accesso

function mostraAccesso() {
  $("vista-app").hidden = true;
  $("vista-accesso").hidden = false;
  $("campo-username").focus();
}

async function mostraApp(profilo) {
  stato.profilo = profilo;
  $("vista-accesso").hidden = true;
  $("vista-app").hidden = false;
  $("nome-utente").textContent = profilo.nome;
  $("ruolo-utente").textContent = profilo.descrizione_ruolo;
  $("btn-utenti").hidden = profilo.ruolo !== "admin";
  const scelta = $("scelta-modello");
  scelta.replaceChildren(...profilo.modelli.map((m) => {
    const opzione = crea("option", "", m.etichetta);
    opzione.value = m.id;
    return opzione;
  }));
  $("messaggi").replaceChildren();
  $("traccia").replaceChildren();
  await apriSessione();
}

$("form-accesso").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const errore = $("errore-accesso");
  errore.hidden = true;
  try {
    const risposta = await api("/api/login", {
      corpo: { username: $("campo-username").value, password: $("campo-password").value },
    });
    $("campo-password").value = "";
    await mostraApp(await risposta.json());
  } catch (e) {
    errore.textContent = e.message;
    errore.hidden = false;
  }
});

$("btn-esci").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST", credentials: "same-origin" });
  stato.profilo = null;
  mostraAccesso();
});

// ------------------------------------------------------------------ sessione e modello

async function apriSessione() {
  const modello = $("scelta-modello").value;
  aggiungiMessaggio("sistema", "Preparo l'assistente…");
  bloccaInvio(true);
  try {
    const risposta = await (await api("/api/sessione", { corpo: { modello } })).json();
    const scritture = risposta.strumenti.filter((s) => s.scrittura).length;
    $("messaggi").lastElementChild.textContent =
      `Assistente pronto con ${risposta.modello.etichetta}. ` +
      `Strumenti disponibili per il tuo ruolo: ${risposta.strumenti.length} (${scritture} modificano i dati e chiedono conferma).`;
    aggiungiPasso("turno", "Sessione avviata", risposta.strumenti.map((s) => ETICHETTE_TOOL[s.nome] || s.nome).join(", "));
    stato.tokenSessione = 0;
    $("token-sessione").textContent = "0";
  } catch (e) {
    $("messaggi").lastElementChild.textContent = `Assistente non disponibile: ${e.message}`;
  } finally {
    bloccaInvio(false);
  }
}

$("scelta-modello").addEventListener("change", apriSessione);

$("btn-nuova").addEventListener("click", async () => {
  try {
    await api("/api/nuova-conversazione", { metodo: "POST" });
    $("messaggi").replaceChildren();
    $("traccia").replaceChildren();
    aggiungiMessaggio("sistema", "Nuova conversazione iniziata.");
  } catch (e) {
    aggiungiMessaggio("sistema", e.message);
  }
});

// ------------------------------------------------------------------ chat

function aggiungiMessaggio(tipo, testo) {
  const li = crea("li", `messaggio ${tipo}`);
  if (tipo === "assistente") li.append(crea("span", "firma", "Osteria del Borgo"));
  li.append(document.createTextNode(testo));
  $("messaggi").append(li);
  li.scrollIntoView({ block: "end" });
  return li;
}

function bloccaInvio(bloccato) {
  stato.occupato = bloccato;
  $("btn-invia").disabled = bloccato;
}

$("campo-messaggio").addEventListener("keydown", (evento) => {
  if (evento.key === "Enter" && !evento.shiftKey) {
    evento.preventDefault();
    $("form-chat").requestSubmit();
  }
});

$("form-chat").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const testo = $("campo-messaggio").value.trim();
  if (!testo || stato.occupato) return;
  $("campo-messaggio").value = "";
  aggiungiMessaggio("utente", testo);
  const locale = $("scelta-modello").value.startsWith("ollama");
  const attesa = aggiungiMessaggio("assistente in-attesa", locale
    ? "Sto lavorando alla richiesta… Il modello locale gira sulla CPU di questo computer: la risposta può richiedere da 30 secondi a 3 minuti."
    : "Sto lavorando alla richiesta…");
  aggiungiPasso("turno", `Richiesta: «${testo.slice(0, 80)}${testo.length > 80 ? "…" : ""}»`);
  bloccaInvio(true);
  try {
    const risposta = await api("/api/chat", { corpo: { testo } });
    await leggiFlusso(risposta, attesa);
  } catch (e) {
    attesa.remove();
    aggiungiMessaggio("sistema", e.message);
  } finally {
    bloccaInvio(false);
    $("campo-messaggio").focus();
  }
});

// Lettura degli eventi Server-Sent Events dalla risposta in streaming.
async function leggiFlusso(risposta, attesa) {
  const lettore = risposta.body.getReader();
  const decodifica = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await lettore.read();
    if (done) break;
    buffer += decodifica.decode(value, { stream: true });
    let separatore;
    while ((separatore = buffer.indexOf("\n\n")) >= 0) {
      const blocco = buffer.slice(0, separatore);
      buffer = buffer.slice(separatore + 2);
      if (blocco.startsWith("data: ")) gestisciEvento(JSON.parse(blocco.slice(6)), attesa);
    }
  }
}

function gestisciEvento(e, attesa) {
  switch (e.tipo) {
    case "risposta":
      attesa.remove();
      aggiungiMessaggio("assistente", e.testo);
      stato.tokenSessione = e.token_sessione;
      $("token-sessione").textContent = e.token_sessione.toLocaleString("it-IT");
      break;
    case "errore":
      attesa.remove();
      aggiungiMessaggio("sistema", e.messaggio);
      break;
    case "richiesta_conferma":
      mostraConferma(e);
      break;
    case "attesa_fornitore":
      attesa.lastChild.textContent =
        `Il servizio del modello ha raggiunto il limite di richieste al minuto del piano gratuito: ` +
        `riprovo tra ${Math.round(e.secondi)} secondi (tentativo ${e.tentativo}). La risposta arriverà.`;
      passoDaEvento(e);
      break;
    default:
      passoDaEvento(e);
  }
}

// ------------------------------------------------------------------ conferma umana

function mostraConferma(e) {
  const scheda = crea("li", `conferma${e.distruttivo ? " distruttiva" : ""}`);
  scheda.append(crea("h3", "", e.distruttivo ? "Conferma necessaria: operazione non annullabile" : "Conferma necessaria"));
  scheda.append(crea("pre", "", e.riepilogo));
  const pulsanti = crea("div", "pulsanti");
  const si = crea("button", e.distruttivo ? "distruttivo" : "primario", "Conferma");
  const no = crea("button", "", "Annulla");
  si.type = no.type = "button";
  pulsanti.append(si, no);
  scheda.append(pulsanti);
  $("messaggi").append(scheda);
  scheda.scrollIntoView({ block: "end" });
  si.focus();

  const rispondi = async (approvato) => {
    si.disabled = no.disabled = true;
    try {
      await api("/api/conferma", { corpo: { id: e.id, approvato } });
      pulsanti.replaceWith(crea("p", "esito-conferma", approvato ? "Confermato" : "Annullato: nessuna modifica eseguita"));
    } catch (err) {
      pulsanti.replaceWith(crea("p", "esito-conferma", err.message));
    }
  };
  si.addEventListener("click", () => rispondi(true));
  no.addEventListener("click", () => rispondi(false));
}

// ------------------------------------------------------------------ comanda dell'agente

function aggiungiPasso(classe, titolo, dettaglio) {
  const li = crea("li", classe);
  li.append(crea("span", "titolo-passo", titolo));
  if (dettaglio) li.append(crea("span", "dettaglio", dettaglio));
  $("traccia").append(li);
  li.scrollIntoView({ block: "end" });
}

function argomentiLeggibili(argomenti) {
  return Object.entries(argomenti || {})
    .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`)
    .join(", ") || "nessun parametro";
}

function passoDaEvento(e) {
  const nome = ETICHETTE_TOOL[e.tool] || e.tool;
  switch (e.tipo) {
    case "risposta_modello": {
      const chiede = (e.tool_calls || []).map((t) => ETICHETTE_TOOL[t.nome] || t.nome);
      aggiungiPasso("modello", `Modello, iterazione ${e.iterazione}`,
        `${e.token_input} + ${e.token_output} token, ${(e.durata_ms / 1000).toFixed(1)} s · ` +
        (chiede.length ? `chiede: ${chiede.join(", ")}` : "risposta pronta"));
      break;
    }
    case "chiamata_tool":
      aggiungiPasso("tool", nome, argomentiLeggibili(e.argomenti));
      break;
    case "argomenti_convertiti":
      aggiungiPasso("controllo", "Tipi dei parametri corretti dall'harness", argomentiLeggibili(e.convertiti));
      break;
    case "conferma_utente":
      aggiungiPasso("conferma-passo", e.approvato ? "Confermato dall'utente" : "Negato dall'utente", nome);
      break;
    case "risultato_tool":
      if (e.ok) aggiungiPasso("ok", `${nome}: eseguito`, e.risultato || "");
      else if (e.annullato_da_utente) aggiungiPasso("ko", `${nome}: non eseguito`, "l'utente non ha confermato");
      else aggiungiPasso("ko", `${nome}: errore ${e.errore?.codice || ""}`, e.errore?.messaggio || "");
      break;
    case "guardrail_coerenza":
      aggiungiPasso("controllo", "Risposta respinta dal controllo di coerenza",
        "affermava un'operazione mai eseguita: il modello viene richiamato");
      break;
    case "tool_call_testuale_recuperata":
      aggiungiPasso("controllo", "Chiamata scritta come testo recuperata", nome);
      break;
    case "tool_call_testuale_malformata":
      aggiungiPasso("controllo", "Chiamata malformata intercettata", "non mostrata al cliente");
      break;
    case "errore_modello":
      aggiungiPasso("ko", "Modello non raggiungibile", "");
      break;
    case "attesa_fornitore":
      aggiungiPasso("controllo", "Attesa imposta dal fornitore del modello",
        `limite di token al minuto: nuovo tentativo tra ${Math.round(e.secondi)} s`);
      break;
    case "fine_turno":
      aggiungiPasso("fine", `Fine turno: ${e.motivo_arresto.replaceAll("_", " ")}`,
        `${e.token_totali} token · ${(e.durata_ms / 1000).toFixed(1)} s`);
      break;
    default:
      break;
  }
}

// ------------------------------------------------------------------ gestione utenti (admin)

const RUOLI = { cliente: "Cliente", sala: "Personale di sala", cucina: "Cucina", admin: "Amministratore" };

function esitoUtenti(testo, errore = false) {
  const el = $("esito-utenti");
  el.textContent = testo;
  el.classList.toggle("errore", errore);
}

async function modificaUtente(id, modifiche, descrizione) {
  try {
    await api(`/api/admin/utenti/${id}`, { metodo: "PATCH", corpo: modifiche });
    esitoUtenti(descrizione);
  } catch (e) {
    esitoUtenti(e.message, true);
  }
  await caricaUtenti();
}

async function caricaUtenti() {
  const elenco = await (await api("/api/admin/utenti")).json();
  const righe = elenco.map((u) => {
    const tr = crea("tr", u.attivo ? "" : "disattivo");
    tr.append(crea("td", "", u.username), crea("td", "", u.nome));

    const tdRuolo = crea("td");
    const ruolo = crea("select");
    ruolo.setAttribute("aria-label", `Ruolo di ${u.username}`);
    for (const [valore, etichetta] of Object.entries(RUOLI)) {
      const o = crea("option", "", etichetta);
      o.value = valore;
      o.selected = valore === u.ruolo;
      ruolo.append(o);
    }
    ruolo.addEventListener("change", () =>
      modificaUtente(u.id_utente, { ruolo: ruolo.value }, `Ruolo di ${u.username} aggiornato: ${RUOLI[ruolo.value]}`));
    tdRuolo.append(ruolo);

    const tdStato = crea("td");
    const attiva = crea("button", "", u.attivo ? "Disattiva" : "Riattiva");
    attiva.type = "button";
    attiva.addEventListener("click", () =>
      modificaUtente(u.id_utente, { attivo: !u.attivo }, `${u.username} ${u.attivo ? "disattivato" : "riattivato"}`));
    tdStato.append(attiva);

    const tdPassword = crea("td");
    const campo = crea("input");
    campo.type = "password";
    campo.placeholder = "nuova password";
    campo.setAttribute("aria-label", `Nuova password per ${u.username}`);
    campo.addEventListener("change", () => {
      if (campo.value) modificaUtente(u.id_utente, { password: campo.value }, `Password di ${u.username} aggiornata`);
    });
    tdPassword.append(campo);

    tr.append(tdRuolo, tdStato, tdPassword);
    return tr;
  });
  $("righe-utenti").replaceChildren(...righe);
}

$("btn-utenti").addEventListener("click", async () => {
  esitoUtenti("");
  try {
    await caricaUtenti();
    $("pannello-utenti").showModal();
  } catch (e) {
    aggiungiMessaggio("sistema", e.message);
  }
});

$("btn-chiudi-utenti").addEventListener("click", () => $("pannello-utenti").close());

$("form-nuovo-utente").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const dati = Object.fromEntries(new FormData(evento.target));
  if (!dati.telefono) delete dati.telefono;
  try {
    await api("/api/admin/utenti", { corpo: dati });
    esitoUtenti(`Utente ${dati.username} aggiunto`);
    evento.target.reset();
    await caricaUtenti();
  } catch (e) {
    esitoUtenti(e.message, true);
  }
});

// ------------------------------------------------------------------ avvio

(async () => {
  try {
    const risposta = await fetch("/api/me", { credentials: "same-origin" });
    if (risposta.ok) await mostraApp(await risposta.json());
    else mostraAccesso();
  } catch (_) {
    mostraAccesso();
  }
})();
