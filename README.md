# ✈️ Voli convenienti da Roma

Cerca voli low-cost **esteri** da Fiumicino (FCO) e Ciampino (CIA) per weekend e ponti, esclude le città già visitate e ti avvisa su Telegram.

## Come funziona
- `bot_scheduler.py` – gira ogni giorno su GitHub Actions. Cerca alcune date a rotazione (ponti e weekend), manda su Telegram solo le offerte **nuove** o scese di almeno il 10% e salva i risultati nel repository.
- `app.py` – interfaccia Streamlit. Di default mostra gli **ultimi risultati del bot senza consumare crediti**; la "ricerca live" è opzionale e usa crediti SerpAPI.
- `flight_logic.py` – logica condivisa (date, festivi, ricerca SerpAPI, filtri, Telegram, quota).
- File salvati dal workflow: `stato_notifiche.json` (offerte già inviate), `ultimi_risultati.json` (letto dall'app), `quota_serpapi.json` (contatore del mese).

## Secrets necessari
GitHub → Settings → Secrets and variables → Actions: `SERPAPI_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
Per la ricerca live e il pulsante Telegram dell'app, gli stessi nomi vanno nei Secrets di Streamlit.

## Impostazioni (nel workflow `.github/workflows/check_flights.yml`)
| Variabile | Default | Significato |
|---|---|---|
| `BUDGET_MAX` | 160 | prezzo massimo A/R in € |
| `DURATA_MAX_ORE` | 2.5 | durata massima del volo |
| `MESI_AVANTI` | 4 | mese corrente + N mesi |
| `MAX_CHIAMATE` | 4 | ricerche SerpAPI per esecuzione |
| `TIPO_VIAGGIO` | tutte | `tutte`, `weekend` o `ponti` |
| `LIMITE_MENSILE` | 230 | tetto di ricerche SerpAPI al mese |

## Consumo SerpAPI
Il piano gratuito ha 250 ricerche al mese. Con 4 chiamate al giorno il bot ne usa circa 120; il tetto `LIMITE_MENSILE` lascia un margine per le ricerche manuali dall'app. Il bot legge i consumi reali dall'account SerpAPI (la lettura è gratuita). Se i consumi si avvicinano al tetto, o il tetto viene raggiunto, ricevi un avviso su Telegram e il bot si ferma fino al mese successivo.

## Avvisi di errore
Se il controllo giornaliero fallisce (chiave errata, quota finita, formato dei dati cambiato) ricevi un messaggio su Telegram con il motivo. Chiavi e token vengono nascosti dai messaggi.

## Prova locale
```
pip install -r requirements.txt
python bot_scheduler.py --demo      # dati finti, non invia nulla e non salva nulla
python bot_scheduler.py --dry-run   # ricerca reale (serve SERPAPI_KEY), ma niente Telegram e niente file salvati
streamlit run app.py
```
