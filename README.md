# ✈️ Voli convenienti da Roma

Cerca voli low-cost **esteri** da Fiumicino (FCO) e Ciampino (CIA) per weekend e ponti, esclude le città già visitate e ti avvisa su Telegram.

## Come funziona
- `app.py` – interfaccia Streamlit: scegli i filtri e premi "Cerca".
- `bot_scheduler.py` – bot automatico lanciato da GitHub Actions due volte al giorno. Manda su Telegram solo le offerte **nuove** o scese di prezzo di almeno il 10%.
- `flight_logic.py` – logica condivisa (date, ricerca SerpAPI, filtri, Telegram).
- `stato_notifiche.json` – memoria delle offerte già inviate (la salva il workflow).

## Secrets necessari
GitHub → Settings → Secrets and variables → Actions: `SERPAPI_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
Per l'app Streamlit gli stessi nomi vanno nei Secrets di Streamlit.

## Consumo SerpAPI
Il bot gira una volta al giorno e usa al massimo `MAX_CHIAMATE` chiamate (default 4) → circa 120 ricerche al mese,
dentro le 250 del piano gratuito SerpAPI (resta margine per i clic sull'app Streamlit, che consumano chiamate anch'essi).
L'orizzonte è il mese corrente + `MESI_AVANTI` mesi (default 4). Le date ruotano a ogni esecuzione.

## Prova locale
```
pip install -r requirements.txt
python bot_scheduler.py --demo --dry-run
```
