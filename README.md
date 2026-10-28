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
Ogni esecuzione usa al massimo `MAX_CHIAMATE` chiamate (default 10) → fino a 20 chiamate al giorno.
Il piano gratuito SerpAPI ha poche ricerche al mese: abbassa `MAX_CHIAMATE` nel workflow o riduci la frequenza del cron se serve.

## Prova locale
```
pip install -r requirements.txt
python bot_scheduler.py --demo --dry-run
```
