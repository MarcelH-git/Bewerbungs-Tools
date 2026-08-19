import requests
import re
import time
import json
import sys
from urllib.parse import quote

# STEPSTONE_HEADERS aus originalem Code übernehmen oder ggf. anpassen
STEPSTONE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def hole_indeed_beschreibung(url):
    """Holt vollständige Stellenbeschreibung von Indeed via Playwright+Stealth."""
    try:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
        with Stealth().use_sync(sync_playwright()) as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            page.goto(url, timeout=30000)
            page.wait_for_timeout(5000)
            html = page.content()
            browser.close()
        matches = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
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
        print(f"Indeed-Fehler: {e}")
    return None, None

def hole_indeed_beschreibungen_parallel(stellen, max_workers=3):
    """Holt Beschreibungen für mehrere Indeed-Stellen parallel."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    ergebnisse = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(hole_indeed_beschreibung, s['refnr']): s for s in stellen}
        for future in as_completed(futures):
            stelle = futures[future]
            try:
                ergebnisse[stelle['refnr']] = future.result()
            except Exception as e:
                print(f"Indeed parallel Fehler: {e}")
                ergebnisse[stelle['refnr']] = (None, None)
    return ergebnisse


def extrahiere_ort_indeed(titel, content=''):
    """Extrahiert Ort aus Indeed-Titel oder Content."""
    import re as _re
    titel_clean = _re.sub(r'\s*-\s*Indeed(\.com)?\s*$', '', titel)
    m = _re.search(r'-\s*\d{5}\s+([A-Z\xc4\xd6\xdc][a-z\xe4\xf6\xfc\xdf]+)', titel_clean)
    if m:
        return m.group(1)
    m = _re.search(r'-\s*([A-Z\xc4\xd6\xdc][a-z\xe4\xf6\xfc\xdf]{3,})\s*$', titel_clean)
    if m:
        return m.group(1)
    if 'Hamburg' in titel or 'Hamburg' in content:
        return 'Hamburg'
    return ''

def suche_indeed(begriffe):
    """Sucht Stellen via SearXNG auf Indeed."""
    trabajos = []
    gesehen_urls = set()
    
    for begriff in begriffe:
        try:
            query = f'site:de.indeed.com/viewjob {begriff} Hamburg'
            params = {
                'q': query,
                'format': 'json',
                'categories': 'general'
            }

            r = requests.get('http://127.0.0.1:8080/search', params=params, timeout=10)
            for res in r.json().get('results', []):
                url = res.get('url', '')
                if 'viewjob' not in url or url in gesehen_urls:
                    continue
                if 'de.indeed.com' not in url:
                    continue
                gesehen_urls.add(url)

                titel = res.get('title', '')
                titel = re.sub(r'\s*-\s*Indeed.*$', '', titel).strip()
                if not titel or titel.lower() == 'indeed':
                    continue
                content = res.get('content', '')
                
                # Firma extrahieren
                firma = ''
                if ' - ' in titel:
                    parts = titel.split(' - ')
                    titel = parts[0].strip()
                    firma = parts[1].strip()
                else:
                    # Content-Text durchsuchen, falls nicht im Titel
                    content = res.get('content', '')
                    m = re.search(r'bei der Firma ([^.]+)', content)
                    if m:
                        firma = m.group(1).strip()
                
                trabajos.append({
                    'refnr': url,
                    'titel': titel,
                    'arbeitgeber': firma,
                    'arbeitsort': {'ort': extrahiere_ort_indeed(titel, content), 'entfernung': None},
                    'beschreibung': content,
                    'quelle': 'indeed'
                })
            time.sleep(1)  # Rate-Limiting
        except Exception as e:
            print(f"Indeed-SearXNG-Fehler: {e}")
    
    return trabajos


if __name__ == '__main__':
    if '--test' not in sys.argv:
        print("== bitte --test ausfuehren ===")
        sys.exit(1)
    print("Suche Indeed-Stellen...")
    indeed_stellen = suche_indeed(['KI Automatisierung Hamburg', 'Python Automatisierung Hamburg'])
    print(f"{len(indeed_stellen)} Indeed-Stellen gefunden")
    if indeed_stellen:
        print("Testbeschreibungsholen...")
        url = indeed_stellen[0]['refnr']
        beschreibung, firma = hole_indeed_beschreibung(url)
        if beschreibung:
            print("Beschreibung:", beschreibung[:200] + "...")
            print("Firma:", firma)
        else:
            print("Keine Beschreibung gefunden")
    print("Fertig!")
