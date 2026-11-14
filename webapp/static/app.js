// Osteria del Borgo - logica dell'interfaccia.
// Tutto il testo proveniente dal server viene inserito con textContent (mai come HTML).

"use strict";

const $ = (id) => document.getElementById(id);

// Tema: ?tema=chiaro (o scuro / sistema) viene ricordato nel browser.
(() => {
  let tema = new URLSearchParams(location.search).get("tema");
  try {
    if (tema) localStorage.setItem("tema", tema);
    else tema = localStorage.getItem("tema");
  } catch (_) { /* archiviazione non disponibile */ }
  if (tema === "chiaro") document.documentElement.dataset.tema = "chiaro";
})();
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
  giacenze_ingredienti: "Giacenze di magazzino",
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
  $("btn-menu").hidden = profilo.ruolo !== "admin";
  $("btn-cruscotto").hidden = profilo.ruolo !== "admin";
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

// Resa minima e sicura del Markdown usato dai modelli: **grassetto**, elenchi "- " e tabelle "| a | b |".
// Si costruiscono nodi DOM (mai innerHTML), quindi il testo non può iniettare codice.
function testoInLinea(testo) {
  const frammento = document.createDocumentFragment();
  for (const parte of testo.replace(/^(\s*)[-*] /gm, "$1• ").split(/(\*\*[^*\n]+\*\*)/)) {
    if (/^\*\*[^*\n]+\*\*$/.test(parte)) frammento.append(crea("strong", "", parte.slice(2, -2)));
    else if (parte) frammento.append(document.createTextNode(parte));
  }
  return frammento;
}

function tabellaMarkdown(righe) {
  const celle = (riga) => riga.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
  const corpo = righe.filter((r) => !/^\s*\|?[\s:|-]+\|?\s*$/.test(r));  // toglie la riga |---|---|
  const tabella = crea("table", "tabella-chat");
  corpo.forEach((riga, i) => {
    const tr = crea("tr");
    for (const c of celle(riga)) {
      const td = crea(i === 0 ? "th" : "td");
      td.append(testoInLinea(c));
      tr.append(td);
    }
    tabella.append(tr);
  });
  return tabella;
}

function testoFormattato(testo) {
  const frammento = document.createDocumentFragment();
  const righe = testo.split("\n");
  let testoNormale = [];
  const svuota = () => {
    if (testoNormale.length) frammento.append(testoInLinea(testoNormale.join("\n")));
    testoNormale = [];
  };
  for (let i = 0; i < righe.length; i++) {
    if (/^\s*\|.*\|\s*$/.test(righe[i]) && /^\s*\|?[\s:|-]+\|?\s*$/.test(righe[i + 1] || "")) {
      svuota();
      const blocco = [];
      while (i < righe.length && /^\s*\|.*\|\s*$/.test(righe[i])) blocco.push(righe[i++]);
      i--;
      frammento.append(tabellaMarkdown(blocco));
    } else {
      testoNormale.push(righe[i]);
    }
  }
  svuota();
  return frammento;
}

