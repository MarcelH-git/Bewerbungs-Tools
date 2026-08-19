import requests
import json
import time
import os
import re
import base64


ARGE_API_KEY = 'jobboerse-jobsuche'

STEPSTONE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'de-DE,de;q=0.9',
}


def _map_arge_job(e):
    # v6 liefert umbenannte Felder -> zurueck auf das vom restlichen Code
    # erwartete Format (titel/arbeitgeber/refnr/arbeitsort).
    lok = (e.get('stellenlokationen') or [{}])[0]
    adresse = lok.get('adresse', {})
    return {
        'titel': e.get('stellenangebotsTitel', ''),
        'arbeitgeber': e.get('firma', ''),
        'refnr': e.get('referenznummer', ''),
        'externeURL': e.get('externeURL'),
        'arbeitsort': {
            'ort': adresse.get('ort'),
            'plz': adresse.get('plz'),
            'entfernung': e.get('entfernung'),
        },
    }


def suche_arge(begriffe):
    # v6-Endpunkt (v4 abgeschaltet -> 404). Treffer unter 'ergebnisliste'.
    jobs = []
    for begriff in begriffe:
        url = 'https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs'
        params = {'was': begriff, 'wo': 'Hamburg', 'umkreis': 30, 'size': 5, 'angebotsart': 1}
        try:
            r = requests.get(url, params=params, headers={'X-API-Key': ARGE_API_KEY}, timeout=20)
            if r.status_code != 200:
                print(f"ARGE Fehler ({begriff}): HTTP {r.status_code}")
                continue
            jobs.extend(_map_arge_job(e) for e in r.json().get('ergebnisliste', []))
        except Exception as e:
            print(f"ARGE Fehler ({begriff}): {e}")
    return jobs


def hole_arge_details(refnr):
    # jobdetails laeuft weiterhin unter v4 (v6 gibt hier 403).
    encoded = base64.b64encode(refnr.encode()).decode()
    url = f'https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/{encoded}'
    r = requests.get(url, headers={'X-API-Key': ARGE_API_KEY}, timeout=20)
    return r.json()


def suche_linkedin(cfg):
    try:
        from linkedin_api import Linkedin
        import requests as req

        session = req.Session()
        session.cookies.set('li_at', cfg['LINKEDIN_LI_AT'])
        session.cookies.set('JSESSIONID', cfg['LINKEDIN_JSESSIONID'])
        api = Linkedin('', '', cookies=session.cookies)

        suchbegriffe = [
            'Künstliche Intelligenz Junior',
            'Python Automatisierung Junior',
            'Junior Data Analyst',
            'Junior Produktmanager Digital',
            'KI Berater Junior',
        ]

        alle_job_ids = {}
        for begriff in suchbegriffe:
            jobs = api.search_jobs(
                keywords=begriff,
                experience=['1', '2'],
                job_type=['F'],
                listed_at=604800,
                limit=5,
                location_geo_urn='urn:li:geo:101282230'
            )
            for j in jobs:
                job_id = j['entityUrn'].split(':')[-1]
                alle_job_ids[job_id] = True
            time.sleep(1)

        from concurrent.futures import ThreadPoolExecutor, as_completed

        def hole_job(job_id):
            try:
                details = api.get_job(job_id)
                firma = details.get('companyDetails', {}).get(
                    'com.linkedin.voyager.deco.jobs.web.shared.WebCompactJobPostingCompany', {}
                ).get('companyResolutionResult', {}).get('name', '')
                beschreibung = details.get('description', {}).get('text', '')
                ort = details.get('formattedLocation', '')
                ist_hamburg = 'hamburg' in ort.lower() or ort == ''
                ist_remote = any(w in beschreibung.lower() for w in ['remote', 'homeoffice', 'home office', '100% mobil'])
                if not ist_hamburg and not ist_remote:
                    return None
                return {
                    'refnr': f'linkedin_{job_id}',
                    'titel': details.get('title', ''),
                    'arbeitgeber': firma,
                    'arbeitsort': {'ort': ort or 'Hamburg', 'entfernung': 0},
                    'beschreibung': beschreibung,
                    'quelle': 'linkedin'
                }
            except Exception as e:
                print(f"LinkedIn Job Fehler: {e}")
                return None

        stellen = []
        job_ids = list(alle_job_ids.keys())[:15]
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(hole_job, jid): jid for jid in job_ids}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    stellen.append(result)
        return stellen
    except Exception as e:
        print(f"LinkedIn Fehler: {e}")
        return []


