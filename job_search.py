#!/usr/bin/env python3
# ------------------------------------------------------------
# WICHTIG: Dieser Ordner ist root:winnetou_kowslovskiwitch / 0750.
# Schreibzugriff nur als root. Grund: Wrapper ~/bin/job-search startet
# das Skript mit NOPASSWD-sudo + Credstore-Zugriff (Groq/Telegram/
# LinkedIn/RapidAPI). Würde das Skript für den User schreibbar sein,
# könnte ein Edit die Credstore-Keys exfiltrieren.
#
# Zum Editieren:
#   sudo chmod -R g+w /home/winnetou_kowslovskiwitch/bewerbungs-tools
#   # ... änderungen machen ...
#   sudo chmod -R g-w /home/winnetou_kowslovskiwitch/bewerbungs-tools
# ------------------------------------------------------------
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(__file__))

from modules.job_config import load_config
from modules.job_scraper import scrape_all, hole_arge_details
from modules.job_filter import filter_jobs, ist_beschreibung_ausgeschlossen
from modules.job_evaluator import vorauswahl_nach_quellen, quelle, bewerte_stelle, punkte_int, plz_zu_distanz
from modules.job_notifier import versende_ergebnisse, sende_telegram

SEEN_FILE = os.path.expanduser('~/job_search_seen.json')
# Hart ausgeschlossene Stellen (Titel-Filter, K.O.-Begriffe in der Beschreibung) —
# bleiben auch bei --reset gesperrt, da sie nie passen und ein Reset dafür da ist,
# potenziell passende (nur schwach bewertete) Stellen erneut zu sehen.
AUSGESCHLOSSEN_FILE = os.path.expanduser('~/job_search_ausgeschlossen.json')
LOCK_FILE = '/tmp/job_search.lock'


def _lade_set(pfad):
    if os.path.exists(pfad):
        with open(pfad) as f:
            return set(json.load(f))
    return set()


def _speichere_set(pfad, werte):
    with open(pfad, 'w') as f:
        json.dump(list(werte), f)


def lade_gesehen():
    return _lade_set(SEEN_FILE), _lade_set(AUSGESCHLOSSEN_FILE)


def speichere_gesehen(gesehen):
    _speichere_set(SEEN_FILE, gesehen)


def speichere_ausgeschlossen(ausgeschlossen):
    _speichere_set(AUSGESCHLOSSEN_FILE, _lade_set(AUSGESCHLOSSEN_FILE) | ausgeschlossen)


MAX_RETRY_OHNE_TREFFER = 3  # harte Obergrenze, sonst Free-Tier-TPD-Risiko
RETRY_PAUSE_SEKUNDEN = 30


def main():
    if os.path.exists(LOCK_FILE):
        print("Jobsuche läuft bereits — abgebrochen.")
        return
    open(LOCK_FILE, 'w').close()

    try:
        for versuch in range(1, MAX_RETRY_OHNE_TREFFER + 1):
            # Retry NUR bei technisch sauberem Lauf ohne Treffer (Vorauswahl lehnte
            # alles zu Recht ab) — bei Groq-Fehlern (TPD/429 erschöpft, Exception)
            # bricht _main() bereits selbst ab, kein weiterer Versuch sinnvoll/sicher.
            weiter_versuchen = _main(versuch, MAX_RETRY_OHNE_TREFFER)
            if not weiter_versuchen:
                break
            if versuch < MAX_RETRY_OHNE_TREFFER:
                time.sleep(RETRY_PAUSE_SEKUNDEN)
    finally:
        os.remove(LOCK_FILE)


