import pandas as pd
import streamlit as st

import flight_logic as fl

st.set_page_config(page_title="Flight Finder Roma", page_icon="✈️", layout="wide")

st.title("✈️ Personal Flight Finder da Roma (FCO / CIA)")
st.caption("Weekend lunghi, ponti e offerte low-cost ESTERE in partenza da Roma, con i tuoi filtri.")

# --- SIDEBAR: PARAMETRI E FILTRI ---
st.sidebar.header("⚙️ Filtri di Ricerca")
budget_max = st.sidebar.slider("Budget Massimo A/R (€)", min_value=20, max_value=400, value=160, step=5)
durata_max_ore = st.sidebar.slider("Durata Max Volo (ore)", min_value=1.0, max_value=6.0, value=2.5, step=0.5,
                                   help="Se Google non indica la durata, il volo non viene scartato.")

st.sidebar.subheader("🚫 Esclusioni")
escludi_italia = st.sidebar.checkbox("Escludi città/aeroporti italiani", value=True)
escludi_visitate = st.sidebar.checkbox("Escludi città già visitate", value=True,
                                       help=f"Esclude: {fl.NOMI_VISITATE_STR}")
solo_stesso_aeroporto = st.sidebar.checkbox("Forza stesso aeroporto A/R (auto al parcheggio)", value=False)

st.sidebar.subheader("📅 Orizzonte e consumo API")
mesi_avanti = st.sidebar.slider("Mesi oltre il mese corrente", min_value=1, max_value=12, value=4)
max_chiamate = st.sidebar.slider("Chiamate SerpAPI per ricerca", min_value=2, max_value=30, value=4, step=2,
                                 help="Ogni chiamata consuma crediti SerpAPI. Ogni clic ne usa fino a questo numero.")
invia_telegram_da_web = st.sidebar.checkbox("Invia report su Telegram al click", value=False)


def secret(nome):
    try:
        return st.secrets[nome]
    except Exception:
        return None


serpapi_key = secret("SERPAPI_KEY")
if not serpapi_key:
    st.info("🧪 Nessuna `SERPAPI_KEY` nei Secrets: vedrai solo dati dimostrativi. "
            "Aggiungila in Streamlit → Settings → Secrets per la ricerca reale.")

if st.button("🔍 Cerca Offerte Aggiornate"):
    errori = []
    with st.spinner("Scansione offerte estere da Fiumicino e Ciampino..."):
        if serpapi_key:
            grezze, chiamate, errori = fl.cerca_offerte(
                serpapi_key, mesi=mesi_avanti, max_chiamate=max_chiamate, log=lambda *_: None)
            st.caption(f"Chiamate SerpAPI usate: {chiamate} · destinazioni lette: {len(grezze)}")
        else:
            grezze = fl.dati_dimostrativi()

        filtrate = fl.filtra_offerte(grezze, budget_max, durata_max_ore, escludi_italia,
                                     escludi_visitate, solo_stesso_aeroporto)

    for e in errori:
        st.warning(f"Chiamata fallita: {e}")

    if not filtrate:
        st.warning("Nessun volo con i filtri attuali. Prova ad alzare il budget o la durata massima, "
                   "oppure a disattivare 'Escludi città già visitate'.")
    else:
        st.success(f"Trovate {len(filtrate)} offerte estere!")
        df = pd.DataFrame(filtrate)[
            ["citta", "dest", "prezzo", "dep", "ret", "tipo", "durata", "avviso_auto", "link"]
        ].rename(columns={
            "citta": "Città Destinazione", "dest": "Codice IATA", "prezzo": "Prezzo Totale A/R (€)",
            "dep": "Data Partenza", "ret": "Data Ritorno", "tipo": "Tipologia Viaggio",
            "durata": "Durata Volo", "avviso_auto": "Aeroporti A/R", "link": "Link Prenotazione",
        })
        st.dataframe(
            df,
            column_config={
                "Link Prenotazione": st.column_config.LinkColumn("Link Prenotazione",
                                                                 display_text="✈️ Apri su Google Flights"),
                "Prezzo Totale A/R (€)": st.column_config.NumberColumn("Prezzo Totale A/R (€)", format="%.2f €"),
            },
            use_container_width=True,
        )

        if invia_telegram_da_web:
            token, chat = secret("TELEGRAM_BOT_TOKEN"), secret("TELEGRAM_CHAT_ID")
            if not token or not chat:
                st.warning("Telegram non configurato: controlla i Secrets.")
            else:
                msg = fl.formatta_messaggio("✈️ RICERCA VOLI DA STREAMLIT", filtrate[:25], int(budget_max))
                if fl.invia_telegram(token, chat, msg):
                    st.info("📩 Report inviato anche su Telegram!")
                else:
                    st.warning("Invio Telegram fallito.")
