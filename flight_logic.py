"""Logica condivisa tra l'app Streamlit (app.py) e il bot automatico (bot_scheduler.py).

Niente import di streamlit qui dentro: deve funzionare anche in GitHub Actions.
"""
import html
import json
import os
import re
import time
from datetime import date, datetime, timedelta
from urllib.parse import quote

import requests

SERPAPI_URL = "https://serpapi.com/search.json"
AEROPORTI_PARTENZA = ["FCO", "CIA"]

# Città già visitate (codici IATA) e nomi (minuscoli, IT + EN) per il confronto sul nome
CITTA_VISITATE = ["LIS", "MAD", "VLC", "VIE", "AGP", "WAW", "OTP", "ATH", "RHO", "GPA", "BRU", "CRL", "SOF"]
NOMI_VISITATE_STR = "Lisbona, Madrid, Valencia, Vienna, Malaga, Varsavia, Bucarest, Atene, Rodi, Patrasso, Bruxelles, Charleroi, Sofia"
NOMI_VISITATE = [
    "lisbona", "lisbon", "madrid", "valencia", "vienna", "wien", "malaga", "málaga",
    "varsavia", "warsaw", "bucarest", "bucharest", "atene", "athens", "rodi", "rhodes",
    "patrasso", "patras", "bruxelles", "brussels", "charleroi", "sofia",
]

# Aeroporti italiani (FCO/CIA sono le partenze, non destinazioni, ma li teniamo per sicurezza)
AEROPORTI_ITALIANI = [
    "FCO", "CIA", "MXP", "LIN", "BGY", "VCE", "TSF", "NAP", "BLQ",
    "PMO", "CTA", "TRN", "GOA", "FLR", "PSA", "BRI", "SUF", "CAG",
    "VRN", "TRS", "AOI", "PEG", "PSR", "LMP", "PNL", "TPS", "CIY", "QSR",
    "OLB", "REG", "BDS", "TAR", "RMI", "BZO", "CUF", "AHO", "EBA", "PNL",
]
PAESI_ITALIA = {"italy", "italia"}