def _main(versuch=1, max_versuche=1):
    """Gibt True zurück, wenn ein Retry sinnvoll ist: die Vorauswahl lief technisch
    sauber durch, lehnte aber (zu Recht) alles ab — dank vorauswahl_abgelehnt sind
    diese Jobs beim nächsten Versuch bereits ausgeschlossen, echte neue Kandidaten
    rücken nach. Bei Groq-Fehlern (TPD/429 erschöpft) oder wenn es Ergebnisse gab
    (auch schwache), wird False zurückgegeben — kein Retry, um das Free-Tier-
    Tageslimit nicht durch blindes Wiederholen zu sprengen.
    """
    verbose = '--no-verbose' not in sys.argv

    if '--reset' in sys.argv and os.path.exists(SEEN_FILE):
        os.remove(SEEN_FILE)
        print("Gesehene Stellen zurückgesetzt.")

    cfg = load_config()

    def notify(text):
        print(text)
        if verbose:
            sende_telegram(text, cfg)

    def notify_warn(text):
        # Fehler/Warnungen (z.B. Groq liefert 0 Refs) immer an Telegram senden,
        # unabhängig von --no-verbose — sonst verschwindet die Fehlerursache bei
        # automatischen Timer-Läufen spurlos, nur das leere Endergebnis bleibt sichtbar.
        print(text)
        sende_telegram(text, cfg)

    try:
        gesehen, ausgeschlossen = lade_gesehen()

        if verbose and versuch == 1:
            sende_telegram('🔄 Jobsuche gestartet...', cfg)
        elif versuch > 1:
            notify(f"🔁 Kein Treffer — Versuch {versuch}/{max_versuche} mit aktualisierter Ausschlussliste...")

        neue_jobs = scrape_all(cfg, gesehen | ausgeschlossen, notify=notify)

        if not neue_jobs:
            sende_telegram('✅ Keine neuen Stellen heute.', cfg)
            speichere_gesehen(gesehen)
            return False

        gefilterte_jobs, titel_ausgeschlossen = filter_jobs(neue_jobs, cfg)
        notify(f"🔍 {len(gefilterte_jobs)} Stellen nach Filter — starte KI-Vorauswahl...")

        try:
            top_jobs, vorauswahl_abgelehnt = vorauswahl_nach_quellen(gefilterte_jobs, cfg, notify=notify_warn)
        except Exception as e:
            # z.B. Groq-Tageslimit erschöpft — nicht den ganzen Lauf killen, aber
            # auch keinen Retry, das würde das Limit nur weiter strapazieren.
            sende_telegram(f'⚠ Vorauswahl abgebrochen ({e}). Heute keine KI-Bewertung möglich.', cfg)
            speichere_ausgeschlossen(titel_ausgeschlossen)
            speichere_gesehen(gesehen)
            return False

        if not top_jobs:
            # Vorauswahl lief sauber durch, lehnte aber alles ab. vorauswahl_abgelehnt
            # ist bereits dauerhaft ausgeschlossen -> nächster Versuch sieht neue Jobs.
            speichere_ausgeschlossen(titel_ausgeschlossen | vorauswahl_abgelehnt)
            speichere_gesehen(gesehen)
            if versuch < max_versuche:
                notify(f"⚙️ 0 Stellen ausgewählt — {len(vorauswahl_abgelehnt)} davon dauerhaft ausgeschlossen.")
                return True
            sende_telegram('ℹ Keine bewertbaren Stellen heute (nach mehreren Versuchen).', cfg)
            return False
        notify(f"⚙️ {len(top_jobs)} Stellen ausgewählt — bewerte Details...")

        t0 = time.time()
        ausgesondert = set()
        bewertete = []
        for job in top_jobs:
            try:
                if quelle(job) in ('stepstone', 'linkedin', 'apis'):
                    beschreibung = job.get('beschreibung', '')
                else:
                    beschreibung = hole_arge_details(job['refnr']).get('stellenangebotsBeschreibung', '')

                if ist_beschreibung_ausgeschlossen(beschreibung, cfg['BESCHREIBUNG_AUSSCHLUSS']):
                    print(f"⚠ {job['titel']} — Beschreibung ausgeschlossen")
                    ausgesondert.add(job['refnr'])
                    continue

                bew = bewerte_stelle(job, beschreibung, cfg, notify=notify_warn)
                dist = job.get('arbeitsort', {}).get('entfernung')
                if dist == 0:
                    plz = job.get('arbeitsort', {}).get('plz')
                    if plz:
                        dist = plz_zu_distanz(plz, cfg['HOME_LAT'], cfg['HOME_LON'])
                if dist is not None:
                    bew['DISTANZ'] = dist

                bewertete.append((job, bew))
                print(f"✅ {job['titel']}: {bew.get('PUNKTE', '?')}/10")
                time.sleep(1)
            except Exception as e:
                print(f"❌ Fehler bei {job.get('titel', '?')}: {e}")

        print(f"Bewertung: {time.time()-t0:.1f}s")
        bewertete.sort(key=lambda x: punkte_int(x[1]), reverse=True)

        # Schwache Stellen (unter MIN_PUNKTE) nicht anzeigen — verhindert das
        # Auffüllen der Top-Liste mit 1/10-K.O.-Stellen bei wenig Material.
        min_punkte = cfg.get('MIN_PUNKTE', 4)
        gut_genug = [(job, bew) for job, bew in bewertete if punkte_int(bew) >= min_punkte]
        zu_schwach = [(job, bew) for job, bew in bewertete if punkte_int(bew) < min_punkte]
        angezeigte = gut_genug[:8]
        if angezeigte:
            versende_ergebnisse(angezeigte, cfg)
        elif bewertete:
            sende_telegram(f'ℹ Heute keine Stelle über {min_punkte}/10 — {len(zu_schwach)} schwächere aussortiert.', cfg)
        else:
            sende_telegram('ℹ Keine bewertbaren Stellen heute.', cfg)

        # zu_schwach (1-3 Punkte) sind laut Punkteskala harte K.O.s, keine Grauzone —
        # zusammen mit titel_ausgeschlossen/ausgesondert/vorauswahl_abgelehnt dauerhaft
        # sperren, damit ein --reset sie nicht zurückbringt. vorauswahl_abgelehnt sind
        # Jobs, die Groq in der Vorauswahl bereits gesehen und nicht ausgewählt hat —
        # ohne das würden sie bei jedem Lauf erneut Deckel-Slots belegen und erneut
        # (zu Recht) abgelehnt werden. Nur angezeigte (>= MIN_PUNKTE, potenziell
        # passend) landen in der resettbaren Liste.
        angezeigte_refnrs = {job['refnr'] for job, _ in angezeigte}
        schwach_refnrs = {job['refnr'] for job, _ in zu_schwach}
        speichere_ausgeschlossen(titel_ausgeschlossen | ausgesondert | schwach_refnrs | vorauswahl_abgelehnt)
        speichere_gesehen(gesehen | angezeigte_refnrs)
        notify('✅ Jobsuche abgeschlossen.')
        return False

    except Exception as e:
        sende_telegram(f'❌ Jobsuche abgestürzt: {e}', cfg)
        raise


if __name__ == '__main__':
    main()
