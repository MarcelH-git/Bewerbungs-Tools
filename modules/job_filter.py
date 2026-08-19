import re


def ist_titel_ausgeschlossen(titel, ausschluss_liste):
    titel_lower = titel.lower().strip()
    for wort in ausschluss_liste:
        idx = titel_lower.find(wort)
        if idx == -1:
            continue
        vorher = titel_lower[:idx].strip().strip('(').strip()
        if vorher == '' or vorher == '(':
            return True
    return False


def ist_beschreibung_ausgeschlossen(beschreibung, ausschluss_liste):
    beschreibung_lower = beschreibung.lower()
    return any(kw in beschreibung_lower for kw in ausschluss_liste)


def ist_hamburg_oder_remote(job):
    ort = job['arbeitsort'].get('ort', '').lower()
    beschreibung = job.get('beschreibung', '').lower()
    titel = job.get('titel', '').lower()
    refnr = job.get('refnr', '').lower()
    ist_hamburg = 'hamburg' in ort or 'hamburg' in titel or 'hamburg' in refnr
    hat_homeoffice = any(w in beschreibung for w in ['homeoffice', 'remote', 'hybrid'])
    return ist_hamburg or hat_homeoffice


def _dedup_key(job):
    titel = re.sub(r'\s+', ' ', job.get('titel', '').lower().strip())
    titel = re.sub(r'\(m/w/d\)|\(w/m/d\)|\(all genders\)|\(m/f/d\)|m/w/divers', '', titel).strip()
    arbeitgeber = job.get('arbeitgeber', '').lower().strip()[:20]
    return (titel, arbeitgeber)


def filter_jobs(jobs, cfg):
    gefiltert = []
    # NUR inhaltliche Ausschlüsse (Titel) dürfen dauerhaft als "gesehen" gelten —
    # sie ändern sich nicht. Geo- und Duplikat-Ausschluss NICHT dauerhaft merken:
    # eine heute als Duplikat/nicht-Hamburg aussortierte Stelle kann morgen der
    # einzige Treffer sein (andere Quelle liefert sie nicht mehr) oder die
    # Beschreibung fehlte nur im Kurzsnippet. Sonst frisst sich der Pool leer.
    titel_ausgeschlossen = set()
    gesehen_keys = set()
    for job in jobs:
        if ist_titel_ausgeschlossen(job['titel'], cfg['TITEL_AUSSCHLUSS']):
            print(f"⚠ {job['titel']} — Titel ausgeschlossen")
            titel_ausgeschlossen.add(job['refnr'])
            continue
        if not ist_hamburg_oder_remote(job):
            print(f"⚠ {job['titel']} in {job['arbeitsort'].get('ort', '?')} — kein Hamburg/Homeoffice, wird aussortiert")
            continue
        key = _dedup_key(job)
        if key in gesehen_keys:
            print(f"⚠ {job['titel']} — Duplikat ({job.get('quelle', '?')}), wird aussortiert")
            continue
        gesehen_keys.add(key)
        gefiltert.append(job)
    return gefiltert, titel_ausgeschlossen