def _extrahiere_ort_stepstone(url):
    slug = re.search(r'stellenangebote--(.+)--\d+', url)
    if not slug:
        return ''
    teile = slug.group(1).split('-')
    if 'Hamburg' in teile:
        return 'Hamburg'
    firma_suffixe = ['GmbH', 'AG', 'KG', 'SE', 'eG', 'Co', 'mbH', 'Inc', 'Ltd']
    keine_orte = ['GmbH', 'AG', 'KG', 'SE', 'eG', 'Co', 'mbH', 'Inc', 'Ltd', 'und', 'der', 'die',
                  'Electronic', 'Digital', 'Solutions', 'Services', 'Systems', 'Group', 'Global',
                  'Management', 'Consulting']
    for i in range(len(teile) - 1, -1, -1):
        if teile[i] in firma_suffixe:
            for j in range(i - 1, -1, -1):
                if teile[j] not in keine_orte and teile[j][0].isupper() and len(teile[j]) > 3:
                    return teile[j]
    return ''


def hole_stepstone_beschreibung(url):
    try:
        r = requests.get(url, headers=STEPSTONE_HEADERS, timeout=10)
        if r.status_code != 200:
            return None, None
        matches = re.findall(r'<script type="application/ld\+json">(.*?)</script>', r.text, re.DOTALL)
        for m in matches:
            try:
                data = json.loads(m)
                if data.get('@type') == 'JobPosting':
                    beschreibung = re.sub(r'<[^>]+>', ' ', data.get('description', ''))
                    beschreibung = re.sub(r'\s+', ' ', beschreibung).strip()
                    firma = data.get('hiringOrganization', {}).get('name', '')
                    return beschreibung, firma
            except:
                continue
    except:
        pass
    return None, None


def _stepstone_state_jobs(html):
    """Extrahiert die Job-Liste aus window.__PRELOADED_STATE__ der Stepstone-Suchseite.

    Stepstone rendert die Treffer serverseitig in ein JS-State-Objekt
    (searchResults.items) mit allen Feldern (title/companyName/location/url/
    textSnippet/workFromHome/postCode). Direktes Scraping der Suchseite umgeht
    SearXNG komplett — die Detailseiten sind gegen Direktabruf geschützt (HTTP 000),
    aber die Suchseite liefert genug (inkl. textSnippet als Beschreibung).
    """
    m = re.search(r'window\.__PRELOADED_STATE__\["app-unifiedResultlist"\]\s*=\s*(\{.*)', html, re.DOTALL)
    if not m:
        return []
    raw = m.group(1)
    depth = 0
    end = 0
    for i, c in enumerate(raw):
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    try:
        state = json.loads(raw[:end])
        return state.get('searchResults', {}).get('items', [])
    except Exception:
        return []


def suche_stepstone(begriffe):
    stellen = []
    gesehen_urls = set()
    for begriff in begriffe:
        try:
            slug = begriff.strip().replace(' ', '-')
            url = f'https://www.stepstone.de/jobs/{slug}/in-Hamburg'
            r = requests.get(url, headers=STEPSTONE_HEADERS, timeout=20)
            if r.status_code != 200:
                print(f"Stepstone Fehler ({begriff}): HTTP {r.status_code}")
                continue
            for job in _stepstone_state_jobs(r.text):
                job_url = job.get('url', '')
                if 'stellenangebote--' not in job_url:
                    continue
                voll_url = job_url if job_url.startswith('http') else f'https://www.stepstone.de{job_url}'
                # Stabile refnr aus der Stellen-ID (--<ID>-inline) bilden. Die volle URL
                # trägt einen wechselnden ?rltr=-Trackingparameter -> als refnr wäre
                # dieselbe Stelle bei jedem Lauf "neu" (seen-Filter/Dedup wirkungslos).
                m = re.search(r'--(\d+)-inline', voll_url)
                refnr = f'stepstone_{m.group(1)}' if m else voll_url
                if refnr in gesehen_urls:
                    continue
                gesehen_urls.add(refnr)
                # workFromHome: 0=nein, sonst (1/2) möglich -> für Distanz-/Ort-Logik
                wfh = job.get('workFromHome', 0)
                ort = (job.get('location') or '').split(',')[0].strip() or 'Hamburg'
                stellen.append({
                    'refnr': refnr,
                    'url': voll_url,
                    'titel': job.get('title', ''),
                    'arbeitgeber': job.get('companyName', ''),
                    'arbeitsort': {'ort': ort, 'plz': job.get('postCode'), 'entfernung': None},
                    'beschreibung': job.get('textSnippet', '') or '',
                    'homeoffice': bool(wfh),
                    'quelle': 'stepstone'
                })
            time.sleep(1)
        except Exception as e:
            print(f"Stepstone Fehler ({begriff}): {e}")
    return stellen


