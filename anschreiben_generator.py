import requests, json, os, re, base64
from datetime import datetime

OUTPUT_DIR = '/media/sf_Shared_Folder_VM_OC'
os.makedirs(OUTPUT_DIR, exist_ok=True)
PATH_PRIVATE = os.path.expanduser('~/.openclaw/SOUL_PRIVATE.md')
PATH_TEMPLATE = os.path.expanduser('~/.openclaw/anschreiben_template.txt')

def parse_private(text):
    daten = {}
    for zeile in text.split('\n'):
        if ':' in zeile and not zeile.startswith('#'):
            key, _, value = zeile.partition(':')
            daten[key.strip()] = value.strip()
    return daten

def hole_stelle(refnr):
    print(f"Hole Stelle {refnr}...")
    if 'linkedin.com/jobs' in refnr:
        job_id = refnr.split('/')[-2] if refnr.endswith('/') else refnr.split('/')[-1]
        return hole_stelle_linkedin(job_id)
    if 'stepstone.de' in refnr:
        return hole_stelle_stepstone(refnr)
    encoded = base64.b64encode(refnr.encode()).decode()
    url = f'https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/{encoded}'
    r = requests.get(url, headers={'X-API-Key': 'jobboerse-jobsuche'})
    data = r.json()
    adresse = ''
    if data.get('stellenlokationen'):
        adr = data['stellenlokationen'][0].get('adresse', {})
        adresse = f"{adr.get('strasse', '')} {adr.get('hausnummer', '')}\n{adr.get('plz', '')} {adr.get('ort', '')}"
    ansprechpartner = ''
    if data.get('ansprechpartner'):
        ap = data['ansprechpartner']
        ansprechpartner = f"{ap.get('anrede', '')} {ap.get('vorname', '')} {ap.get('nachname', '')}".strip()
    return {
        'titel': data.get('stellenangebotsTitel', ''),
        'firma': data.get('firma', ''),
        'beschreibung': data.get('stellenangebotsBeschreibung', ''),
        'adresse': adresse,
        'ansprechpartner': ansprechpartner
    }



def hole_stelle_stepstone(url):
    import re as _re, json as _json, subprocess as _sp
    try:
        result = _sp.run(
            ['curl', '-s', '-m', '30',
             '-H', 'User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
             '-H', 'Accept: text/html,application/xhtml+xml',
             '-H', 'Accept-Language: de-DE,de;q=0.9',
             url],
            capture_output=True, text=True, timeout=35
        )
        html = result.stdout
    except Exception:
        html = ''
    matches = _re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, _re.DOTALL)
    for m in matches:
        try:
            data = _json.loads(m)
            if data.get('@type') == 'JobPosting':
                beschreibung = _re.sub(r'<[^>]+>', ' ', data.get('description', ''))
                beschreibung = _re.sub(r'\s+', ' ', beschreibung).strip()
                loc = data.get('jobLocation', {}).get('address', {})
                adresse = loc.get('streetAddress', '') + '\n' + loc.get('postalCode', '') + ' ' + loc.get('addressLocality', '')
                return {
                    'titel': data.get('title', ''),
                    'firma': data.get('hiringOrganization', {}).get('name', ''),
                    'beschreibung': beschreibung,
                    'adresse': adresse.strip(),
                    'ansprechpartner': ''
                }
        except:
            continue
    return {'titel': '', 'firma': '', 'beschreibung': '', 'adresse': '', 'ansprechpartner': ''}



def hole_stelle_linkedin(job_id):
    import requests as _req
    from linkedin_api import Linkedin
    import json as _json

    session = _req.Session()
    session.cookies.set('li_at', os.environ.get('LINKEDIN_LI_AT', ''))
    session.cookies.set('JSESSIONID', os.environ.get('LINKEDIN_JSESSIONID', ''))

    api = Linkedin('', '', cookies=session.cookies)
    details = api.get_job(job_id)

    firma = details.get('companyDetails', {}).get(
        'com.linkedin.voyager.deco.jobs.web.shared.WebCompactJobPostingCompany', {}
    ).get('companyResolutionResult', {}).get('name', '')

    beschreibung = details.get('description', {}).get('text', '')

    loc = details.get('formattedLocation', '')

    return {
        'titel': details.get('title', ''),
        'firma': firma,
        'beschreibung': beschreibung,
        'adresse': loc,
        'ansprechpartner': ''
    }

