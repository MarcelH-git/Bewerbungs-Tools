import requests, json

def suche_stepstone(begriffe):
    """Sucht Stellen via SearXNG auf Stepstone, gibt direkt Stellen-Dicts zurück."""
    stellen = []
    gesehen_urls = set()
    for begriff in begriffe:
        try:
            query = f'site:stepstone.de/stellenangebote {begriff}'
            r = requests.get('http://127.0.0.1:8080/search', params={
                'q': query, 'format': 'json', 'categories': 'general'
            }, timeout=10)
            for res in r.json().get('results', []):
                url = res.get('url', '')
                if 'stellenangebote--' not in url or url in gesehen_urls:
                    continue
                gesehen_urls.add(url)
                titel = res.get('title', '')
                titel = re.sub(r'\s*-\s*Stepstone$', '', titel)
                titel = re.sub(r'\s*-\s*Job bei der Firma\s*', ' bei ', titel)
                firma = ''
                if ' bei ' in titel:
                    parts = titel.split(' bei ')
                    titel = parts[0].strip()
                    firma = parts[-1].strip()
                if not firma:
                    content = res.get('content', '')
                    m = re.search(r'bei der Firma ([^.]+)', content)
                    if m:
                        firma = m.group(1).strip()
                beschreibung = res.get('content', '')
                stellen.append({
                    'refnr': url,
                    'titel': titel,
                    'arbeitgeber': firma,
                    'arbeitsort': {'ort': extrahiere_ort_stepstone(url), 'entfernung': None},
                    'beschreibung': beschreibung,
                    'quelle': 'stepstone'
                })
            time.sleep(1)
        except Exception as e:
            print(f"SearXNG Fehler: {e}")
    return stellen

def hole_stepstone_beschreibung(url):
    """Holt vollständige Stellenbeschreibung von Stepstone."""
    try:
        r = requests.get(url, headers=STEPSTONE_HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        matches = re.findall(r'<script type="application/ld+json">(.*?)</script>', r.text, re.DOTALL)
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

def extrahiere_ort_stepstone(url):
    pass