import requests, json, base64, math, os, time, re
from math import cos, radians

HOME_LAT, HOME_LON = (53.5530, 10.0062)

def suche_jobs(begriff):
    # v6-Endpunkt (v4 wurde abgeschaltet -> 404). v6 liefert die Treffer unter
    # 'ergebnisliste' mit umbenannten Feldern; hier zurueck auf das vom restlichen
    # Code erwartete Format (titel/arbeitgeber/arbeitsort/refnr) gemappt.
    url = 'https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs'
    params = {'was': begriff, 'wo': 'Hamburg', 'umkreis': 30, 'size': 5, 'angebotsart': 1, 'veroeffentlichtSeit': 7}
    r = requests.get(url, params=params, headers={'X-API-Key': 'jobboerse-jobsuche'}, timeout=20)
    if r.status_code != 200:
        return []
    ergebnisse = r.json().get('ergebnisliste', [])
    jobs = []
    for e in ergebnisse:
        lok = (e.get('stellenlokationen') or [{}])[0]
        adresse = lok.get('adresse', {})
        jobs.append({
            'titel': e.get('stellenangebotsTitel', ''),
            'arbeitgeber': e.get('firma', ''),
            'refnr': e.get('referenznummer', ''),
            'externeURL': e.get('externeURL'),
            'arbeitsort': {
                'ort': adresse.get('ort'),
                'plz': adresse.get('plz'),
                'entfernung': e.get('entfernung'),
            },
        })
    return jobs

def hole_details(refnr):
    # jobdetails laeuft weiterhin unter v4 (v6 gibt hier 403).
    encoded = base64.b64encode(refnr.encode()).decode()
    url = f'https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/{encoded}'
    r = requests.get(url, headers={'X-API-Key': 'jobboerse-jobsuche'}, timeout=20)
    return r.json()

def lade_koordinaten():
    try:
        lat, lon = None, None
        with open(os.path.expanduser('~/.openclaw/SOUL_PRIVATE.md'), 'r') as f:
            for zeile in f:
                if zeile.startswith('LAT:'):
                    lat = float(zeile.split(':')[1].strip())
                elif zeile.startswith('LON:'):
                    lon = float(zeile.split(':')[1].strip())
        return lat, lon
    except:
        return 53.5530, 10.0062

def distanz(job):
    entfernung = job.get('arbeitsort', {}).get('entfernung')
    if entfernung is not None:
        return float(entfernung)
    return None

def plz_zu_distanz(plz):
    try:
        r = requests.get(
            f'https://nominatim.openstreetmap.org/search?postalcode={plz}&country=DE&format=json',
            headers={'User-Agent': 'job-search-tool'}, timeout=2
        )
        data = r.json()
        if data:
            lat, lon = float(data[0]['lat']), float(data[0]['lon'])
            dlat = abs(lat - HOME_LAT) * 111
            dlon = abs(lon - HOME_LON) * 111 * cos(radians(HOME_LAT))
            return round(math.sqrt(dlat**2 + dlon**2), 1)
    except:
        pass
    return None
