import streamlit as st
import pandas as pd
from datetime import date, timedelta
import requests
import database

# Inizializza il database locale SQLite
database.init_db()

st.set_page_config(page_title="Flight Finder Roma", page_icon="✈️", layout="wide")

# 1. Le tue 13 città già visitate (Codici IATA)
CITTA_VISITATE = ["LIS", "MAD", "VLC", "VIE", "AGP", "WAW", "OTP", "ATH", "RHO", "GPA", "BRU", "CRL", "SOF"]
NOMI_VISITATE_STR = "Lisbona, Madrid, Valencia, Vienna, Malaga, Varsavia, Bucarest, Atene, Rodi, Patrasso, Bruxelles, Charleroi, Sofia"

# 2. Aeroporti italiani principali da escludere
AEROPORTI_ITALIANI = [
    "FCO", "CIA", "MXP", "LIN", "BGY", "VCE", "TSF", "NAP", "BLQ", 
    "PMO", "CTA", "TRN", "GOA", "FLR", "PSA", "BRI", "SUF", "CAG", 
    "VRN", "TRS", "AOI", "PEG", "PSR", "LMP", "PNL", "TPS", "CIY", "QSR"
]

st.title("✈️ Personal Flight Finder da Roma (FCO / CIA)")
st.caption("Cerca weekend lunghi, ponti e offerte low-cost ESTERE in partenza da Roma con filtri personalizzati.")

# --- SIDEBAR: PARAMETRI E FILTRI ---
st.sidebar.header("⚙️ Filtri di Ricerca")

# Budget: min 20€, max 400€, default standard impostato a 120€
budget_max = st.sidebar.slider("Budget Massimo A/R (€)", min_value=20, max_value=400, value=120, step=5)

# Durata Max Volo (Default 2.5 ore)
durata_max_ore = st.sidebar.slider("Durata Max Volo (ore)", min_value=1.0, max_value=6.0, value=2.5, step=0.5)

st.sidebar.subheader("🚫 Esclusioni & Parcheggio")
escludi_italia = st.sidebar.checkbox("Escludi città/aeroporti italiani", value=True, help="Mostra solo destinazioni estere.")
escludi_visitate = st.sidebar.checkbox("Escludi città già visitate", value=True, help=f"Esclude: {NOMI_VISITATE_STR}")
solo_stesso_aeroporto = st.sidebar.checkbox("Forza stesso aeroporto A/R (Auto al parcheggio)", value=False,
                                            help="Evita combinazioni in cui parti da Fiumicino e torni a Ciampino (o viceversa).")

invia_telegram_da_web = st.sidebar.checkbox("Invia report su Telegram al click", value=True,
                                           help="Invia anche la notifica su Telegram quando fai clic sul pulsante di ricerca.")

st.sidebar.subheader("📅 Tipologia di Viaggio")
tipo_viaggio = st.sidebar.selectbox("Formato Date:", [
    "Tutte le opzioni",
    "Weekend Standard (Ven-Dom / Sab-Dom / Sab-Lun)",
    "Ponti & Ponti Allungati (Festivi + Ferie)"
])

# --- FUNZIONE PER COSTRUIRE LINK GOOGLE FLIGHTS ---
def genera_link_google_flights(dep_iata, dest_iata, dep_date, ret_date):
    return f"https://www.google.com/travel/flights?q=Flights%20to%20{dest_iata}%20from%20{dep_iata}%20on%20{dep_date}%20through%20{ret_date}"

# --- FUNZIONE NOTIFICA TELEGRAM ---
def invia_telegram(testo):
    try:
        bot_token = st.secrets["TELEGRAM_BOT_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": testo, "parse_mode": "Markdown"}
        requests.post(url, json=payload)
    except Exception as e:
        st.warning(f"Errore invio Telegram (verifica i Secrets): {e}")

