"""Freie Job-APIs als Ersatz für die nicht mehr scrapebaren Quellen (Indeed/Heise).

Alle Quellen liefern sauberes JSON ohne Scraping/Cloudflare/SearXNG:
- Arbeitnow  : deutsche Stellen inkl. Hamburg (paginiert)
- The Muse   : mit Hamburg-Location-Filter
- Remotive   : Remote-Developer
- Jobicy     : Remote, geo-Filter
- Himalayas  : Remote

Jede Quelle gibt das im restlichen Code erwartete Format zurück:
{refnr, titel, arbeitgeber, arbeitsort{ort,entfernung}, beschreibung, quelle, url}
Gefiltert wird auf Hamburg ODER Remote/Homeoffice (passend zum Profil).
"""
import requests
import re
import html as _html
import time
from datetime import datetime, timezone

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}


def _clean(text):
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', ' ', text)
    text = _html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


def _passt(ort_text, beschreibung, remote_flag=False):
    """True, wenn Hamburg ODER Remote/Homeoffice — sonst raus."""
    blob = f"{ort_text} {beschreibung}".lower()
    if remote_flag:
        return True
    if 'hamburg' in blob:
        return True
    return any(w in blob for w in ['remote', 'homeoffice', 'home office', 'home-office', 'hybrid', 'anywhere', 'worldwide', 'deutschlandweit'])


def _relevant(titel, begriffe):
    """Grobe Relevanz: mind. ein Suchbegriff-Wort im Titel (die APIs haben keinen guten Volltext-Filter)."""
    t = titel.lower()
    for b in begriffe:
        for wort in b.lower().split():
            if len(wort) > 3 and wort in t:
                return True
    return False


MAX_ALTER_TAGE = 14

def _zu_alt(iso_str, max_tage=MAX_ALTER_TAGE):
    """True wenn der ISO-Datums-String älter als max_tage ist."""
    if not iso_str:
        return False
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        alter = (datetime.now(timezone.utc) - dt).days
        return alter > max_tage
    except Exception:
        return False

def suche_arbeitnow(begriffe, max_seiten=3):
    stellen = []
    url = 'https://www.arbeitnow.com/api/job-board-api'
    grenze = time.time() - MAX_ALTER_TAGE * 86400
    try:
        for _ in range(max_seiten):
            r = requests.get(url, headers=UA, timeout=20)
            if r.status_code != 200:
                break
            data = r.json()
            for j in data.get('data', []):
                created = j.get('created_at')
                if created and float(created) < grenze:
                    continue
                ort = j.get('location', '') or ''
                besch = _clean(j.get('description', ''))
                if not _passt(ort, besch, j.get('remote')):
                    continue
                if not _relevant(j.get('title', ''), begriffe):
                    continue
                stellen.append({
                    'refnr': f"arbeitnow_{j.get('slug', '')}",
                    'titel': j.get('title', ''),
                    'arbeitgeber': j.get('company_name', ''),
                    'arbeitsort': {'ort': 'Remote' if j.get('remote') else (ort or 'Hamburg'), 'entfernung': None},
                    'beschreibung': besch[:2000],
                    'quelle': 'arbeitnow',
                    'url': j.get('url', ''),
                })
            url = data.get('links', {}).get('next')
            if not url:
                break
    except Exception as e:
        print(f"Arbeitnow Fehler: {e}")
    return stellen


def suche_themuse(begriffe, max_seiten=2):
    stellen = []
    try:
        for page in range(max_seiten):
            r = requests.get('https://www.themuse.com/api/public/jobs',
                             params={'location': 'Hamburg, Germany', 'page': page},
                             headers=UA, timeout=20)
            if r.status_code != 200:
                break
            for j in r.json().get('results', []):
                titel = j.get('name', '')
                if not _relevant(titel, begriffe):
                    continue
                orte = ', '.join(l.get('name', '') for l in j.get('locations', []))
                firma = j.get('company', {}).get('name', '') if isinstance(j.get('company'), dict) else ''
                besch = _clean(j.get('contents', ''))
                stellen.append({
                    'refnr': f"themuse_{j.get('id', '')}",
                    'titel': titel,
                    'arbeitgeber': firma,
                    'arbeitsort': {'ort': orte or 'Hamburg', 'entfernung': None},
                    'beschreibung': besch[:2000],
                    'quelle': 'themuse',
                    'url': j.get('refs', {}).get('landing_page', '') if isinstance(j.get('refs'), dict) else '',
                })
    except Exception as e:
        print(f"TheMuse Fehler: {e}")
    return stellen


