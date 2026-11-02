"""Bot da riga di comando: cerca voli da Roma (FCO/CIA), filtra e avvisa su Telegram.

Eseguito da GitHub Actions (.github/workflows/check_flights.yml). Variabili d'ambiente:
  SERPAPI_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  (obbligatorie, salvo --dry-run/--demo)
  BUDGET_MAX (default 160), DURATA_MAX_ORE (default 2.5), MESI_AVANTI (default 4: mese corrente + 4 mesi),
  MAX_CHIAMATE (default 4: chiamate SerpAPI per esecuzione),
  TIPO_VIAGGIO (tutte | weekend | ponti, default tutte),
  LIMITE_MENSILE (default 230: tetto di ricerche SerpAPI al mese, sotto le 250 del piano gratuito
                  per lasciare un margine alle ricerche manuali dall'app)

File salvati nel repository (li committa il workflow):
  stato_notifiche.json   offerte già notificate (niente doppioni)
  ultimi_risultati.json  ultime offerte viste, lette dall'app senza consumare crediti
  quota_serpapi.json     contatore ricerche del mese

Esempi:
  python bot_scheduler.py --demo --dry-run    # prova senza chiavi, stampa e basta
  python bot_scheduler.py --dry-run           # ricerca reale ma niente Telegram e niente file salvati
"""
import argparse
import os
import sys

import flight_logic as fl

MAX_MSG_OFFERTE = 25


def _avvisa_una_volta(quota, chiave_avviso, token, chat, testo, salva):
    """Manda un avviso di servizio una sola volta al mese per ciascun tipo."""
    if chiave_avviso in quota.setdefault("avvisi", []):
        return
    if salva and token and chat and fl.avvisa_telegram(token, chat, testo):
        quota["avvisi"].append(chiave_avviso)


