import os
import requests
import database
import pandas as pd
from datetime import datetime

# Recupera i token in sicurezza dalle variabili d'ambiente di GitHub Actions
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Le tue 13 città già visitate (Codici IATA) da escludere
CITTA_VISITATE = ["LIS", "MAD", "VLC", "VIE", "AGP", "WAW", "OTP", "ATH", "RHO", "GPA", "BRU", "CRL", "SOF"]

def invia_messaggio_telegram(testo):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Token o Chat ID di Telegram mancanti nelle variabili d'ambiente.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": testo,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

def genera_link_google_flights(dep_iata, dest_iata, dep_date, ret_date):
    return f"https://www.google.com/travel/flights?q=Flights%20to%20{dest_iata}%20from%20{dep_iata}%20on%20{dep_date}%20through%20{ret_date}"

def esegui_controllo_automatico():
    database.init_db()
    
    # Dati di simulazione / controllo (qui puoi collegare la chiamata reale alle API di SerpApi)
    offerte_trovate = [
        {
            "id": "OPO_20261113", "citta": "Porto", "code": "OPO", 
            "dep": "2026-11-13", "ret": "2026-11-15", "prezzo": 42.0, 
            "dep_apt": "FCO", "ret_apt": "FCO", "tipo": "Weekend Standard (Ven-Dom)"
        },
        {
            "citta": "Trieste", "code": "TRS", 
            "dep": "2026-12-05", "ret": "2026-12-08", "prezzo": 115.0, 
            "dep_apt": "FCO", "ret_apt": "FCO", "tipo": "Ponte 8 Dic (Sab-Mar | Ferie Lun)"
        }
    ]
    
    nuove_offerte = []
    
    for o in offerte_trovate:
        # 1. Salta le città già visitate
        if o["code"] in CITTA_VISITATE:
            continue
            
        # 2. Controlla sul DB SQLite se ti è già arrivata questa notifica (evita doppioni)
        if not database.offerta_gia_notificata(o["id"]):
            nuove_offerte.append(o)
            # Salva subito nel DB che te l'abbiamo notificata
            database.salva_offerta(o["id"], o["code"], o["dep"], o["ret"], o["prezzo"], o["dep_apt"], o["ret_apt"])

    if not nuove_offerte:
        print("Nessuna nuova offerta trovata in questo controllo.")
        return

    # Componi un UNICO report raggruppato
    ora_attuale = datetime.now().strftime("%H:%M")
    messaggio = f"✈️ *REPORT VOLI LOW-COST DA ROMA* ({ora_attuale})\n"
    messaggio += f"Trovate {len(nuove_offerte)} nuove offerte imperdibili:\n\n"
    
    for idx, f in enumerate(nuove_offerte, 1):
        if f["dep_apt"] == f["ret_apt"]:
            tag_apt = f"🟢 Stesso Aeroporto ({f['dep_apt']})"
        else:
            tag_apt = f"🟡 Cross-Airport ({f['dep_apt']} ➡️ {f['ret_apt']})"
            
        link_volo = genera_link_google_flights(f["dep_apt"], f["code"], f["dep"], f["ret"])
        
        messaggio += (
            f"*{idx}. {f['citta']} ({f['code']})* — *{f['prezzo']} €*\n"
            f"📅 Andata: {f['dep']} | Ritorno: {f['ret']}\n"
            f"🎒 Tipo: {f['tipo']}\n"
            f"✈️ Aeroporti: {tag_apt}\n"
            f"🔗 [Prenota su Google Flights]({link_volo})\n\n"
        )
        
    invia_messaggio_telegram(messaggio)
    print("Report unico inviato con successo su Telegram!")

if __name__ == "__main__":
    esegui_controllo_automatico()