def suche_remotive(begriffe):
    stellen = []
    try:
        # Remotive: search-Param pro Begriff wäre zu viele Calls -> ein Developer-Suchlauf, dann Titel-Filter
        r = requests.get('https://remotive.com/api/remote-jobs',
                         params={'search': 'developer OR analyst OR consultant', 'limit': 100},
                         headers=UA, timeout=20)
        if r.status_code == 200:
            for j in r.json().get('jobs', []):
                if _zu_alt(j.get('publication_date')):
                    continue
                titel = j.get('title', '')
                if not _relevant(titel, begriffe):
                    continue
                besch = _clean(j.get('description', ''))
                stellen.append({
                    'refnr': f"remotive_{j.get('id', '')}",
                    'titel': titel,
                    'arbeitgeber': j.get('company_name', ''),
                    'arbeitsort': {'ort': 'Remote', 'entfernung': None},
                    'beschreibung': besch[:2000],
                    'quelle': 'remotive',
                    'url': j.get('url', ''),
                })
    except Exception as e:
        print(f"Remotive Fehler: {e}")
    return stellen


def suche_jobicy(begriffe):
    stellen = []
    try:
        r = requests.get('https://jobicy.com/api/v2/remote-jobs',
                         params={'count': 100, 'industry': 'dev'},
                         headers=UA, timeout=20)
        if r.status_code == 200:
            for j in r.json().get('jobs', []):
                titel = j.get('jobTitle', '')
                if not _relevant(titel, begriffe):
                    continue
                besch = _clean(j.get('jobDescription', '') or j.get('jobExcerpt', ''))
                stellen.append({
                    'refnr': f"jobicy_{j.get('id', '')}",
                    'titel': titel,
                    'arbeitgeber': j.get('companyName', ''),
                    'arbeitsort': {'ort': j.get('jobGeo', 'Remote') or 'Remote', 'entfernung': None},
                    'beschreibung': besch[:2000],
                    'quelle': 'jobicy',
                    'url': j.get('url', ''),
                })
    except Exception as e:
        print(f"Jobicy Fehler: {e}")
    return stellen


def suche_himalayas(begriffe):
    stellen = []
    try:
        r = requests.get('https://himalayas.app/jobs/api',
                         params={'limit': 100},
                         headers=UA, timeout=20)
        if r.status_code == 200:
            for j in r.json().get('jobs', []):
                if _zu_alt(j.get('createdAt') or j.get('created_at')):
                    continue
                titel = j.get('title', '')
                if not _relevant(titel, begriffe):
                    continue
                besch = _clean(j.get('description', '') or j.get('excerpt', ''))
                stellen.append({
                    'refnr': f"himalayas_{j.get('guid', '')}",
                    'titel': titel,
                    'arbeitgeber': j.get('companyName', ''),
                    'arbeitsort': {'ort': 'Remote', 'entfernung': None},
                    'beschreibung': besch[:2000],
                    'quelle': 'himalayas',
                    'url': j.get('applicationLink', '') or '',
                })
    except Exception as e:
        print(f"Himalayas Fehler: {e}")
    return stellen


def suche_alle_apis(begriffe):
    """Alle freien APIs abfragen und zusammenführen (dedupliziert nach refnr)."""
    alle = []
    for fn in (suche_arbeitnow, suche_themuse, suche_remotive, suche_jobicy, suche_himalayas):
        alle.extend(fn(begriffe))
    seen = set()
    uniq = []
    for j in alle:
        if j['refnr'] in seen:
            continue
        seen.add(j['refnr'])
        uniq.append(j)
    return uniq
