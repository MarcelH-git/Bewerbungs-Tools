import os
import json

SUCHEN = [
    'Prozessautomatisierung', 'RPA Developer', 'Digitalisierung',
    'Junior IT Consultant', 'Data Analyst', 'Junior Developer',
    'Automatisierung', 'KI Berater', 'Digital Transformation',
    'FinTech Junior', 'Junior Fintech Developer', 'Junior RPA Banking',
    'Junior Data Analyst FinTech', 'Junior Business Analyst FinTech',
    'Junior Prozessautomatisierung Bank', 'Digital Banking Junior',
    'Payment Automation Junior', 'RegTech Junior'
]

TITEL_AUSSCHLUSS = [
    'senior', 'head', 'lead', 'teamleiter', 'projektleitung', 'projektleiter',
    'werkstudent', 'werkstudentin', 'working student', 'student assistant',
    'studentische hilfskraft', 'studentische aushilfskraft', 'aushilfskraft'
    # Praktika bewusst NICHT ausgeschlossen (Nutzerwunsch 2026-08-04) — Bewertung via MIN_PUNKTE
]

BESCHREIBUNG_AUSSCHLUSS = [
    'softwarebeschaffung', 'anforderungsmanagement', 'it-vertrieb',
    'software-vertrieb', 'pre-sales', 'presales', 'account manager',
    'kundenstamm aufbauen'
]

CHECKLISTE = """
KANDIDATENPROFIL — Technische Kenntnisse:
- Programmiersprachen: NUR Python (Pandas, NumPy, PyTorch) und AutoHotkey
- KEINE Kenntnisse in: Java, TypeScript, JavaScript, C#, C++, Ruby, PHP
- KEINE Kenntnisse in: Spring, Quarkus, Angular, React, Vue, Flutter
- KEINE Kenntnisse in: SAP, Salesforce, Kubernetes, Docker, BPMN
- Erfahrung: Prozessautomatisierung, Bot-Entwicklung, IT-Support (5 Jahre)
- Studium: BWL Finance Bachelor

ABSOLUTE K.O. KRITERIEN (sofort aussortieren, keine Ausnahmen):
- Stelle ist NICHT in Hamburg/Umgebung (max. 30km) UND bietet KEIN Homeoffice/Remote/Hybrid
- Stelle erfordert 3+ Jahre Berufserfahrung
- Pflichtanforderungen enthalten Technologien die der Kandidat nicht kennt (Java, SAP, Docker etc.)
MUSS-KRITERIEN (K.O. wenn nicht erfüllt):
- Junior-Level oder Berufseinsteiger ausdrücklich willkommen
- Stelle maximal 30 km entfernt ODER Homeoffice/Hybrid möglich
- Keine unbekannten Technologien als Pflichtanforderung
- Keine 3+ Jahre Berufserfahrung als Pflicht

AUSSCHLIESSEN (sehr niedrige Bewertung):
- Pre-Sales, Software-Vertrieb, Softwarebeschaffung
- Reine Projektmanagement-Rollen ohne technischen Fokus
- Reisebereitschaft als Hauptanforderung

PASSUNG (positiv):
- Automatisierung, Digitalisierung, KI/AI im Fokus
- Python oder allgemeine Programmierkenntnisse willkommen
- BWL/Business-Verständnis gefragt
- Lernbereitschaft wichtiger als spezifische Technologien
- FinTech / Banking / Payment / RegTech / Digital Banking — BWL Finance Bachelor
  ist hier direkt einschlägig, insbesondere in Kombination mit Python/RPA
- Fachliche Nähe zu Finance, Zahlungsverkehr, Compliance-Automatisierung,
  regulatorischen Prozessen ist Pluspunkt (nicht Sales!)

BONUS:
- Homeoffice/Hybrid möglich
- Unbefristet
- Gehalt angegeben
"""


def _read_secret(name):
    cred_dir = os.environ.get('CREDENTIALS_DIRECTORY')
    if cred_dir:
        path = os.path.join(cred_dir, name)
        if os.path.exists(path):
            with open(path) as f:
                return f.read().strip()
    return None


def load_config():
    openclaw = {}
    with open(os.path.expanduser('~/.openclaw/openclaw.json')) as f:
        openclaw = json.load(f)

    openclaw_env = {}
    env_path = os.path.expanduser('~/.openclaw/.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    openclaw_env[k.strip()] = v.strip()

    def secret(cred_name, env_name):
        return _read_secret(cred_name) or openclaw_env.get(env_name, '')

    profil_public = ''
    try:
        with open(os.path.expanduser('~/.openclaw/SOUL_PUBLIC.md')) as f:
            profil_public = f.read()
    except FileNotFoundError:
        pass

    home_lat, home_lon = 53.5530, 10.0062
    try:
        with open(os.path.expanduser('~/.openclaw/SOUL_PRIVATE.md')) as f:
            for zeile in f:
                if zeile.startswith('LAT:'):
                    home_lat = float(zeile.split(':')[1].strip())
                elif zeile.startswith('LON:'):
                    home_lon = float(zeile.split(':')[1].strip())
    except FileNotFoundError:
        pass

    return {
        'BOT_TOKEN': secret('telegram_bot_token', 'TELEGRAM_BOT_TOKEN') or openclaw.get('channels', {}).get('telegram', {}).get('botToken', ''),
        'CHAT_ID': secret('telegram_chat_id', 'TELEGRAM_CHAT_ID'),
        'GROQ_KEY': secret('groq_api_key', 'GROQ_API_KEY'),
        'GROQ_KEY_SECONDARY': secret('groq_api_key_secondary', 'GROQ_API_KEY_SECONDARY'),
        'LINKEDIN_LI_AT': secret('linkedin_li_at', 'LINKEDIN_LI_AT') or openclaw.get('env', {}).get('LINKEDIN_LI_AT', ''),
        'LINKEDIN_JSESSIONID': secret('linkedin_jsessionid', 'LINKEDIN_JSESSIONID') or openclaw.get('env', {}).get('LINKEDIN_JSESSIONID', ''),
        'HOME_LAT': home_lat,
        'HOME_LON': home_lon,
        'PROFIL_PUBLIC': profil_public,
        'CHECKLISTE': CHECKLISTE,
        'SUCHEN': SUCHEN,
        'TITEL_AUSSCHLUSS': TITEL_AUSSCHLUSS,
        'BESCHREIBUNG_AUSSCHLUSS': BESCHREIBUNG_AUSSCHLUSS,
        'MIN_PUNKTE': 4,  # Stellen unter dieser Bewertung nicht per Telegram schicken (1-3 = K.O.)
    }
