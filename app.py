import pandas as pd
import streamlit as st

import flight_logic as fl

st.set_page_config(page_title="Flight Finder Roma", page_icon="✈️", layout="wide")

st.title("✈️ Personal Flight Finder da Roma (FCO / CIA)")
st.caption("Weekend lunghi, ponti e offerte low-cost ESTERE in partenza da Roma, con i tuoi filtri.")

MODO_BOT = "📦 Ultimi risultati del bot (gratis)"
MODO_LIVE = "🔍 Ricerca live (usa crediti SerpAPI)"


def secret(nome):
    try:
        return st.secrets[nome]
    except Exception:
        return None


serpapi_key = secret("SERPAPI_KEY")


@st.cache_data(ttl=600, show_spinner=False)
def quota_serpapi(chiave):
    return fl.quota_account(chiave)


# --- SIDEBAR: PARAMETRI E FILTRI ---
st.sidebar.header("⚙️ Filtri")
budget_max = st.sidebar.slider("Budget Massimo A/R (€)", min_value=20, max_value=400, value=160, step=5)
durata_max_ore = st.sidebar.slider("Durata Max Volo (ore)", min_value=1.0, max_value=6.0, value=2.5, step=0.5,
                                   help="Se Google non indica la durata, il volo non viene scartato.")

st.sidebar.subheader("📅 Tipologia di Viaggio")
tipo_viaggio = st.sidebar.selectbox(
    "Formato date", list(fl.TIPI_VIAGGIO), format_func=lambda k: fl.TIPI_VIAGGIO[k], label_visibility="collapsed")

st.sidebar.subheader("🚫 Esclusioni")
escludi_italia = st.sidebar.checkbox("Escludi città/aeroporti italiani", value=True)
escludi_visitate = st.sidebar.checkbox("Escludi città già visitate", value=True,
                                       help=f"Esclude: {fl.NOMI_VISITATE_STR}")
solo_stesso_aeroporto = st.sidebar.checkbox("Forza stesso aeroporto A/R (auto al parcheggio)", value=False)

st.sidebar.subheader("🗂️ Fonte dei dati")
modo = st.sidebar.radio("Fonte", [MODO_BOT, MODO_LIVE], label_visibility="collapsed")

mesi_avanti, max_chiamate = 4, 4
if modo == MODO_LIVE:
    mesi_avanti = st.sidebar.slider("Mesi oltre il mese corrente", min_value=1, max_value=12, value=4)
    max_chiamate = st.sidebar.slider("Chiamate SerpAPI per ricerca", min_value=2, max_value=30, value=4, step=2,
                                     help="Ogni chiamata consuma crediti SerpAPI. Ogni clic ne usa fino a questo numero.")

# --- QUOTA SERPAPI ---
st.sidebar.subheader("🔢 Ricerche SerpAPI")
conto = quota_serpapi(serpapi_key) if serpapi_key else None
if conto and conto.get("usate") is not None and conto.get("limite"):
    st.sidebar.progress(min(1.0, conto["usate"] / conto["limite"]),
                        text=f"{conto['usate']} / {conto['limite']} usate questo mese")
else:
    q = fl.carica_quota()
    if q["usate"]:
        st.sidebar.progress(min(1.0, q["usate"] / q["limite"]),
                            text=f"{q['usate']} / {q['limite']} usate dal bot questo mese")
    else:
        st.sidebar.caption("Nessun dato sul consumo del mese.")


