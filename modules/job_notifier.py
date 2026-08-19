import html

import requests


def sende_telegram(text, cfg):
    url = f'https://api.telegram.org/bot{cfg["BOT_TOKEN"]}/sendMessage'
    r = requests.post(url, json={'chat_id': cfg['CHAT_ID'], 'text': text, 'parse_mode': 'HTML'})
    if not r.json().get('ok'):
        print(f"Telegram Fehler: {r.json()}")
        # Fallback ohne HTML-Formatierung
        requests.post(url, json={'chat_id': cfg['CHAT_ID'], 'text': text})


def refnr_zu_url(refnr, job=None):
    if refnr.startswith('http'):
        return refnr
    if refnr.startswith('linkedin_'):
        return f'https://www.linkedin.com/jobs/view/{refnr[len("linkedin_"):]}'
    if refnr.startswith(('jsearch_', 'stepstone_')) and job and job.get('url'):
        return job['url']
    return f'https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}'


def baue_nachricht(bewertete):
    def esc(v):
        return html.escape(str(v))

    nachricht = '🔍 <b>Top Stellen heute:</b>\n\n'
    for job, bew in bewertete:
        p = int(bew.get('PUNKTE', 0)) if str(bew.get('PUNKTE', '0')).isdigit() else 0
        nachricht += f"<b>{p}/10</b> {'⭐' * min(p, 10)}\n"
        nachricht += f"<b>{esc(job['titel'])}</b>\n"
        nachricht += f"🏢 {esc(job['arbeitgeber'])}\n"
        nachricht += f"📍 {esc(job['arbeitsort']['ort'])}"
        dist = bew.get('DISTANZ')
        try:
            dist = float(dist) if dist is not None else None
        except (ValueError, TypeError):
            dist = None
        if dist is not None and 0 < dist < 50:
            nachricht += f" (~{dist} km)"
        nachricht += '\n'
        if bew.get('GEHALT') and bew.get('GEHALT') != 'Keine Angabe':
            nachricht += f"💰 {esc(bew['GEHALT'])}\n"
        if bew.get('HOMEOFFICE') and bew.get('HOMEOFFICE') != 'Keine Angabe':
            nachricht += f"🏠 {esc(bew['HOMEOFFICE'])}\n"
        if bew.get('PASSUNG'):
            nachricht += f"💡 {esc(bew['PASSUNG'])}\n"
        if bew.get('GRUND'):
            nachricht += f"🎯 {esc(bew['GRUND'])}\n"
        nachricht += f"📋 <a href=\"{esc(refnr_zu_url(job['refnr'], job))}\">Zur Stelle</a>\n\n"
    return nachricht


def _teile_nachricht(nachricht, limit=4000):
    """Zerlegt an Job-Grenzen (\\n\\n), nie mitten in einem HTML-Tag."""
    teile = []
    aktuell = ''
    for block in nachricht.split('\n\n'):
        kandidat = block if not aktuell else f"{aktuell}\n\n{block}"
        if len(kandidat) <= limit:
            aktuell = kandidat
        else:
            if aktuell:
                teile.append(aktuell)
            aktuell = block
    if aktuell:
        teile.append(aktuell)
    return teile


def versende_ergebnisse(bewertete, cfg):
    nachricht = baue_nachricht(bewertete)
    for teil in _teile_nachricht(nachricht):
        sende_telegram(teil, cfg)