# ----------------------------------------------------------------------------
# Date: weekend e ponti
# ----------------------------------------------------------------------------
def _pasqua(anno):
    """Domenica di Pasqua (algoritmo gregoriano anonimo)."""
    a = anno % 19
    b, c = divmod(anno, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese, giorno = divmod(h + l - 7 * m + 114, 31)
    return date(anno, mese, giorno + 1)


def festivi_italiani(anno):
    """Festivi nazionali + patrono di Roma (29 giugno, Santi Pietro e Paolo)."""
    pasqua = _pasqua(anno)
    return {
        date(anno, 1, 1), date(anno, 1, 6), date(anno, 4, 25), date(anno, 5, 1),
        date(anno, 6, 2), date(anno, 6, 29), date(anno, 8, 15), date(anno, 11, 1), date(anno, 12, 8),
        date(anno, 12, 25), date(anno, 12, 26),
        pasqua, pasqua + timedelta(days=1),
    }


def fine_orizzonte(oggi, mesi):
    """Ultimo giorno del mese corrente + `mesi` mesi (mesi=4 da ottobre -> 28 febbraio)."""
    indice = oggi.year * 12 + (oggi.month - 1) + mesi
    anno, mese = divmod(indice, 12)
    mese += 1
    primo_successivo = date(anno + (mese == 12), mese % 12 + 1, 1)
    return primo_successivo - timedelta(days=1)


def calcola_date_estese(mesi=4, oggi=None):
    """Coppie (andata, ritorno) per weekend e ponti dal giorno corrente
    fino a fine del mese corrente + `mesi` mesi."""
    oggi = oggi or date.today()
    fine = fine_orizzonte(oggi, mesi)
    festivi = festivi_italiani(oggi.year) | festivi_italiani(oggi.year + 1)
    coppie = {}

    def aggiungi(dep, ret, tipo):
        chiave = (dep, ret)
        # un ponte ha priorità sull'etichetta "weekend" generica
        if chiave not in coppie or tipo.startswith("Ponte"):
            coppie[chiave] = tipo

    for i in range((fine - oggi).days + 1):
        g = oggi + timedelta(days=i)
        dow = g.weekday()  # 0 = lun ... 6 = dom

        if dow == 4:  # venerdì
            aggiungi(g, g + timedelta(days=2), "Weekend (Ven-Dom)")
            aggiungi(g, g + timedelta(days=3), "Weekend lungo (Ven-Lun)")
        elif dow == 5:  # sabato
            aggiungi(g, g + timedelta(days=1), "Weekend (Sab-Dom)")
            aggiungi(g, g + timedelta(days=2), "Weekend (Sab-Lun)")

        # Festivo di giovedì -> ferie venerdì -> ritorno domenica
        if g in festivi and dow == 3:
            aggiungi(g, g + timedelta(days=3), "Ponte (Gio-Dom | ferie Ven)")
        # Festivo di venerdì (weekend lungo "gratis")
        if g in festivi and dow == 4:
            aggiungi(g, g + timedelta(days=2), "Ponte (Ven festivo)")
        # Festivo di martedì -> ferie lunedì -> sabato-martedì
        if g in festivi and dow == 1:
            aggiungi(g - timedelta(days=3), g, "Ponte (Sab-Mar | ferie Lun)")
        # Festivo di lunedì
        if g in festivi and dow == 0:
            aggiungi(g - timedelta(days=3), g, "Ponte (Ven-Lun festivo)")

    risultato = []
    for (dep, ret), tipo in sorted(coppie.items()):
        if oggi <= dep and ret <= fine:
            risultato.append({"dep": dep.isoformat(), "ret": ret.isoformat(), "tipo": tipo})
    return risultato


def seleziona_date(coppie, quante, adesso=None):
    """Sceglie `quante` coppie di date per questa esecuzione.

    Metà dei posti (arrotondata per eccesso) va ai ponti, il resto ai weekend; entrambe le liste
    ruotano a ogni esecuzione, così nel tempo si copre tutto l'orizzonte con poche chiamate API.
    """
    if quante <= 0 or not coppie:
        return []
    ponti = [c for c in coppie if c["tipo"].startswith("Ponte")]
    altre = [c for c in coppie if not c["tipo"].startswith("Ponte")]
    n_ponti = min(len(ponti), (quante + 1) // 2)
    n_altre = min(len(altre), quante - n_ponti)
    n_ponti = min(len(ponti), quante - n_altre)  # se mancano weekend, più ponti
    adesso = adesso or datetime.now()
    turno = adesso.toordinal() * 2 + (1 if adesso.hour >= 12 else 0)

    def ruota(lista, n):
        if n <= 0 or not lista:
            return []
        start = (turno * n) % len(lista)
        return [lista[(start + k) % len(lista)] for k in range(n)]

    return sorted(ruota(ponti, n_ponti) + ruota(altre, n_altre), key=lambda c: c["dep"])


# ----------------------------------------------------------------------------
# Link e utilità
# ----------------------------------------------------------------------------
def genera_link_google_flights(dep_iata, dest, dep_date, ret_date):
    q = f"Flights to {dest} from {dep_iata} on {dep_date} through {ret_date}"
    return "https://www.google.com/travel/flights?q=" + quote(q)


def _durata_minuti(valore):
    """Accetta minuti (int/float) o stringhe tipo '2 hr 5 min', '1h 25m'. None se ignota."""
    if valore is None:
        return None
    if isinstance(valore, (int, float)):
        return int(valore)
    testo = str(valore).lower()
    ore = re.search(r"(\d+)\s*(?:h|hr|ore|ora)", testo)
    minuti = re.search(r"(\d+)\s*(?:m|min)", testo)
    if not ore and not minuti:
        return int(testo) if testo.isdigit() else None
    return (int(ore.group(1)) if ore else 0) * 60 + (int(minuti.group(1)) if minuti else 0)


def formatta_durata(minuti):
    if minuti is None:
        return "n.d."
    return f"{minuti // 60}h {minuti % 60:02d}m"


# ----------------------------------------------------------------------------
# Ricerca reale con SerpAPI (Google Travel Explore: una chiamata = molte destinazioni)
# ----------------------------------------------------------------------------
def cerca_serpapi(api_key, dep_apt, dep, ret, tipo, timeout=40):
    params = {
        "engine": "google_travel_explore",
        "departure_id": dep_apt,
        "outbound_date": dep,
        "return_date": ret,
        "currency": "EUR",
        "hl": "it",
        "api_key": api_key,
    }
    r = requests.get(SERPAPI_URL, params=params, timeout=timeout)
    r.raise_for_status()
    dati = r.json()
    if dati.get("error"):
        raise RuntimeError(dati["error"])

    offerte = []
    for d in dati.get("destinations", []) or []:
        prezzo = d.get("flight_price", d.get("price"))
        if isinstance(prezzo, str):
            prezzo = float(re.sub(r"[^\d.]", "", prezzo.replace(",", ".")) or 0) or None
        if prezzo is None:
            continue
        aeroporto = d.get("destination_airport") or {}
        codice = (aeroporto.get("code") if isinstance(aeroporto, dict) else aeroporto) or ""
        nome = d.get("name") or codice
        offerte.append({
            "citta": nome,
            "dest": codice or nome,
            "paese": d.get("country") or "",
            "dep": d.get("start_date") or dep,
            "ret": d.get("end_date") or ret,
            "prezzo": float(prezzo),
            "dep_apt": dep_apt,
            "ret_apt": dep_apt,
            "durata_min": _durata_minuti(d.get("flight_duration")),
            "scali": d.get("number_of_stops"),
            "tipo": tipo,
            "link": genera_link_google_flights(dep_apt, codice or nome, d.get("start_date") or dep, d.get("end_date") or ret),
        })
    return offerte


def cerca_offerte(api_key, mesi=4, max_chiamate=4, aeroporti=None, pausa=1.0, log=print):
    """Scansiona le date selezionate su FCO/CIA. Ritorna (offerte, chiamate_fatte, errori)."""
    aeroporti = aeroporti or AEROPORTI_PARTENZA
    pairs_per_airport = max(1, max_chiamate // len(aeroporti))
    date_scelte = seleziona_date(calcola_date_estese(mesi), pairs_per_airport)
    offerte, chiamate, errori = [], 0, []
    for c in date_scelte:
        for apt in aeroporti:
            if chiamate >= max_chiamate:
                break
            try:
                trovate = cerca_serpapi(api_key, apt, c["dep"], c["ret"], c["tipo"])
                log(f"  {apt} {c['dep']}→{c['ret']} ({c['tipo']}): {len(trovate)} destinazioni")
                offerte.extend(trovate)
            except Exception as e:  # una chiamata fallita non deve fermare le altre
                errori.append(f"{apt} {c['dep']}→{c['ret']}: {e}")
                log(f"  ERRORE {apt} {c['dep']}→{c['ret']}: {e}")
            chiamate += 1
            time.sleep(pausa)
    return offerte, chiamate, errori


# ----------------------------------------------------------------------------
# Filtri
# ----------------------------------------------------------------------------
def filtra_offerte(offerte, budget_max, durata_max_ore=None, escludi_italia=True,
                   escludi_visitate=True, solo_stesso_aeroporto=False):
    risultato = []
    for f in offerte:
        if f["prezzo"] > budget_max:
            continue
        codice = str(f.get("dest", "")).upper()
        nome = str(f.get("citta", "")).lower()
        paese = str(f.get("paese", "")).lower()

        if escludi_italia and (codice in AEROPORTI_ITALIANI or paese in PAESI_ITALIA):
            continue
        if escludi_visitate and (codice in CITTA_VISITATE or any(n in nome for n in NOMI_VISITATE)):
            continue
        if solo_stesso_aeroporto and f["dep_apt"] != f["ret_apt"]:
            continue
        # Durata sconosciuta -> non scartiamo il volo
        if durata_max_ore is not None and f.get("durata_min") is not None \
                and f["durata_min"] > durata_max_ore * 60:
            continue

        f = dict(f)
        f["durata"] = formatta_durata(f.get("durata_min"))
        if f["dep_apt"] == f["ret_apt"]:
            f["avviso_auto"] = f"🟢 Stesso aeroporto ({f['dep_apt']})"
        else:
            f["avviso_auto"] = f"🟡 Cross-airport ({f['dep_apt']} ➡️ {f['ret_apt']})"
        risultato.append(f)

    # stessa destinazione+date da due aeroporti: tieni la più economica
    migliori = {}
    for f in risultato:
        chiave = (f["dest"], f["dep"], f["ret"])
        if chiave not in migliori or f["prezzo"] < migliori[chiave]["prezzo"]:
            migliori[chiave] = f
    return sorted(migliori.values(), key=lambda x: (x["prezzo"], x["dep"]))


# ----------------------------------------------------------------------------
# Telegram
# ----------------------------------------------------------------------------
def formatta_messaggio(titolo, offerte, budget_max):
    righe = [f"<b>{html.escape(titolo)}</b>", f"{len(offerte)} offerte estere (budget max {budget_max}€):", ""]
    for f in offerte:
        righe.append(f"• <b>{html.escape(f['citta'])}</b> ({html.escape(str(f['dest']))}) – {f['prezzo']:.0f}€")
        righe.append(f"  📅 {f['dep']} ➡️ {f['ret']} ({html.escape(f['tipo'])}) · {f['dep_apt']}")
        righe.append(f"  🔗 <a href=\"{html.escape(f['link'], quote=True)}\">Apri su Google Flights</a>")
        righe.append("")
    return "\n".join(righe)


def invia_telegram(bot_token, chat_id, testo):
    """Invia spezzando i messaggi oltre il limite di Telegram (4096). Ritorna True/False."""
    blocchi, corrente = [], ""
    for paragrafo in testo.split("\n\n"):
        if len(corrente) + len(paragrafo) + 2 > 3800 and corrente:
            blocchi.append(corrente)
            corrente = ""
        corrente += paragrafo + "\n\n"
    if corrente.strip():
        blocchi.append(corrente)

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    ok = True
    for b in blocchi:
        r = requests.post(url, json={
            "chat_id": chat_id, "text": b, "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=30)
        if not r.ok:
            ok = False
    return ok


# ----------------------------------------------------------------------------
# Memoria delle offerte già notificate (file JSON, committabile da GitHub Actions)
# ----------------------------------------------------------------------------
def _id_offerta(f):
    return f"{f['dep_apt']}-{f['dest']}-{f['dep']}-{f['ret']}"


def carica_stato(percorso):
    try:
        with open(percorso, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def salva_stato(percorso, stato, giorni_da_tenere=60):
    limite = (date.today() - timedelta(days=giorni_da_tenere)).isoformat()
    pulito = {k: v for k, v in stato.items() if v.get("dep", "") >= limite}
    with open(percorso, "w", encoding="utf-8") as fh:
        json.dump(pulito, fh, ensure_ascii=False, indent=1, sort_keys=True)


def solo_nuove(offerte, stato, calo_minimo=0.10):
    """Offerte mai notificate, oppure scese di almeno `calo_minimo` rispetto all'ultima notifica."""
    nuove = []
    for f in offerte:
        vecchio = stato.get(_id_offerta(f))
        if vecchio is None or f["prezzo"] <= vecchio["prezzo"] * (1 - calo_minimo):
            nuove.append(f)
    return nuove


def registra_notificate(offerte, stato):
    ora = datetime.now().isoformat(timespec="seconds")
    for f in offerte:
        stato[_id_offerta(f)] = {"prezzo": f["prezzo"], "dep": f["dep"], "notificata": ora}


# ----------------------------------------------------------------------------
# Dati dimostrativi (solo se manca la chiave SerpAPI o per i test)
# ----------------------------------------------------------------------------
def dati_dimostrativi():
    def o(citta, dest, dep, ret, prezzo, apt, dur, tipo, paese=""):
        return {"citta": citta, "dest": dest, "paese": paese, "dep": dep, "ret": ret, "prezzo": prezzo,
                "dep_apt": apt, "ret_apt": apt, "durata_min": dur, "tipo": tipo,
                "link": genera_link_google_flights(apt, dest, dep, ret)}
    return [
        o("Porto", "OPO", "2026-11-13", "2026-11-15", 132.0, "FCO", 205, "Weekend (Ven-Dom)", "Portugal"),
        o("Parigi", "ORY", "2026-11-27", "2026-11-29", 118.0, "FCO", 125, "Weekend (Ven-Dom)", "France"),
        o("Berlino", "BER", "2026-12-05", "2026-12-08", 98.0, "FCO", 135, "Ponte (Sab-Mar | ferie Lun)", "Germany"),
        o("Praga", "PRG", "2026-12-18", "2026-12-20", 110.0, "CIA", 110, "Weekend (Ven-Dom)", "Czechia"),
        o("Siviglia", "SVQ", "2027-01-15", "2027-01-17", 75.0, "FCO", 150, "Weekend (Ven-Dom)", "Spain"),
        o("Budapest", "BUD", "2027-02-12", "2027-02-14", 85.0, "CIA", 105, "Weekend (Ven-Dom)", "Hungary"),
        o("Malta", "MLA", "2027-03-26", "2027-03-29", 65.0, "FCO", 85, "Weekend lungo (Ven-Lun)", "Malta"),
        o("Vienna", "VIE", "2027-04-23", "2027-04-26", 115.0, "FCO", 95, "Weekend lungo (Ven-Lun)", "Austria"),
        o("Marsiglia", "MRS", "2027-05-14", "2027-05-16", 55.0, "CIA", 90, "Weekend (Ven-Dom)", "France"),
    ]