function aggiungiMessaggio(tipo, testo) {
  const li = crea("li", `messaggio ${tipo}`);
  if (tipo === "assistente") li.append(crea("span", "firma", "Osteria del Borgo"));
  li.append(tipo === "assistente" ? testoFormattato(testo) : document.createTextNode(testo));
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
  const scelta = $("scelta-modello").value;
  const attesa = aggiungiMessaggio("assistente in-attesa", scelta.startsWith("ollama")
    ? "Sto lavorando alla richiesta… Il modello locale gira sulla CPU di questo computer: la risposta può richiedere da 30 secondi a 3 minuti."
    : scelta.startsWith("router")
      ? "Sto lavorando alla richiesta… Le consultazioni le gestisce il modello locale (più lento), le modifiche dei dati quello in cloud."
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
    case "flusso_modello":
      flussoInAttesa(attesa, e);
      break;
    case "risposta_modello":
      chiudiFlusso(attesa, e);
      passoDaEvento(e);
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

// ------------------------------------------------------------------ risposta in diretta

// Frammenti generati dal modello (streaming): il ragionamento, se il modello lo produce, e il testo.
function preparaFlusso(attesa) {
  if (!attesa.dataset.flusso) {
    attesa.dataset.flusso = "1";
    attesa.replaceChildren(crea("span", "firma", "Osteria del Borgo"));
    const pensiero = crea("details", "pensiero-live");
    pensiero.open = true;
    pensiero.hidden = true;
    pensiero.append(crea("summary", "", "Sto ragionando…"), crea("p"));
    attesa.append(pensiero, crea("p", "bozza"), crea("p", "stato-live"));
  }
}

function flussoInAttesa(attesa, e) {
  preparaFlusso(attesa);
  if (e.fase === "pensiero") {
    const pensiero = attesa.querySelector(".pensiero-live");
    pensiero.hidden = false;
    pensiero.querySelector("p").textContent += e.frammento;
  } else {
    attesa.querySelector(".bozza").textContent += e.frammento;
    attesa.querySelector(".stato-live").textContent = "";
  }
  attesa.scrollIntoView({ block: "end" });
}

// Fine di un'iterazione: la bozza si azzera (la risposta definitiva arriva a parte, già controllata
// dall'harness) e, se il modello ha chiesto strumenti, si mostra cosa sta facendo.
function chiudiFlusso(attesa, e) {
  preparaFlusso(attesa);
  const strumenti = (e.tool_calls || []).map((t) => ETICHETTE_TOOL[t.nome] || t.nome).join(", ");
  attesa.querySelector(".bozza").textContent = "";
  const pensiero = attesa.querySelector(".pensiero-live");
  pensiero.querySelector("p").textContent = "";
  pensiero.hidden = true;
  attesa.querySelector(".stato-live").textContent = strumenti ? `Sto consultando: ${strumenti}…` : "Controllo la risposta…";
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
      const via = e.instradamento ? ` · ${e.modello} (${e.instradamento.replace(/^(locale|cloud): /, "$1, ")})` : "";
      aggiungiPasso("modello", `Modello, iterazione ${e.iterazione}${via}`,
        `${e.token_input} + ${e.token_output} token, ${(e.durata_ms / 1000).toFixed(1)} s · ` +
        (chiede.length ? `chiede: ${chiede.join(", ")}` : "risposta pronta"));
      if (e.ragionamento) {
        const dettagli = crea("details", "ragionamento");
        dettagli.append(crea("summary", "", "Ragionamento del modello"), crea("p", "", e.ragionamento));
        $("traccia").lastElementChild.append(dettagli);
      }
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
    case "guardrail_riferimenti":
      aggiungiPasso("controllo", "Risposta respinta: numero non verificato",
        `${e.riferimenti.join(", ")} non compare in nessun risultato dei tool`);
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

// ------------------------------------------------------------------ menu e magazzino (admin)

const menu = { dati: null, modifica: { articoli: null, ingredienti: null, categorie: null } };
const euro = (n) => n.toLocaleString("it-IT", { style: "currency", currency: "EUR" });
const quantita = (n, unita) => `${n.toLocaleString("it-IT", { maximumFractionDigits: 2 })} ${unita}`;

function esitoMenu(testo, errore = false) {
  const el = $("esito-menu");
  el.textContent = testo;
  el.classList.toggle("errore", errore);
}

function pulsante(testo, classe, azione) {
  const b = crea("button", classe, testo);
  b.type = "button";
  b.addEventListener("click", azione);
  return b;
}

// Eliminazione in due clic: il primo chiede conferma, il secondo (entro 4 secondi) elimina.
function pulsanteElimina(descrizione, azione) {
  const b = pulsante("Elimina", "", () => {
    if (b.dataset.armato) return azione();
    b.dataset.armato = "1";
    b.textContent = "Conferma eliminazione";
    b.classList.add("distruttivo");
    b.setAttribute("aria-label", `Conferma l'eliminazione di ${descrizione}`);
    setTimeout(() => {
      delete b.dataset.armato;
      b.textContent = "Elimina";
      b.classList.remove("distruttivo");
      b.removeAttribute("aria-label");
    }, 4000);
  });
  return b;
}

async function salvaAnagrafica(tipo, corpo, descrizione) {
  const id = menu.modifica[tipo];
  try {
    await api(`/api/admin/${tipo}${id ? `/${id}` : ""}`, { metodo: id ? "PUT" : "POST", corpo });
    const o = tipo === "categorie" ? "a" : "o";
    esitoMenu(`${descrizione} ${id ? "aggiornat" : "aggiunt"}${o}`);
    chiudiForm(tipo);
    await caricaMenu();
    return true;
  } catch (e) {
    esitoMenu(e.message, true);
    return false;
  }
}

async function eliminaAnagrafica(tipo, id, descrizione) {
  try {
    await api(`/api/admin/${tipo}/${id}`, { metodo: "DELETE" });
    esitoMenu(`${descrizione} eliminat${tipo === "categorie" ? "a" : "o"}`);
    await caricaMenu();
  } catch (e) {
    esitoMenu(e.message, true);
  }
}

const FORM = { articoli: "form-articolo", ingredienti: "form-ingrediente", categorie: "form-categoria" };
const TITOLI_NUOVO = { articoli: "Nuovo articolo", ingredienti: "Nuovo ingrediente", categorie: "Nuova categoria" };

function chiudiForm(tipo) {
  menu.modifica[tipo] = null;
  const form = $(FORM[tipo]);
  form.reset();
  $(`titolo-${FORM[tipo]}`).textContent = TITOLI_NUOVO[tipo];
  if (tipo === "articoli") form.hidden = true;
}

// --- articoli

function rigaRicetta(riga = {}) {
  const li = crea("li");
  const scelta = crea("select");
  scelta.setAttribute("aria-label", "Ingrediente");
  for (const i of menu.dati.ingredienti) {
    const o = crea("option", "", `${i.nome} (${i.unita_misura})`);
    o.value = i.id_ingrediente;
    o.selected = i.id_ingrediente === riga.id_ingrediente;
    scelta.append(o);
  }
  const q = crea("input");
  Object.assign(q, { type: "number", min: "0", step: "any", required: true, value: riga.quantita ?? "" });
  q.setAttribute("aria-label", "Quantità per porzione");
  li.append(scelta, q, pulsante("Togli", "", () => li.remove()));
  return li;
}

function apriArticolo(a) {
  const form = $("form-articolo");
  menu.modifica.articoli = a ? a.id_articolo : null;
  form.reset();
  $("titolo-form-articolo").textContent = a ? `Modifica: ${a.nome}` : "Nuovo articolo";
  form.elements.id_categoria.replaceChildren(...menu.dati.categorie.map((c) => {
    const o = crea("option", "", c.nome);
    o.value = c.id_categoria;
    return o;
  }));
  if (a) {
    for (const campo of ["nome", "descrizione", "prezzo", "id_categoria"]) form.elements[campo].value = a[campo];
  }
  form.elements.vegetariano.checked = a ? a.vegetariano : false;
  form.elements.asporto.checked = a ? a.asporto : true;
  form.elements.attivo.checked = a ? a.attivo : true;
  $("spunte-allergeni").replaceChildren(...menu.dati.allergeni.map((al) => {
    const etichetta = crea("label");
    const spunta = crea("input");
    Object.assign(spunta, { type: "checkbox", name: "allergene", value: al.codice, checked: !!a?.allergeni.includes(al.codice) });
    etichetta.append(spunta, ` ${al.nome}`);
    return etichetta;
  }));
  $("righe-ricetta").replaceChildren(...(a ? a.ricetta.map(rigaRicetta) : []));
  form.hidden = false;
  form.scrollIntoView({ block: "start", behavior: "smooth" });
  form.elements.nome.focus();
}

function disegnaArticoli() {
  const filtro = $("filtro-articoli").value.trim().toLowerCase();
  const righe = menu.dati.articoli
    .filter((a) => !filtro || a.nome.toLowerCase().includes(filtro))
    .map((a) => {
      const tr = crea("tr", a.attivo ? "" : "disattivo");
      const stato = [a.attivo ? "Nel menu" : "Fuori menu", a.vegetariano ? "vegetariano" : "", a.asporto ? "" : "no asporto"]
        .filter(Boolean).join(", ");
      const azioni = crea("td", "azioni-riga");
      azioni.append(pulsante("Modifica", "", () => apriArticolo(a)));
      tr.append(crea("td", "", a.nome), crea("td", "", a.categoria), crea("td", "num", euro(a.prezzo)),
        crea("td", "allergeni-cella", a.allergeni.join(", ") || "nessuno"), crea("td", "", stato), azioni);
      return tr;
    });
  $("righe-articoli").replaceChildren(...righe);
}

$("form-articolo").addEventListener("submit", (evento) => {
  evento.preventDefault();
  const f = evento.target.elements;
  const corpo = {
    nome: f.nome.value,
    descrizione: f.descrizione.value,
    prezzo: Number(f.prezzo.value),
    id_categoria: Number(f.id_categoria.value),
    vegetariano: f.vegetariano.checked,
    asporto: f.asporto.checked,
    attivo: f.attivo.checked,
    allergeni: [...evento.target.querySelectorAll("input[name=allergene]:checked")].map((s) => s.value),
    ricetta: [...$("righe-ricetta").children].map((li) => ({
      id_ingrediente: Number(li.querySelector("select").value),
      quantita: Number(li.querySelector("input").value),
    })),
  };
  salvaAnagrafica("articoli", corpo, `Articolo ${corpo.nome}`);
});

$("btn-nuovo-articolo").addEventListener("click", () => apriArticolo(null));
$("btn-aggiungi-riga").addEventListener("click", () => $("righe-ricetta").append(rigaRicetta()));
$("filtro-articoli").addEventListener("input", disegnaArticoli);

// --- ingredienti

function disegnaIngredienti() {
  const filtro = $("filtro-ingredienti").value.trim().toLowerCase();
  const soloSotto = $("solo-sotto-scorta").checked;
  const righe = menu.dati.ingredienti
    .filter((i) => (!filtro || i.nome.toLowerCase().includes(filtro)) && (!soloSotto || i.sotto_scorta_minima))
    .map((i) => {
      const tr = crea("tr", i.sotto_scorta_minima ? "sotto-scorta" : "");
      const disponibile = crea("td", "num", quantita(i.quantita_disponibile, i.unita_misura));
      if (i.sotto_scorta_minima) disponibile.append(crea("span", "segnale", "sotto scorta"));
      const azioni = crea("td", "azioni-riga");
      azioni.append(pulsante("Modifica", "", () => {
        const f = $("form-ingrediente").elements;
        menu.modifica.ingredienti = i.id_ingrediente;
        for (const campo of ["nome", "unita_misura", "quantita_disponibile", "scorta_minima"]) f[campo].value = i[campo];
        $("titolo-form-ingrediente").textContent = `Modifica: ${i.nome}`;
        f.quantita_disponibile.focus();
      }));
      if (!i.numero_ricette) azioni.append(pulsanteElimina(i.nome, () => eliminaAnagrafica("ingredienti", i.id_ingrediente, `Ingrediente ${i.nome}`)));
      tr.append(crea("td", "", i.nome), disponibile, crea("td", "num", quantita(i.scorta_minima, i.unita_misura)),
        crea("td", "num", String(i.numero_ricette)), azioni);
      return tr;
    });
  $("righe-ingredienti").replaceChildren(...righe);
}

$("form-ingrediente").addEventListener("submit", (evento) => {
  evento.preventDefault();
  const f = evento.target.elements;
  salvaAnagrafica("ingredienti", {
    nome: f.nome.value,
    unita_misura: f.unita_misura.value,
    quantita_disponibile: Number(f.quantita_disponibile.value),
    scorta_minima: Number(f.scorta_minima.value),
  }, `Ingrediente ${f.nome.value}`);
});

$("filtro-ingredienti").addEventListener("input", disegnaIngredienti);
$("solo-sotto-scorta").addEventListener("change", disegnaIngredienti);

// --- categorie

function disegnaCategorie() {
  const righe = menu.dati.categorie.map((c) => {
    const tr = crea("tr");
    const azioni = crea("td", "azioni-riga");
    azioni.append(pulsante("Modifica", "", () => {
      const f = $("form-categoria").elements;
      menu.modifica.categorie = c.id_categoria;
      f.nome.value = c.nome;
      f.ordine.value = c.ordine;
      $("titolo-form-categoria").textContent = `Modifica: ${c.nome}`;
      f.nome.focus();
    }));
    if (!c.numero_articoli) azioni.append(pulsanteElimina(c.nome, () => eliminaAnagrafica("categorie", c.id_categoria, `Categoria ${c.nome}`)));
    tr.append(crea("td", "num", String(c.ordine)), crea("td", "", c.nome), crea("td", "num", String(c.numero_articoli)), azioni);
    return tr;
  });
  $("righe-categorie").replaceChildren(...righe);
}

$("form-categoria").addEventListener("submit", (evento) => {
  evento.preventDefault();
  const f = evento.target.elements;
  salvaAnagrafica("categorie", { nome: f.nome.value, ordine: f.ordine.value === "" ? null : Number(f.ordine.value) },
    `Categoria ${f.nome.value}`);
});

// --- pannello

for (const tipo of Object.keys(FORM)) {
  $(FORM[tipo]).querySelector(".annulla-form").addEventListener("click", () => chiudiForm(tipo));
}

for (const scheda of document.querySelectorAll("#pannello-menu [role=tab]")) {
  scheda.addEventListener("click", () => {
    for (const altra of document.querySelectorAll("#pannello-menu [role=tab]")) {
      const attiva = altra === scheda;
      altra.setAttribute("aria-selected", String(attiva));
      $(altra.getAttribute("aria-controls")).hidden = !attiva;
    }
    esitoMenu("");
  });
}

async function caricaMenu() {
  menu.dati = await (await api("/api/admin/menu")).json();
  disegnaArticoli();
  disegnaIngredienti();
  disegnaCategorie();
}

$("btn-menu").addEventListener("click", async () => {
  esitoMenu("");
  try {
    await caricaMenu();
    $("pannello-menu").showModal();
  } catch (e) {
    aggiungiMessaggio("sistema", e.message);
  }
});

$("btn-chiudi-menu").addEventListener("click", () => $("pannello-menu").close());

// ------------------------------------------------------------------ storico delle conversazioni

const storicoStato = { elenco: [], letta: null };

function esitoStorico(testo, errore = false) {
  const el = $("esito-storico");
  el.textContent = testo;
  el.classList.toggle("errore", errore);
}

async function riprendiConversazione(id) {
  try {
    const c = await (await api(`/api/conversazioni/${id}/riprendi`, { metodo: "POST" })).json();
    $("pannello-storico").close();
    $("messaggi").replaceChildren();
    $("traccia").replaceChildren();
    for (const m of c.messaggi) aggiungiMessaggio(m.ruolo === "utente" ? "utente" : "assistente", m.testo);
    aggiungiMessaggio("sistema", `Conversazione ripresa: «${c.titolo}». Puoi continuare a scrivere.`);
    aggiungiPasso("turno", "Conversazione ripresa", `${c.messaggi.length} messaggi ripristinati`);
  } catch (e) {
    esitoStorico(e.message, true);
  }
}

async function eliminaConversazione(c) {
  try {
    await api(`/api/conversazioni/${c.id_conversazione}`, { metodo: "DELETE" });
    esitoStorico(`Conversazione «${c.titolo}» eliminata`);
    await caricaStorico();
  } catch (e) {
    esitoStorico(e.message, true);
  }
}

async function leggiConversazione(c) {
  try {
    const dati = await (await api(`/api/conversazioni/${c.id_conversazione}`)).json();
    storicoStato.letta = dati;
    $("titolo-lettura").textContent = dati.propria ? dati.titolo : `${dati.titolo} (utente: ${dati.username})`;
    $("messaggi-lettura").replaceChildren(...dati.messaggi.map((m) => {
      const li = crea("li", `messaggio ${m.ruolo === "utente" ? "utente" : "assistente"}`);
      if (m.ruolo !== "utente") li.append(crea("span", "firma", "Osteria del Borgo"));
      li.append(m.ruolo === "utente" ? document.createTextNode(m.testo) : testoFormattato(m.testo));
      li.append(crea("span", "orario", data(m.creato_il)));
      return li;
    }));
    $("btn-riprendi-letta").hidden = !dati.propria;
    $("elenco-storico").hidden = true;
    $("lettura-storico").hidden = false;
  } catch (e) {
    esitoStorico(e.message, true);
  }
}

function disegnaStorico() {
  const filtro = $("filtro-storico").value.trim().toLowerCase();
  const tutte = $("storico-tutte").checked;
  for (const th of document.querySelectorAll("#pannello-storico .colonna-utente")) th.hidden = !tutte;
  const righe = storicoStato.elenco
    .filter((c) => !filtro || c.titolo.toLowerCase().includes(filtro))
    .map((c) => {
      const tr = crea("tr");
      const utente = crea("td", "colonna-utente", c.propria ? "tu" : `${c.nome} (${c.username})`);
      utente.hidden = !tutte;
      const azioni = crea("td", "azioni-riga");
      azioni.append(pulsante("Leggi", "", () => leggiConversazione(c)));
      if (c.propria) {
        azioni.append(pulsante("Riprendi", "", () => riprendiConversazione(c.id_conversazione)));
        azioni.append(pulsanteElimina(c.titolo, () => eliminaConversazione(c)));
      }
      tr.append(crea("td", "", c.titolo), utente, crea("td", "", data(c.aggiornata_il)),
        crea("td", "num", String(c.numero_messaggi)), azioni);
      return tr;
    });
  $("righe-storico").replaceChildren(...righe);
  if (!righe.length) {
    const tr = crea("tr");
    const td = crea("td", "vuoto", filtro ? "Nessuna conversazione con questo titolo." : "Non ci sono ancora conversazioni salvate.");
    td.colSpan = 5;
    tr.append(td);
    $("righe-storico").append(tr);
  }
}

async function caricaStorico() {
  const tutte = $("storico-tutte").checked;
  storicoStato.elenco = await (await api(`/api/conversazioni${tutte ? "?tutte=true" : ""}`)).json();
  disegnaStorico();
}

$("btn-storico").addEventListener("click", async () => {
  esitoStorico("");
  $("etichetta-tutte").hidden = stato.profilo?.ruolo !== "admin";
  $("elenco-storico").hidden = false;
  $("lettura-storico").hidden = true;
  try {
    await caricaStorico();
    $("pannello-storico").showModal();
  } catch (e) {
    aggiungiMessaggio("sistema", e.message);
  }
});
$("storico-tutte").addEventListener("change", () => caricaStorico().catch((e) => esitoStorico(e.message, true)));
$("filtro-storico").addEventListener("input", disegnaStorico);
$("btn-torna-storico").addEventListener("click", () => {
  $("lettura-storico").hidden = true;
  $("elenco-storico").hidden = false;
});
$("btn-riprendi-letta").addEventListener("click", () => riprendiConversazione(storicoStato.letta.id_conversazione));
$("btn-chiudi-storico").addEventListener("click", () => $("pannello-storico").close());

// ------------------------------------------------------------------ cruscotto (admin)

const numero = (n, decimali = 0) => n.toLocaleString("it-IT", { maximumFractionDigits: decimali, useGrouping: "always" });
const dollari = (n) => `${n.toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 4 })} $`;
const data = (iso) => iso ? new Date(iso).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "-";

function riquadro(valore, etichetta, nota, stato) {
  const r = crea("div", `riquadro${stato ? ` ${stato}` : ""}`);
  r.append(crea("span", "valore", valore), crea("span", "etichetta", etichetta));
  if (nota) r.append(crea("span", "nota", nota));
  return r;
}

// Barre orizzontali a una sola serie: la lunghezza codifica il valore, che è comunque scritto accanto.
function barre(contenitore, voci) {
  const massimo = Math.max(1, ...voci.map((v) => v.valore));
  contenitore.replaceChildren(...voci.map((v) => {
    const li = crea("li");
    li.title = `${v.etichetta}: ${numero(v.valore)}`;
    const traccia = crea("span", "traccia-barra");
    const barra = crea("span", "riempimento-barra");
    barra.style.width = `${(100 * v.valore) / massimo}%`;
    traccia.append(barra);
    li.append(crea("span", "nome-barra", v.etichetta), traccia, crea("span", "valore-barra", numero(v.valore)));
    return li;
  }));
  if (!voci.length) contenitore.append(crea("li", "vuoto", "Nessun dato nel periodo."));
}

function disegnaCruscotto(m) {
  $("periodo-cruscotto").textContent = m.turni
    ? `${numero(m.sessioni)} sessioni dal ${data(m.periodo.dal)} al ${data(m.periodo.al)}`
    : "Nessuna conversazione registrata finora.";
  $("kpi-uso").replaceChildren(
    riquadro(numero(m.turni), "richieste gestite"),
    riquadro(`${m.completati_pct}%`, "completate con una risposta", "le altre si sono fermate in modo controllato"),
    riquadro(`${numero(m.tempo_turno_s.mediana, 1)} s`, "tempo mediano di risposta", `il 90% entro ${numero(m.tempo_turno_s.p90, 1)} s`),
    riquadro(numero(m.token_per_turno), "token per richiesta", `${numero(m.token_totali)} in totale`),
    riquadro(dollari(m.costo_usd), "costo stimato totale", `${dollari(m.costo_per_turno_usd)} per richiesta`),
  );
  const s = m.sicurezza;
  $("kpi-sicurezza").replaceChildren(
    riquadro(numero(s.scritture_senza_conferma), "scritture senza conferma",
      `su ${numero(s.scritture_eseguite)} scritture eseguite`, s.scritture_senza_conferma ? "allarme" : "buono"),
    riquadro(`${numero(s.conferme_negate)} / ${numero(s.conferme_richieste)}`, "conferme negate dall'utente", "operazioni non eseguite"),
    riquadro(numero(s.permessi_negati), "tentativi fuori dal proprio ruolo", "bloccati dal server MCP"),
    riquadro(numero(s.risposte_respinte_coerenza + s.numeri_inventati_bloccati), "risposte respinte dall'harness",
      `${numero(s.numeri_inventati_bloccati)} con numeri inventati`),
    riquadro(numero(s.chiamate_bloccate + s.correzioni_formato), "chiamate corrette o bloccate", "parametri non validi, formato errato"),
  );
  barre($("barre-strumenti"), m.strumenti.slice(0, 8).map((x) => ({ etichetta: ETICHETTE_TOOL[x.nome] || x.nome, valore: x.chiamate })));
  barre($("barre-esiti"), m.arresti.map((x) => ({ etichetta: x.etichetta, valore: x.turni })));
  $("righe-modelli").replaceChildren(...m.modelli.map((x) => {
    const tr = crea("tr");
    tr.append(
      crea("td", "", x.modello + (x.locale ? " (locale)" : "")), crea("td", "num", numero(x.chiamate)),
      crea("td", "num", numero(x.token_input)), crea("td", "num", numero(x.token_output)),
      crea("td", "num", numero(x.secondi_medi, 1)), crea("td", "num", x.locale ? "gratuito" : dollari(x.costo_usd)),
    );
    return tr;
  }));
  $("sezione-router").hidden = !m.router.length;
  barre($("barre-router"), m.router.map((x) => ({ etichetta: `${x.destinazione === "cloud" ? "Cloud" : "Locale"}: ${x.motivo}`, valore: x.chiamate })));
}

async function caricaCruscotto() {
  disegnaCruscotto(await (await api("/api/admin/metriche")).json());
}

$("btn-cruscotto").addEventListener("click", async () => {
  try {
    await caricaCruscotto();
    $("pannello-cruscotto").showModal();
  } catch (e) {
    aggiungiMessaggio("sistema", e.message);
  }
});
$("btn-aggiorna-cruscotto").addEventListener("click", () => caricaCruscotto().catch((e) => aggiungiMessaggio("sistema", e.message)));
$("btn-chiudi-cruscotto").addEventListener("click", () => $("pannello-cruscotto").close());

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
