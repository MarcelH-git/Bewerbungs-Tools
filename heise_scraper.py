import requests
import re
import time
import json
import sys

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def hole_heise_beschreibung(url):
    """Holt vollständige Stellenbeschreibung von jobs.heise.de via JSON-LD."""
    try:
        url = url.replace('://www.jobs.heise.de', '://jobs.heise.de')
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None, None
        matches = re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            r.text, re.DOTALL
        )
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
    except Exception as e:
        print(f"Heise-Fehler: {e}")
    return None, None

def suche_heise(begriffe):
    """Sucht Stellen via SearXNG auf jobs.heise.de/stellenanzeigen."""
    stellen = []
    gesehen_urls = set()

    for begriff in begriffe:
        try:
            query = f'site:jobs.heise.de/stellenanzeigen {begriff} Hamburg'
            r = requests.get('http://127.0.0.1:8080/search', params={
                'q': query, 'format': 'json', 'categories': 'general'
            }, timeout=10)
            for res in r.json().get('results', []):
                url = res.get('url', '')
                url = url.replace('://www.jobs.heise.de', '://jobs.heise.de')
                if 'stellenanzeigen/' not in url or url in gesehen_urls:
                    continue
                gesehen_urls.add(url)

                titel = res.get('title', '')
                titel = re.sub(r'\s*\|\s*jobs\.heise\.de\s*$', '', titel)
                titel = re.sub(r'\s*-\s*jobs\.heise\.de\s*$', '', titel)

                firma = ''
                if ' - ' in titel:
                    parts = titel.split(' - ')
                    titel = parts[0].strip()
                    firma = parts[1].strip() if len(parts) > 1 else ''

                # PLZ+Ort aus Titel extrahieren (z.B. "22305 Hamburg")
                ort = ''
                m = re.search(r'\d{5}\s+([A-ZÄÖÜ][a-zäöüß]+)', titel)
                if m:
                    ort = m.group(1)
                    titel = titel[:m.start()].strip().rstrip('-').strip()
                elif 'Hamburg' in titel:
                    ort = 'Hamburg'

                stellen.append({
                    'refnr': url,
                    'titel': titel,
                    'arbeitgeber': firma,
                    'arbeitsort': {'ort': ort or 'Hamburg', 'entfernung': None},
                    'beschreibung': res.get('content', ''),
                    'quelle': 'heise'
                })
            time.sleep(1)
        except Exception as e:
            print(f"Heise-SearXNG-Fehler: {e}")

    return stellen


if __name__ == '__main__':
    if '--test' not in sys.argv:
        print("Bitte --test angeben.")
        sys.exit(1)

    print("Suche Heise-Stellen...")
    stellen = suche_heise(['KI Automatisierung', 'Python Junior'])
    print(f"{len(stellen)} Stellen gefunden")
    for s in stellen[:5]:
        print(f"  {s['titel']} | {s['arbeitgeber']} | {s['arbeitsort']['ort']}")
        print(f"  {s['refnr']}")

    if stellen:
        print("\nTestbeschreibung holen...")
        url = stellen[0]['refnr']
        beschreibung, firma = hole_heise_beschreibung(url)
        if beschreibung:
            print(f"Firma: {firma}")
            print(f"Beschreibung ({len(beschreibung)} Zeichen): {beschreibung[:300]}...")
        else:
            print("Keine Beschreibung gefunden")

    print("Fertig!")