def hole_aufgabe_optionen(beschreibung, groq_key):
    with open(os.path.expanduser('~/.openclaw/SOUL_PUBLIC.md'), 'r', encoding='utf-8') as f:
        profil_public = f.read()

    _groq = os.environ.get('GROQ_API_KEY', '')

    keywords = ['Stellenbeschreibung', 'Deine Aufgaben', 'Ihre Aufgaben', 'Das erwartet']
    beschreibung_clean = re.sub(r'\*\*|##|__|&amp;', '', beschreibung)
    start = 0
    for kw in keywords:
        idx = beschreibung_clean.find(kw)
        if idx != -1:
            start = idx
            break
    abschnitt = beschreibung_clean[start:start+800]

    response = requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={'Authorization': f'Bearer {_groq}', 'Content-Type': 'application/json'},
        json={
            'model': 'openai/gpt-oss-20b',
            'messages': [
                {'role': 'system', 'content': 'Du bist dieser Bewerber:\n' + profil_public},
                {'role': 'user', 'content': (
                    "Stelle:\n" + abschnitt +
                    "\n\nWaehle die 5 Aufgaben aus dieser Stelle die dich am meisten ansprechen."
                    "\nFormuliere jeden als aktiven Infinitivsatz (max 8 Woerter)."
                    "\nBeispiel: 'KI-Features direkt in Produkte einbauen'"
                    "\nNur die 5 nummerierten Zeilen, keine Einleitung."
                )}
            ],
            'max_tokens': 150
        }
    )
    text = response.json()['choices'][0]['message']['content'].strip()
    # Einleitung entfernen falls vorhanden
    zeilen = [z.strip() for z in text.split('\n') if re.match(r'^\d+\.?', z.strip())]
    optionen_text = '\n'.join(zeilen)
    return optionen_text, abschnitt


def hole_aufgabe_groq(beschreibung, groq_key):
    ki_keywords = ['ki', 'ai', 'ml', 'mlops', 'automatisierung', 'python', 'data', 'llm', 'plattform', 'modell']
    beschreibung_clean = re.sub(r'\*\*|##|__|&amp;', '', beschreibung)
    
    keywords = ['Stellenbeschreibung', 'Deine Aufgaben', 'Ihre Aufgaben', 'Das erwartet']
    start = 0
    for kw in keywords:
        idx = beschreibung_clean.find(kw)
        if idx != -1:
            start = idx
            break
    abschnitt = beschreibung_clean[start:start+1000]
    
    prompt = f"""Lies diese Aufgabenliste und extrahiere EINE konkrete Tätigkeit in max. 8 Wörtern.
Bevorzuge Tätigkeiten mit KI, ML, Automatisierung oder Python Bezug.
Beginne NICHT mit einem Pronomen (Du, Sie, Ich) oder Artikel (der, die, das).
Gib NUR die Tätigkeit aus, keine Erklärung.

Aufgaben:
{abschnitt[:500]}"""

    response = requests.post(
        'http://127.0.0.1:11434/v1/chat/completions',
        headers={'Authorization': f'Bearer {groq_key}', 'Content-Type': 'application/json'},
        json={'model': 'qwen2.5:14b', 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 30}
    )
    result = response.json()['choices'][0]['message']['content'].strip()
    result = re.sub(r'^(Du |Sie |Ich |der |die |das |Der |Die |Das )', '', result)
    return result[0].lower() + result[1:] if result else 'KI-basierte Automatisierung'

def hole_aufgabe(beschreibung):
    beschreibung = re.sub(r'\*\*|##|__|&amp;', '', beschreibung)
    keywords = ['Stellenbeschreibung', 'Deine Aufgaben', 'Ihre Aufgaben', 'Das erwartet']
    start = 0
    for kw in keywords:
        idx = beschreibung.find(kw)
        if idx != -1:
            start = idx
            break
    abschnitt = beschreibung[start:start+2000]
    zeilen = abschnitt.split('\n')
    
    # Bevorzuge Zeilen mit KI/ML/Automatisierungs-Keywords
    ki_keywords = ['ki', 'ai', 'ml', 'machine learning', 'automatisierung', 'python', 'data', 'llm', 'mlops', 'operationalisier', 'plattform', 'modell']
    beste_zeile = None
    fallback_zeile = None
    
    for zeile in zeilen:
        zeile = zeile.strip().lstrip('-•*').strip()
        if len(zeile) > 20 and len(zeile) < 150:
            if fallback_zeile is None:
                fallback_zeile = zeile
            if any(kw in zeile.lower() for kw in ki_keywords):
                beste_zeile = zeile
                break
    
    zeile = beste_zeile or fallback_zeile
    if not zeile:
        return 'KI-basierte Automatisierung und Produktentwicklung'
    
    woerter = zeile.split()
    for i in range(min(14, len(woerter)), 7, -1):
        teilsatz = ' '.join(woerter[:i])
        if not teilsatz.rstrip().endswith(('sowie', 'und', 'für', 'der', 'die', 'das', 'in', 'mit', 'von')):
            result = teilsatz.rstrip(',./*')
            # Alle Artikel und Pronomen am Anfang entfernen
            for art in ('Du berätst ', 'Du ', 'du ', 'Sie ', 'der ', 'die ', 'das ', 'Der ', 'Die ', 'Das '):
                if result.startswith(art):
                    result = result[len(art):]
                    break
            result = result.strip()
            if not result:
                continue
            return result[0].lower() + result[1:]
    return 'KI-basierte Automatisierung und Produktentwicklung'