def esegui(args, token, chat, chiave):
    budget = float(os.environ.get("BUDGET_MAX", 160))
    durata_max = float(os.environ.get("DURATA_MAX_ORE", 2.5))
    mesi = int(os.environ.get("MESI_AVANTI", 4))
    max_chiamate = int(os.environ.get("MAX_CHIAMATE", 4))
    tipo_viaggio = os.environ.get("TIPO_VIAGGIO", "tutte").strip().lower()
    tetto = int(os.environ.get("LIMITE_MENSILE", 230))
    salva = not args.dry_run and not args.demo  # dry-run e demo non toccano nessun file

    if tipo_viaggio not in fl.TIPI_VIAGGIO:
        raise ValueError(f"TIPO_VIAGGIO '{tipo_viaggio}' non valido: usa {', '.join(fl.TIPI_VIAGGIO)}.")

    quota = fl.carica_quota()
    chiamate = 0

    if args.demo:
        offerte = fl.dati_dimostrativi()
        print("Modalità demo: dati dimostrativi.")
    else:
        if not chiave:
            raise RuntimeError("Manca SERPAPI_KEY (controlla i Secrets del repository).")

        # Quota reale da SerpAPI (include anche le ricerche fatte dall'app); se non risponde, uso il contatore locale
        conto = fl.quota_account(chiave)
        if conto and conto.get("usate") is not None:
            quota["usate"] = int(conto["usate"])
            if conto.get("limite"):
                quota["limite"] = int(conto["limite"])
        rimaste = tetto - quota["usate"]
        if conto and conto.get("restanti") is not None:
            rimaste = min(rimaste, int(conto["restanti"]))
        da_fare = max(0, min(max_chiamate, rimaste))
        print(f"Quota SerpAPI: usate {quota['usate']} (tetto {tetto}, piano {quota['limite']}). "
              f"Chiamate previste oggi: {da_fare}.")

        if da_fare == 0:
            testo = (f"Ho raggiunto il tetto di {tetto} ricerche SerpAPI per questo mese "
                     f"(usate {quota['usate']}). Il bot non cercherà nuovi voli fino al mese prossimo.")
            print(testo)
            _avvisa_una_volta(quota, "finita", token, chat, testo, salva)
            if salva:
                fl.salva_quota(quota)
            return 0

        print(f"Ricerca reale: max {da_fare} chiamate, orizzonte: mese corrente + {mesi} mesi, "
              f"tipologia: {fl.TIPI_VIAGGIO[tipo_viaggio]}.")
        offerte, chiamate, errori = fl.cerca_offerte(chiave, mesi=mesi, max_chiamate=da_fare,
                                                    tipo_viaggio=tipo_viaggio)
        print(f"Chiamate SerpAPI fatte: {chiamate}. Destinazioni grezze: {len(offerte)}.")

        # Aggiorno il contatore (le chiamate fallite di solito non vengono addebitate: stima prudente)
        dopo = fl.quota_account(chiave)
        if dopo and dopo.get("usate") is not None:
            quota["usate"] = int(dopo["usate"])
        else:
            quota["usate"] += chiamate - len(errori)
        if salva:
            fl.salva_quota(quota)

        if chiamate and len(errori) == chiamate:
            raise RuntimeError("Tutte le chiamate a SerpAPI sono fallite (chiave errata o quota finita?). "
                               f"Primo errore: {errori[0]}")
        if chiamate and not offerte:
            raise RuntimeError("SerpAPI ha risposto ma senza nessuna destinazione con prezzo: "
                               "forse Google/SerpAPI ha cambiato il formato dei dati. "
                               "Controlla il log dell'esecuzione su GitHub Actions.")

        if salva:
            n = fl.aggiorna_archivio(offerte)
            print(f"Archivio aggiornato: {n} offerte (leggibili dall'app).")

        rimaste_dopo = tetto - quota["usate"]
        if rimaste_dopo <= 0:
            _avvisa_una_volta(quota, "finita", token, chat,
                              f"Raggiunto il tetto di {tetto} ricerche SerpAPI per questo mese: "
                              "il bot si ferma fino al mese prossimo.", salva)
        elif rimaste_dopo <= 3 * max_chiamate:
            _avvisa_una_volta(quota, "poche", token, chat,
                              f"Attenzione: restano solo {rimaste_dopo} ricerche SerpAPI prima del tetto "
                              f"mensile ({tetto}). Il bot si fermerà tra pochi giorni.", salva)
        if salva:
            fl.salva_quota(quota)

    filtrate = fl.filtra_offerte(offerte, budget, durata_max, tipo_viaggio=tipo_viaggio)
    print(f"Dopo i filtri (≤{budget:.0f}€, ≤{durata_max}h, solo estero, non visitate, "
          f"{fl.TIPI_VIAGGIO[tipo_viaggio]}): {len(filtrate)}")

    stato = fl.carica_stato(fl.FILE_STATO)
    nuove = fl.solo_nuove(filtrate, stato)
    print(f"Nuove o scese di prezzo rispetto all'ultima notifica: {len(nuove)}")
    if not nuove:
        print("Niente da notificare.")
        return 0

    piede = None if args.demo else f"Ricerche SerpAPI usate questo mese: {quota['usate']}/{tetto}"
    messaggio = fl.formatta_messaggio("✈️ NUOVE OFFERTE VOLI DA ROMA", nuove[:MAX_MSG_OFFERTE], int(budget), piede)
    if args.dry_run:
        print("\n--- DRY RUN: messaggio che verrebbe inviato ---\n")
        print(messaggio)
        return 0

    if fl.invia_telegram(token, chat, messaggio):
        fl.registra_notificate(nuove[:MAX_MSG_OFFERTE], stato)
        fl.salva_stato(fl.FILE_STATO, stato)
        print("Notifica inviata.")
        return 0
    print("ERRORE: invio Telegram fallito (stato non aggiornato, riproverò al prossimo giro).", file=sys.stderr)
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="non invia su Telegram e non salva nessun file (stato, archivio, quota)")
    ap.add_argument("--demo", action="store_true", help="usa dati dimostrativi invece di SerpAPI")
    args = ap.parse_args()
    if args.demo:  # i dati finti non devono mai arrivare su Telegram né finire nei file di stato
        args.dry_run = True

    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    chiave = os.environ.get("SERPAPI_KEY")
    reale = not args.dry_run and not args.demo

    if reale and (not token or not chat):
        print("ERRORE: mancano TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (controlla i Secrets).", file=sys.stderr)
        return 1

    try:
        return esegui(args, token, chat, chiave)
    except Exception as e:
        dettaglio = fl.pulisci_segreti(f"{type(e).__name__}: {e}", chiave, token)
        print("ERRORE:", dettaglio, file=sys.stderr)
        print(fl.stampa_traceback_pulito(chiave, token), file=sys.stderr)
        if reale:
            fl.avvisa_telegram(token, chat, "Il controllo giornaliero è fallito.\n\n" + dettaglio[:1500])
        return 1


if __name__ == "__main__":
    sys.exit(main())
