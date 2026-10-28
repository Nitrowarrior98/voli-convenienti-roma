import sqlite3
from datetime import datetime

DB_NAME = "voli_roma.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS offerte_notificate (
            id TEXT PRIMARY KEY,
            destinazione TEXT,
            data_partenza TEXT,
            data_ritorno TEXT,
            prezzo REAL,
            aeroporto_andata TEXT,
            aeroporto_ritorno TEXT,
            data_notifica TEXT
        )
    ''')
    conn.commit()
    conn.close()

def offerta_gia_notificata(flight_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM offerte_notificate WHERE id = ?", (flight_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def salva_offerta(flight_id, dest, dep, ret, price, dep_apt, ret_apt):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO offerte_notificate 
        (id, destinazione, data_partenza, data_ritorno, prezzo, aeroporto_andata, aeroporto_ritorno, data_notifica)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (flight_id, dest, dep, ret, price, dep_apt, ret_apt, datetime.now().isoformat()))
    conn.commit()
    conn.close()