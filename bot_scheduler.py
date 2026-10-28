import streamlit as st
import pandas as pd
from datetime import date, timedelta
import calendar
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
st.caption("Cerca weekend lunghi, ponti e offerte low-cost ESTERE in partenza da Roma (Visibilità: Mese corrente + 7 mesi).")

# --- SIDEBAR: PARAMETRI E FILTRI ---
st.sidebar.header("⚙️ Filtri di Ricerca")

# Budget: min 20€, max 400€, default standard a 120€
budget_max = st.sidebar.slider("Budget Massimo A/R (€)", min_value=20, max_value=400, value=120, step=5)

# Durata Max Volo (Default 2.5 ore)
durata_max_ore = st.sidebar.slider("Durata Max Volo (ore)", min_value=1.0, max_value=6.0, value=2.5, step=0.5)

st.sidebar.subheader("🚫 Esclusioni & Parcheggio")
escludi_italia = st.sidebar.checkbox("Escludi città/aeroporti italiani", value=True, help="Mostra solo destinazioni estere.")
escludi_visitate = st.sidebar.checkbox("Escludi città già visitate", value=True, help=f"Esclude: {NOMI_VISITATE_STR}")
solo_stesso_aeroporto = st.sidebar.checkbox("Forza stesso aeroporto A/R (Auto al parcheggio)", value=False,
                                            help="Evita combinazioni in cui parti da Fiumicino e torni a Ciampino (o viceversa).")

invia_telegram_da_web = st.sidebar.checkbox("Invia report su Telegram al click", value=True)

st.sidebar.subheader("📅 Orizzonte Temporale")
mesi_avanti = st.sidebar.slider("Mesi di scansione in avanti", min_value=1, max_value=12, value=7)

# --- FUNZIONE PER GENERARE LINK GOOGLE FLIGHTS ---
def genera_link_google_flights(dep_iata, dest_iata, dep_date, ret_date):
    return f"https://www.google.com/travel/flights?q=Flights%20to%20{dest_iata}%20from%20{dep_iata}%20on%20{dep_date}%20through%20{ret_date}"

# --- CALCOLO DINAMICO WEEKEND E PONTI FINO A MESE CORRENTE + N MESI ---
def calcola_date_estese(mesi=7):
    coppie_date = []
    oggi = date.today()
    # Calcola il limite massimo in base ai mesi selezionati (circa 30 giorni per mese)
    giorni_totali = mesi * 30
    
    # Elenco festività nazionali di riferimento (Anno corrente + successivo)
    festivi = [
        date(2026, 11, 1), date(2026, 12, 8), date(2026, 12, 25), date(2026, 12, 26),
        date(2027, 1, 1), date(2027, 1, 6), date(2027, 3, 28), date(2027, 3, 29), # Pasqua/Pasquetta 2027
        date(2027, 4, 25), date(2027, 5, 1), date(2027, 6, 2), date(2027, 8, 15), date(2027, 11, 1), date(2027, 12, 8)
    ]
    
    for i in range(giorni_totali):
        giorno = oggi + timedelta(days=i)
        dow = giorno.weekday() # 0 = Lun, 1 = Mar, ..., 4 = Ven, 5 = Sab, 6 = Dom
        
        # 1. Weekend Standard: Venerdì - Domenica / Sabato - Domenica / Sabato - Lunedì
        if dow == 4: # Venerdì
            coppie_date.append({"dep": giorno.strftime("%Y-%m-%d"), "ret": (giorno + timedelta(days=2)).strftime("%Y-%m-%d"), "tipo": "Weekend (Ven-Dom)"})
            coppie_date.append({"dep": giorno.strftime("%Y-%m-%d"), "ret": (giorno + timedelta(days=3)).strftime("%Y-%m-%d"), "tipo": "Weekend Lungo (Ven-Lun)"})
        elif dow == 5: # Sabato
            coppie_date.append({"dep": giorno.strftime("%Y-%m-%d"), "ret": (giorno + timedelta(days=1)).strftime("%Y-%m-%d"), "tipo": "Weekend (Sab-Dom)"})
            coppie_date.append({"dep": giorno.strftime("%Y-%m-%d"), "ret": (giorno + timedelta(days=2)).strftime("%Y-%m-%d"), "tipo": "Weekend (Sab-Lun)"})

        # 2. Ponti Allungati (Festivo di Giovedì -> Ferie Venerdì -> Sab-Dom)
        if giorno in festivi and dow == 3:
            coppie_date.append({"dep": giorno.strftime("%Y-%m-%d"), "ret": (giorno + timedelta(days=3)).strftime("%Y-%m-%d"), "tipo": "Ponte (Gio-Dom | Ferie Ven)"})

        # 3. Ponti Allungati (Festivo di Martedì -> Ferie Lunedì -> Sab-Dom-Lun-Mar)
        if (giorno + timedelta(days=3)) in festivi and dow == 5:
            coppie_date.append({"dep": giorno.strftime("%Y-%m-%d"), "ret": (giorno + timedelta(days=3)).strftime("%Y-%m-%d"), "tipo": "Ponte (Sab-Mar | Ferie Lun)"})

    return coppie_date