# --- DATI DIMOSTRATIVI AGGIORNATI CON FILTRI ---
def get_dati_dimostrativi():
    return [
        {
            "citta": "Porto", "dest": "OPO", "dep": "2026-11-13", "ret": "2026-11-15", 
            "prezzo": 132.0, "dep_apt": "FCO", "ret_apt": "FCO", "durata": "1h 25m", 
            "tipo": "Weekend Standard (Ven-Dom)",
            "link": genera_link_google_flights("FCO", "OPO", "2026-11-13", "2026-11-15")
        },
        {
            "citta": "Parigi (Orly)", "dest": "ORY", "dep": "2026-11-27", "ret": "2026-11-29", 
            "prezzo": 118.0, "dep_apt": "FCO", "ret_apt": "FCO", "durata": "2h 05m", 
            "tipo": "Weekend Standard (Ven-Dom)",
            "link": genera_link_google_flights("FCO", "ORY", "2026-11-27", "2026-11-29")
        },
        {
            "citta": "Trieste", "dest": "TRS", "dep": "2026-12-05", "ret": "2026-12-08", 
            "prezzo": 105.0, "dep_apt": "FCO", "ret_apt": "FCO", "durata": "1h 05m", 
            "tipo": "Ponte 8 Dic (Sab-Mar | Ferie Lun)",
            "link": genera_link_google_flights("FCO", "TRS", "2026-12-05", "2026-12-08")
        }
    ]

# --- ELABORAZIONE DATI AL CLICK ---
if st.button("🔍 Cerca Offerte Aggiornate"):
    with st.spinner("Scansione offerte estere da Fiumicino e Ciampino..."):
        
        lista_offerte = get_dati_dimostrativi()

        filtrati = []
        for f in lista_offerte:
            # 1. Filtro Budget Max
            if f["prezzo"] > budget_max:
                continue
            
            # 2. Filtro Esclusione Italia
            if escludi_italia and f["dest"] in AEROPORTI_ITALIANI:
                continue

            # 3. Filtro Città Visitate
            if escludi_visitate and f["dest"] in CITTA_VISITATE:
                continue
                
            # 4. Filtro Stesso Aeroporto (Parcheggio Auto)
            if solo_stesso_aeroporto and f["dep_apt"] != f["ret_apt"]:
                continue
                
            # Assegnazione etichetta visiva aeroporti
            if f["dep_apt"] == f["ret_apt"]:
                f["avviso_auto"] = f"🟢 Stesso Aeroporto ({f['dep_apt']})"
            else:
                f["avviso_auto"] = f"🟡 Cross-Airport ({f['dep_apt']} ➡️ {f['ret_apt']})"
                
            filtrati.append(f)
            
        df = pd.DataFrame(filtrati)
        
        if df.empty:
            st.warning("Nessun volo trovato con i filtri attuali. Prova ad alzare il budget o a cambiare i parametri.")
        else:
            st.success(f"Trovate {len(df)} offerte estere perfette per te!")
            
            # Rinominazione colonne interamente in italiano
            df_display = df[[
                "citta", "dest", "prezzo", "dep", "ret", "tipo", "durata", "avviso_auto", "link"
            ]].rename(columns={
                "citta": "Città Destinazione",
                "dest": "Codice IATA",
                "prezzo": "Prezzo Totale A/R (€)",
                "dep": "Data Partenza",
                "ret": "Data Ritorno",
                "tipo": "Tipologia Viaggio",
                "durata": "Durata Volo",
                "avviso_auto": "Aeroporti A/R",
                "link": "Link Prenotazione"
            })
            
            # Visualizzazione tabella pulita con link cliccabili
            st.dataframe(
                df_display,
                column_config={
                    "Link Prenotazione": st.column_config.LinkColumn(
                        "Link Prenotazione", 
                        display_text="✈️ Apri su Google Flights"
                    ),
                    "Prezzo Totale A/R (€)": st.column_config.NumberColumn(
                        "Prezzo Totale A/R (€)",
                        format="%.2f €"
                    )
                },
                use_container_width=True
            )
            
            # Invio facoltativo del report su Telegram al click
            if invia_telegram_da_web and not df.empty:
                msg = f"✈️ *RICERCA VOLI DA STREAMLIT*\nTrovate {len(df)} offerte estere (Budget max: {budget_max}€):\n\n"
                for _, row in df.iterrows():
                    msg += f"• *{row['citta']}* ({row['dest']}) - {row['prezzo']}€\n"
                    msg += f"  📅 {row['dep']} ➡️ {row['ret']} ({row['tipo']})\n"
                    msg += f"  🔗 [Prenota su Google Flights]({row['link']})\n\n"
                invia_telegram(msg)
                st.info("📩 Report inviato anche su Telegram!")