# --- VISUALIZZAZIONE ---
def mostra(grezze, etichetta_fonte):
    filtrate = fl.filtra_offerte(grezze, budget_max, durata_max_ore, escludi_italia,
                                 escludi_visitate, solo_stesso_aeroporto, tipo_viaggio)
    if not filtrate:
        st.warning("Nessun volo con i filtri attuali. Prova ad alzare il budget o la durata massima, "
                   "cambiare tipologia di viaggio oppure a disattivare 'Escludi città già visitate'.")
        return

    st.success(f"Trovate {len(filtrate)} offerte estere! ({etichetta_fonte})")
    df = pd.DataFrame(filtrate)[
        ["citta", "dest", "prezzo", "dep", "ret", "tipo", "durata", "avviso_auto", "link"]
    ].rename(columns={
        "citta": "Città Destinazione", "dest": "Codice IATA", "prezzo": "Prezzo Totale A/R (€)",
        "dep": "Data Partenza", "ret": "Data Ritorno", "tipo": "Tipologia Viaggio",
        "durata": "Durata Volo", "avviso_auto": "Aeroporti A/R", "link": "Link Prenotazione",
    })
    config = {
        "Link Prenotazione": st.column_config.LinkColumn("Link Prenotazione",
                                                         display_text="✈️ Apri su Google Flights"),
        "Prezzo Totale A/R (€)": st.column_config.NumberColumn("Prezzo Totale A/R (€)", format="%.2f €"),
    }
    try:  # Streamlit recente
        st.dataframe(df, column_config=config, width="stretch", hide_index=True)
    except (TypeError, ValueError):  # Streamlit più vecchio
        st.dataframe(df, column_config=config, use_container_width=True, hide_index=True)

    if st.button("📩 Invia questa lista su Telegram"):
        token, chat = secret("TELEGRAM_BOT_TOKEN"), secret("TELEGRAM_CHAT_ID")
        if not token or not chat:
            st.warning("Telegram non configurato: controlla i Secrets di Streamlit.")
        else:
            msg = fl.formatta_messaggio("✈️ OFFERTE VOLI DA ROMA (da Streamlit)", filtrate[:25], int(budget_max))
            if fl.invia_telegram(token, chat, msg):
                st.info("📩 Lista inviata su Telegram!")
            else:
                st.warning("Invio Telegram fallito.")


if modo == MODO_BOT:
    archivio = fl.carica_archivio()
    if not archivio["offerte"]:
        st.info("Il bot non ha ancora salvato nessun risultato. Si aggiorna una volta al giorno: "
                "puoi lanciarlo subito da GitHub → Actions → «Controllo Voli Giornaliero» → Run workflow, "
                "oppure usare la ricerca live dalla barra laterale.")
    else:
        quando = fl.formatta_aggiornamento(archivio.get("aggiornato"))
        st.caption(f"Ultimo aggiornamento del bot: {quando or 'n.d.'} · {len(archivio['offerte'])} offerte in archivio. "
                   "Ogni giorno il bot controlla alcune date a rotazione: l'archivio si completa col tempo.")
        mostra(fl.offerte_da_archivio(archivio), "dall'archivio del bot")
else:
    if not serpapi_key:
        st.info("🧪 Nessuna `SERPAPI_KEY` nei Secrets: la ricerca live mostra solo dati dimostrativi. "
                "Aggiungila in Streamlit → Settings → Secrets per la ricerca reale.")

    if st.button("🔍 Cerca Offerte Aggiornate"):
        with st.spinner("Scansione offerte estere da Fiumicino e Ciampino..."):
            if serpapi_key:
                grezze, chiamate, errori = fl.cerca_offerte(
                    serpapi_key, mesi=mesi_avanti, max_chiamate=max_chiamate,
                    tipo_viaggio=tipo_viaggio, log=lambda *_: None)
                quota_serpapi.clear()
            else:
                grezze, chiamate, errori = fl.dati_dimostrativi(), 0, []
        # I risultati restano in memoria: muovere gli slider rifiltra senza rifare chiamate a pagamento
        st.session_state["live"] = {"offerte": grezze, "chiamate": chiamate, "errori": errori,
                                    "demo": not serpapi_key}

    live = st.session_state.get("live")
    if live:
        if live["demo"]:
            st.caption("Dati dimostrativi.")
        else:
            st.caption(f"Chiamate SerpAPI usate: {live['chiamate']} · destinazioni lette: {len(live['offerte'])}")
        for e in live["errori"]:
            st.warning(f"Chiamata fallita: {e}")
        mostra(live["offerte"], "ricerca live" if not live["demo"] else "dati dimostrativi")
