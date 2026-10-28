import streamlit as st
import pandas as pd
from datetime import date, timedelta
import requests
import database

database.init_db()

st.set_page_config(page_title="Flight Finder Roma", page_icon="✈️", layout="wide")

# Lista città già visitate da Davide
CITTA_VISITATE = ["LIS", "MAD", "VLC", "VIE", "AGP", "WAW", "OTP", "ATH", "RHO", "GPA", "BRU", "CRL", "SOF"]
# Mappa IATA indicativa per l'interruttore
NOMI_CITTA = "Lisbona, Madrid, Valencia, Vienna, Malaga, Varsavia, Bucarest, Atene, Rodi, Patrasso, Bruxelles, Sofia"

st.title("✈️ Personal Flight Finder da Roma (FCO / CIA)")
st.caption(f"Filtra e trova offerte per weekend e ponti estesi | Partenze da Fiumicino e Ciampino")

# --- SIDEBAR FILTRI ---
st.sidebar.header("⚙️ Parametri di Ricerca")
budget_max = st.sidebar.slider("Budget Massimo (€)", 20, 200, 65, step=5)
durata_max_ore = st.sidebar.slider("Durata Max Volo (ore)", 1.0, 4.0, 1.5, step=0.5)

st.sidebar.subheader("🚫 Esclusioni & Aeroporti")
escludi_visitate = st.sidebar.checkbox("Escludi città già visitate", value=True, 
                                       help=f"Esclude: {NOMI_CITTA}")

solo_stesso_aeroporto = st.sidebar.checkbox("Forza stesso aeroporto A/R (Auto al parcheggio)", value=False)

st.sidebar.subheader("📅 Tipologia di Viaggio")
opzione_date = st.sidebar.radio("Seleziona Combinazione:", [
    "Tutte le opzioni",
    "Weekend Standard (Ven-Dom / Sab-Dom)",
    "Ponti & Ponti Allungati (Festivi + Ferie)"
])

# --- FUNZIONE LOGICA PONTI E WEEKEND (2026/2027) ---
def calcola_fine_settimana_e_ponti():
    date_coppie = []
    oggi = date.today()
    
    # Esempio festivi italiani fissi
    festivi = [
        date(2026, 11, 1), date(2026, 12, 8), date(2026, 12, 25), date(2026, 12, 26),
        date(2027, 1, 1), date(2027, 1, 6), date(2027, 4, 25), date(2027, 5, 1), date(2027, 6, 2)
    ]
    
    # Scansiona i prossimi 90 giorni
    for i in range(90):
        giorno = oggi + timedelta(days=i)
        dow = giorno.weekday() # 0 = Lun, 1 = Mar, ... 3 = Gio, 4 = Ven, 5 = Sab, 6 = Dom
        
        # 1. Weekend Standard
        if dow == 4: # Venerdì
            date_coppie.append((giorno, giorno + timedelta(days=2), "Ven-Dom"))
            date_coppie.append((giorno, giorno + timedelta(days=3), "Ven-Lun"))
        if dow == 5: # Sabato
            date_coppie.append((giorno, giorno + timedelta(days=1), "Sab-Dom"))
            date_coppie.append((giorno, giorno + timedelta(days=2), "Sab-Lun"))
            
        # 2. Ponti Allungati (Festivo di Martedì -> Ferie di Lunedì | Sab-Dom-Lun-Mar)
        if (giorno + timedelta(days=3)) in festivi and dow == 5:
            date_coppie.append((giorno, giorno + timedelta(days=3), "Ponte Allungato (Sab-Mar | Ferie Lun)"))
            
        # 3. Ponti Allungati (Festivo di Giovedì -> Ferie di Venerdì | Gio-Ven-Sab-Dom)
        if giorno in festivi and dow == 3:
            date_coppie.append((giorno, giorno + timedelta(days=3), "Ponte Allungato (Gio-Dom | Ferie Ven)"))
            
    return date_coppie

# API Wrapper (Mockup strutturato per SerpApi / Google Flights)
def cerca_offerte_volo(budget, escludi_citta, solo_stesso_apt):
    # Qui inserisci la tua chiamata a SerpApi o API alternativa
    # Ritorna una struttura simulata di esempio aderente ai filtri
    risultati_mock = [
        {"dest": "OPO", "citta": "Porto", "dep": "2026-11-13", "ret": "2026-11-15", "prezzo": 42.0, "dep_apt": "FCO", "ret_apt": "FCO", "durata": "1h 25m", "tipo": "Ven-Dom"},
        {"dest": "MAD", "citta": "Madrid", "dep": "2026-11-20", "ret": "2026-11-22", "prezzo": 38.0, "dep_apt": "CIA", "ret_apt": "FCO", "durata": "2h 10m", "tipo": "Ven-Dom"},
        {"dest": "TRS", "citta": "Trieste", "dep": "2026-12-05", "ret": "2026-12-08", "prezzo": 55.0, "dep_apt": "FCO", "ret_apt": "FCO", "durata": "1h 05m", "tipo": "Ponte Allungato (Sab-Mar)"}
    ]
    
    filtrati = []
    for f in risultati_mock:
        if f["prezzo"] > budget:
            continue
        if escludi_citta and f["dest"] in CITTA_VISITATE:
            continue
        if solo_stesso_apt and f["dep_apt"] != f["ret_apt"]:
            continue
        
        # Etichetta Aeroporto per l'auto
        if f["dep_apt"] == f["ret_apt"]:
            f["avviso_auto"] = f"🟢 Stesso Aeroporto ({f['dep_apt']})"
        else:
            f["avviso_auto"] = f"🟡 CROSS-AIRPORT ({f['dep_apt']} ➡️ {f['ret_apt']})"
            
        filtrati.append(f)
        
    return pd.DataFrame(filtrati)

# --- BOTTONE RICERCA STREAMLIT ---
if st.button("🔍 Cerca Voli Low-Cost"):
    with st.spinner("Scansione in corso su Fiumicino e Ciampino..."):
        df = cerca_offerte_volo(budget_max, escludi_visitate, solo_stesso_aeroporto)
        
        if df.empty:
            st.warning("Nessun volo trovato con i filtri selezionati.")
        else:
            st.subheader(f"Trovate {len(df)} offerte trasparenti:")
            st.dataframe(
                df[["citta", "dest", "prezzo", "dep", "ret", "tipo", "durata", "avviso_auto"]],
                use_container_width=True
            )