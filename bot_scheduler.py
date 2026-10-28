"""Bot da riga di comando: cerca voli da Roma (FCO/CIA), filtra e avvisa su Telegram.

Eseguito da GitHub Actions (.github/workflows/check_flights.yml). Variabili d'ambiente:
  SERPAPI_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  (obbligatorie, salvo --dry-run/--demo)
  BUDGET_MAX (default 160), DURATA_MAX_ORE (default 2.5), MESI_AVANTI (default 7),
  MAX_CHIAMATE (default 10: chiamate SerpAPI per esecuzione)

Esempi:
  python bot_scheduler.py --demo --dry-run    # prova senza chiavi, stampa e basta
  python bot_scheduler.py --dry-run           # ricerca reale ma niente Telegram
"""
import argparse
import os
import sys

import flight_logic as fl

STATO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stato_notifiche.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="non invia su Telegram e non salva lo stato")
    ap.add_argument("--demo", action="store_true", help="usa dati dimostrativi invece di SerpAPI")
    args = ap.parse_args()

    budget = float(os.environ.get("BUDGET_MAX", 160))
    durata_max = float(os.environ.get("DURATA_MAX_ORE", 2.5))
    mesi = int(os.environ.get("MESI_AVANTI", 7))
    max_chiamate = int(os.environ.get("MAX_CHIAMATE", 10))

    if args.demo:
        offerte, errori = fl.dati_dimostrativi(), []
        print("Modalità demo: dati dimostrativi.")
    else:
        chiave = os.environ.get("SERPAPI_KEY")
        if not chiave:
            print("ERRORE: manca SERPAPI_KEY.", file=sys.stderr)
            return 1
        print(f"Ricerca reale: max {max_chiamate} chiamate, orizzonte {mesi} mesi.")
        offerte, chiamate, errori = fl.cerca_offerte(chiave, mesi=mesi, max_chiamate=max_chiamate)
        print(f"Chiamate SerpAPI usate: {chiamate}. Destinazioni grezze: {len(offerte)}.")
        if chiamate and len(errori) == chiamate:
            print("ERRORE: tutte le chiamate sono fallite (chiave errata o quota finita?).", file=sys.stderr)
            return 1

    filtrate = fl.filtra_offerte(offerte, budget, durata_max)
    print(f"Dopo i filtri (≤{budget:.0f}€, ≤{durata_max}h, solo estero, non visitate): {len(filtrate)}")

    stato = fl.carica_stato(STATO)
    nuove = fl.solo_nuove(filtrate, stato)
    print(f"Nuove o scese di prezzo rispetto all'ultima notifica: {len(nuove)}")
    if not nuove:
        print("Niente da notificare.")
        return 0

    messaggio = fl.formatta_messaggio("✈️ NUOVE OFFERTE VOLI DA ROMA", nuove[:25], int(budget))
    if args.dry_run:
        print("\n--- DRY RUN: messaggio che verrebbe inviato ---\n")
        print(messaggio)
        return 0

    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("ERRORE: mancano TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID.", file=sys.stderr)
        return 1
    if fl.invia_telegram(token, chat, messaggio):
        fl.registra_notificate(nuove[:25], stato)
        fl.salva_stato(STATO, stato)
        print("Notifica inviata.")
        return 0
    print("ERRORE: invio Telegram fallito (stato non aggiornato, riproverò al prossimo giro).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
