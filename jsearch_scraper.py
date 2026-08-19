#!/usr/bin/env python3
import requests
import os
import re
import math
import json
import time

CALLS_PRO_LAUF = 5  # API-Calls pro Skript-Ausführung
QUOTA_CACHE = os.path.expanduser('~/.openclaw/jsearch_quota.json')

RAPIDAPI_KEY = None


def _get_key():
    global RAPIDAPI_KEY
    if RAPIDAPI_KEY:
        return RAPIDAPI_KEY
    cred_dir = os.environ.get('CREDENTIALS_DIRECTORY')
    if cred_dir:
        cred_path = os.path.join(cred_dir, 'rapidapi_key')
        if os.path.exists(cred_path):
            with open(cred_path) as f:
                RAPIDAPI_KEY = f.read().strip()
                return RAPIDAPI_KEY
    env_path = os.path.expanduser('~/.openclaw/.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith('RAPIDAPI_KEY='):
                    RAPIDAPI_KEY = line.split('=', 1)[1].strip()
                    return RAPIDAPI_KEY
    raise RuntimeError('RAPIDAPI_KEY weder im Credstore noch in ~/.openclaw/.env gefunden')


def _lade_quota():
    try:
        with open(QUOTA_CACHE) as f:
            return json.load(f)
    except Exception:
        return None


def _speichere_quota(remaining, reset_unix):
    try:
        with open(QUOTA_CACHE, 'w') as f:
            json.dump({'remaining': remaining, 'reset_unix': reset_unix}, f)
    except Exception as e:
        print(f"JSearch Quota-Cache Fehler: {e}")


def _berechne_min_remaining(reset_unix):
    tage_bis_reset = math.ceil((reset_unix - time.time()) / 86400)
    return max(0, tage_bis_reset) * CALLS_PRO_LAUF


def suche_jsearch(begriffe):
    key = _get_key()
    stellen = []
    gesehen_ids = set()

    # Quota aus Cache lesen und prüfen
    cache = _lade_quota()
    if cache:
        reset_unix = cache['reset_unix']
        remaining = cache['remaining']
        if time.time() >= reset_unix:
            # Reset ist bereits eingetreten — Cache ungültig, wir fahren einfach fort
            cache = None
            print("ℹ JSearch Quota-Cache abgelaufen (Reset war fällig) — wird nach erstem Call aktualisiert")
        else:
            min_remaining = _berechne_min_remaining(reset_unix)
            frei = max(0, remaining - min_remaining)
            tage = math.ceil((reset_unix - time.time()) / 86400)
            print(f"ℹ JSearch (Cache): {remaining} Anfragen übrig, Reset in {tage}d — {min_remaining} für Cronjob reserviert, {frei} für manuelle Läufe frei")
            if remaining <= min_remaining:
                print(f"⚠ JSearch übersprungen — Quota für Cronjob reserviert")
                return []

    min_remaining = None

    suchbegriffe = [
        'Junior IT Jobs Hamburg',
        'Junior Developer Automatisierung Hamburg',
        'Junior Data Analyst KI Hamburg Remote',
        'Junior Consultant Digitalisierung Deutschland Remote',
        'Berufseinsteiger IT Prozessautomatisierung Deutschland',
    ]

    for query in suchbegriffe:
        if min_remaining is not None and remaining <= min_remaining:
            print(f"⚠ JSearch Quota zu knapp ({remaining} verbleibend, {min_remaining} für Cronjob reserviert) — weitere Suchen übersprungen")
            break
        try:
            r = requests.get(
                'https://jsearch.p.rapidapi.com/search',
                headers={
                    'x-rapidapi-host': 'jsearch.p.rapidapi.com',
                    'x-rapidapi-key': key,
                },
                params={
                    'query': query,
                    'page': '1',
                    'num_pages': '2',
                    'country': 'de',
                    'date_posted': 'month',
                },
                timeout=40
            )
            remaining = int(r.headers.get('X-RateLimit-Requests-Remaining', 999))
            reset_sek = int(r.headers.get('X-RateLimit-Requests-Reset', 0))
            reset_unix = time.time() + reset_sek
            _speichere_quota(remaining, reset_unix)

            if min_remaining is None:
                min_remaining = _berechne_min_remaining(reset_unix)
                tage = math.ceil(reset_sek / 86400)
                frei = max(0, remaining - min_remaining)
                print(f"ℹ JSearch: {remaining} Anfragen übrig, Reset in {tage}d — {min_remaining} für Cronjob reserviert, {frei} für manuelle Läufe frei")

            for job in r.json().get('data', []):
                job_id = job.get('job_id', '')
                if job_id in gesehen_ids:
                    continue
                gesehen_ids.add(job_id)

                beschreibung = job.get('job_description', '')
                location = job.get('job_location', '') or ''
                ist_hamburg = 'hamburg' in location.lower() or 'hamburg' in beschreibung.lower()
                ist_remote = any(w in beschreibung.lower() for w in ['homeoffice', 'remote', 'hybrid', 'home office'])

                if not ist_hamburg and not ist_remote:
                    continue

                stellen.append({
                    'refnr': f'jsearch_{job_id}',
                    'titel': job.get('job_title', ''),
                    'arbeitgeber': job.get('employer_name', ''),
                    'arbeitsort': {'ort': 'Hamburg' if ist_hamburg else 'Remote', 'entfernung': None},
                    'beschreibung': beschreibung,
                    'quelle': 'jsearch',
                    'url': job.get('job_apply_link', ''),
                })
        except Exception as e:
            print(f"JSearch Fehler ({query}): {e}")

    return stellen


if __name__ == '__main__':
    from modules.job_config import SUCHEN
    stellen = suche_jsearch(SUCHEN[:3])
    print(f"{len(stellen)} Stellen gefunden")
    for s in stellen[:5]:
        print(f"  {s['titel']} | {s['arbeitgeber']} | {s['arbeitsort']['ort']}")