def scrape_all(cfg, gesehen, notify=print):
    import sys
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import time as _time

    begriffe = cfg['SUCHEN']
    sys.path.insert(0, os.path.expanduser('~'))

    def scrape_arge():
        t0 = _time.time()
        stellen = [j for j in suche_arge(begriffe) if j['refnr'] not in gesehen]
        notify(f"✅ ARGE: {len(stellen)} Stellen ({_time.time()-t0:.1f}s)")
        return stellen

    def scrape_linkedin():
        t0 = _time.time()
        stellen = suche_linkedin(cfg)
        neue = [s for s in stellen if s['refnr'] not in gesehen]
        notify(f"✅ LinkedIn: {len(neue)} Stellen ({_time.time()-t0:.1f}s)")
        return neue

    def scrape_stepstone():
        t0 = _time.time()
        roh = suche_stepstone(begriffe)
        # suche_stepstone liefert Titel/Firma/Ort/Beschreibung (textSnippet) bereits
        # aus dem Suchseiten-State — kein Detailseiten-Nachladen mehr nötig
        # (Detailseiten sind gegen Direktabruf geschützt).
        neue = [s for s in roh if s['refnr'] not in gesehen]
        notify(f"✅ Stepstone: {len(neue)} Stellen ({_time.time()-t0:.1f}s)")
        return neue

    # Indeed entfernt: Cloudflare blockt requests (403), headless-Playwright (Challenge)
    # und IP-fremde Cookies (403). Nicht mit vertretbarem Aufwand scrapebar.
    # Heise entfernt: SPA mit Consent-Wall + verstecktem API-Format.
    # Beide ersetzt durch scrape_apis() (freie Job-APIs).

    def scrape_apis():
        # Ersetzt Indeed+Heise (nicht mehr scrapebar: Cloudflare / SPA) durch
        # freie Job-APIs: Arbeitnow (DE), The Muse (Hamburg), Remotive/Jobicy/Himalayas (Remote).
        t0 = _time.time()
        stellen = []
        try:
            from modules.job_apis import suche_alle_apis
            roh = suche_alle_apis(begriffe)
            stellen = [s for s in roh if s['refnr'] not in gesehen]
            notify(f"✅ Job-APIs: {len(stellen)} Stellen ({_time.time()-t0:.1f}s)")
        except Exception as e:
            print(f"Job-APIs Fehler: {e}")
        return stellen

    def scrape_jsearch():
        t0 = _time.time()
        stellen = []
        try:
            from jsearch_scraper import suche_jsearch
            roh = suche_jsearch(begriffe)
            stellen = [s for s in roh if s['refnr'] not in gesehen]
            notify(f"✅ JSearch: {len(stellen)} Stellen ({_time.time()-t0:.1f}s)")
        except Exception as e:
            print(f"JSearch Fehler: {e}")
        return stellen

    aufgaben = {
        'arge': scrape_arge,
        'linkedin': scrape_linkedin,
        'stepstone': scrape_stepstone,
        'apis': scrape_apis,
        'jsearch': scrape_jsearch,
    }

    notify("🔍 Starte alle Scraper parallel...")
    ergebnisse = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fn): name for name, fn in aufgaben.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                ergebnisse[name] = future.result()
            except Exception as e:
                print(f"Scraper {name} Fehler: {e}")
                ergebnisse[name] = []

    return (
        ergebnisse.get('arge', []) +
        ergebnisse.get('stepstone', []) +
        ergebnisse.get('linkedin', []) +
        ergebnisse.get('apis', []) +
        ergebnisse.get('jsearch', [])
    )