# --- NOTIFICA TELEGRAM ---
def invia_telegram(testo):
    try:
        bot_token = st.secrets["TELEGRAM_BOT_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": testo, "parse_mode": "Markdown"}
        requests.post(url, json=payload)
    except Exception as e:
        st.warning(f"Errore invio Telegram: {e}")

# --- RICERCA ESTESA ---
if st.button("🔍 Cerca Offerte Aggiornate (Mese Corrente + 7 Mesi)"):
    with st.spinner(f"Scansione in corso sui prossimi {mesi_avanti} mesi per Fiumicino e Ciampino..."):
        
        # Genera tutte le date ideali per i prossimi 7 mesi
        date_target = calcola_date_estese(mesi=mesi_avanti)
        
        # Generatore di catalogo voli esteso su più mesi
        # (Quando avrai collegato la SerpApi Key live, scansionerà tutte le date generate da calcola_date_estese)
        lista_offerte = [
            # Novembre 2026
            {"citta": "Porto", "dest": "OPO", "dep": "2026-11-13", "ret": "2026-11-15", "prezzo": 132.0, "dep_apt": "FCO", "ret_apt": "FCO", "durata": "1h 25m", "tipo": "Weekend (Ven-Dom)"},
            {"citta": "Parigi (Orly)", "dest": "ORY", "dep": "2026-11-27", "ret": "2026-11-29", "prezzo": 118.0, "dep_apt": "FCO", "ret_apt": "FCO", "durata": "2h 05m", "tipo": "Weekend (Ven-Dom)"},
            # Dicembre 2026
            {"citta": "Berlino", "dest": "BER", "dep": "2026-12-05", "ret": "2026-12-08", "prezzo": 98.0, "dep_apt": "FCO", "ret_apt": "FCO", "durata": "2h 15m", "tipo": "Ponte 8 Dic (Sab-Mar | Ferie Lun)"},
            {"citta": "Praga", "dest": "PRG", "dep": "2026-12-18", "ret": "2026-12-20", "prezzo": 110.0, "dep_apt": "CIA", "ret_apt": "CIA", "durata": "1h 50m", "tipo": "Weekend (Ven-Dom)"},
            # Gennaio 2027
            {"citta": "Siviglia", "dest": "SVQ", "dep": "2027-01-15", "ret": "2027-01-17", "prezzo": 75.0, "dep_apt": "FCO", "ret_apt": "FCO", "durata": "2h 30m", "tipo": "Weekend (Ven-Dom)"},
            # Febbraio 2027
            {"citta": "Budapest", "dest": "BUD", "dep": "2027-02-12", "ret": "2027-02-14", "prezzo": 85.0, "dep_apt": "CIA", "ret_apt": "CIA", "durata": "1h 45m", "tipo": "Weekend San Valentino (Ven-Dom)"},
            # Marzo 2027
            {"citta": "Malta", "dest": "MLA", "dep": "2027-03-26", "ret": "2027-03-29", "prezzo": 65.0, "dep_apt": "FCO", "ret_apt": "FCO", "durata": "1h 25m", "tipo": "Ponte Pasqua (Ven-Lun)"},
            # Aprile 2027
            {"citta": "Vienna", "dest": "VIE", "dep": "2027-04-23", "ret": "2027-04-26", "prezzo": 115.0, "dep_apt": "FCO", "ret_apt": "FCO", "durata": "1h 35m", "tipo": "Ponte 25 Aprile (Ven-Lun)"},
            # Maggio 2027
            {"citta": "Marsiglia", "dest": "MRS", "dep": "2027-05-14", "ret": "2027-05-16", "prezzo": 55.0, "dep_apt": "CIA", "ret_apt": "CIA", "durata": "1h 30m", "tipo": "Weekend (Ven-Dom)"}
        ]

        filtrati = []
        for f in lista_offerte:
            # Genera il link Google Flights dinamico per ciascuna offerta
            f["link"] = genera_link_google_flights(f["dep_apt"], f["dest"], f["dep"], f["ret"])
            
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
                
            if f["dep_apt"] == f["ret_apt"]:
                f["avviso_auto"] = f"🟢 Stesso Aeroporto ({f['dep_apt']})"
            else:
                f["avviso_auto"] = f"🟡 Cross-Airport ({f['dep_apt']} ➡️ {f['ret_apt']})"
                
            filtrati.append(f)
            
        df = pd.DataFrame(filtrati)
        
        if df.empty:
            st.warning("Nessun volo trovato con i filtri attuali. Prova ad alzare il budget.")
        else:
            st.success(f"Trovate {len(df)} offerte estere nei prossimi {mesi_avanti} mesi!")
            
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
            
            if invia_telegram_da_web and not df.empty:
                msg = f"✈️ *RICERCA VOLI DA STREAMLIT ({mesi_avanti} MESI)*\nTrovate {len(df)} offerte estero (Budget max: {budget_max}€):\n\n"
                for _, row in df.iterrows():
                    msg += f"• *{row['citta']}* ({row['dest']}) - {row['prezzo']}€\n"
                    msg += f"  📅 {row['dep']} ➡️ {row['ret']} ({row['tipo']})\n"
                    msg += f"  🔗 [Prenota su Google Flights]({row['link']})\n\n"
                invia_telegram(msg)
                st.info("📩 Report inviato anche su Telegram!")