def _privat(feld):
    import subprocess
    r = subprocess.run(['sudo', '-u', 'private_data', 'python3', '/opt/openclaw/private_resolver.py', feld],
                       capture_output=True, text=True)
    return r.stdout.strip()

def erstelle_anschreiben(stelle):
    with open(PATH_TEMPLATE, 'r', encoding='utf-8') as f:
        template = f.read()
    datum = datetime.now().strftime('%d.%m.%Y')
    briefkopf = f"{_privat('NAME')}\n{_privat('ADRESSE')}\n{_privat('PLZ_ORT')}\n{_privat('TELEFON')}\n{_privat('EMAIL')}"
    empfaenger = f"{stelle['firma']}\n{stelle['adresse']}"
    anrede = f"Sehr geehrte/r {stelle['ansprechpartner']}," if stelle['ansprechpartner'] else "Sehr geehrte Damen und Herren,"
    _groq_key = os.environ.get('GROQ_API_KEY', '')

    print("\n--- Optionen für Brückensatz ---")
    optionen, abschnitt = hole_aufgabe_optionen(stelle['beschreibung'], _groq_key)
    print(optionen)
    print("\nWähle eine Option (1-5) oder schreibe eigenen Text:")
    auswahl = input().strip()

    if auswahl in ['1','2','3','4','5']:
        for zeile in optionen.split('\n'):
            if zeile.strip().startswith(auswahl + '.') or zeile.strip().startswith(auswahl + ')'):
                basis = re.sub(r'^\d+[.)\s]+', '', zeile).strip().rstrip('.').lstrip('.')
                break
        aufgabe = basis
        # Bereinigen
        aufgabe = aufgabe.strip('"').strip()
        aufgabe = aufgabe.lstrip('...').strip().rstrip('.')
        for art in ('Die ', 'Der ', 'Das ', 'die ', 'der ', 'das '):
            if aufgabe.startswith(art):
                aufgabe = aufgabe[len(art):]
                break
        for art in ('Die ', 'Der ', 'Das ', 'die ', 'der ', 'das '):
            if aufgabe.startswith(art):
                aufgabe = aufgabe[len(art):]
                break
    else:
        aufgabe = auswahl.rstrip('.')
    text = template
    text = text.replace('{BRIEFKOPF}', briefkopf)
    text = text.replace('{EMPFAENGER}', empfaenger)
    text = text.replace('{DATUM}', datum)
    text = text.replace('{TITEL}', stelle['titel'])
    text = text.replace('Sehr geehrte Damen und Herren,', anrede)
    text = text.replace('{GROQ_SATZ}', aufgabe[0].upper() + aufgabe[1:] + '.')
    text = text.replace('{NAME}', _privat('NAME'))
    return text

def speichern(anschreiben, firma):
    firma_clean = re.sub(r'[^a-zA-Z0-9]', '_', firma.lower())
    datum = datetime.now().strftime('%Y%m%d')
    dateiname = f"anschreiben_{firma_clean}_{datum}.txt"
    pfad = os.path.join(OUTPUT_DIR, dateiname)
    with open(pfad, 'w', encoding='utf-8') as f:
        f.write(anschreiben)
    return pfad

if __name__ == "__main__":
    print("Template: (1) KI/Automatisierung  (2) Data Analyst")
    template_wahl = input().strip()
    if template_wahl == '2':
        PATH_TEMPLATE = os.path.expanduser('~/.openclaw/anschreiben_template_data_analyst.txt')
    else:
        PATH_TEMPLATE = os.path.expanduser('~/.openclaw/anschreiben_template.txt')
    refnr = input("Referenznummer: ").strip()
    stelle = hole_stelle(refnr)
    anschreiben = erstelle_anschreiben(stelle)
    print("\n--- ANSCHREIBEN ---")
    print(anschreiben)
    pfad = speichern(anschreiben, stelle['firma'])
    print(f"\nGespeichert: {pfad}")
