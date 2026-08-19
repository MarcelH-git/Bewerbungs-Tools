import requests
import re
import json
import time
from math import sqrt, cos, radians


def _groq_keys(cfg):
    """Verfügbare Groq-Keys in Reihenfolge: primär, dann sekundär (falls gesetzt)."""
    keys = [cfg.get('GROQ_KEY')]
    zweit = cfg.get('GROQ_KEY_SECONDARY')
    if zweit and zweit != cfg.get('GROQ_KEY'):
        keys.append(zweit)
    return [k for k in keys if k]


def _ist_tpd(response):
    return 'per day' in response.text or 'TPD' in response.text


def _groq_post(payload, cfg, max_versuche=4):
    """POST an Groq mit Retry bei HTTP 429 (Rate-Limit) und Key-Fallback bei TPD.

    Groq nennt im Fehlertext die Wartezeit ('try again in 15.6s'); die lesen wir
    aus und warten entsprechend, statt den ganzen Lauf abzubrechen. TPM-Limits im
    Free-Tier (12k tokens/min) werden so einfach ausgesessen.

    Ist das Tageslimit (TPD) eines Keys erschöpft, ist Warten sinnlos (Reset erst
    in Stunden) -> wir wechseln auf den nächsten Key. Der aktive Key-Index wird in
    cfg['_GROQ_KEY_IDX'] gemerkt, damit verbrauchte Keys über alle folgenden
    _groq_post-Aufrufe (Vorauswahl + jede Detailbewertung) übersprungen bleiben.
    """
    url = 'https://api.groq.com/openai/v1/chat/completions'
    keys = _groq_keys(cfg)
    idx = cfg.get('_GROQ_KEY_IDX', 0)

    while idx < len(keys):
        headers = {'Authorization': f'Bearer {keys[idx]}', 'Content-Type': 'application/json'}
        for versuch in range(max_versuche):
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code != 429:
                return response
            if _ist_tpd(response):
                # Tageslimit dieses Keys erschöpft -> auf nächsten Key wechseln.
                if idx + 1 < len(keys):
                    idx += 1
                    cfg['_GROQ_KEY_IDX'] = idx
                    print(f"⛔ Groq Tageslimit (TPD) auf Key {idx}/{len(keys)} erschöpft — wechsle auf Key {idx+1}/{len(keys)}.")
                    break  # innere Retry-Schleife verlassen, äußere while nimmt neuen Key
                print(f"⛔ Groq Tageslimit (TPD) auf allen {len(keys)} Key(s) erschöpft — breche Groq-Calls ab.")
                return response
            # Wartezeit aus Header oder Fehlertext ziehen, sonst Default.
            wartezeit = None
            retry_after = response.headers.get('retry-after')
            if retry_after:
                try:
                    wartezeit = float(retry_after)
                except ValueError:
                    wartezeit = None
            if wartezeit is None:
                m = re.search(r'try again in ([\d.]+)s', response.text)
                if m:
                    wartezeit = float(m.group(1))
            wartezeit = min((wartezeit or 5) + 0.5, 30)  # kleiner Puffer, Deckel 30s
            if versuch < max_versuche - 1:
                print(f"⏳ Groq Rate-Limit (429) — warte {wartezeit:.1f}s (Versuch {versuch+1}/{max_versuche})")
                time.sleep(wartezeit)
        else:
            # innere Schleife ohne break beendet -> weiterhin 429 (kein TPD)
            # Nächsten Key probieren falls vorhanden, anstatt aufzugeben.
            if idx + 1 < len(keys):
                idx += 1
                cfg['_GROQ_KEY_IDX'] = idx
                print(f"⏳ Groq TPM-Limit auf Key {idx}/{len(keys)} ausgeschöpft — wechsle auf Key {idx+1}/{len(keys)}.")
            else:
                return response  # alle Keys durch -> _groq_content meldet klar
    return response  # alle Keys durch -> letzter Response


def _groq_content(response):
    """Extrahiert den Antworttext aus einer Groq-Response oder wirft mit klarer Meldung.

    Groq liefert bei Rate-Limit/Überlast einen HTTP-Fehler oder ein JSON ohne
    'choices' (z.B. {'error': {...}}). Ungeprüfter Zugriff auf ['choices'] crasht
    dann mit KeyError('choices') — deshalb hier abfangen und den echten Grund melden.
    """
    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(f"Groq-Antwort war kein JSON (HTTP {response.status_code}): {response.text[:200]}")
    if 'choices' not in data:
        fehler = data.get('error')
        if isinstance(fehler, dict):
            fehler = fehler.get('message', fehler)
        raise RuntimeError(f"Groq-Fehler (HTTP {response.status_code}): {fehler or data}")
    return data['choices'][0]['message']['content']


_API_QUELLEN = ('arbeitnow', 'themuse', 'remotive', 'jobicy', 'himalayas')


def quelle(job):
    refnr = job.get('refnr', '')
    if 'stepstone' in refnr:
        return 'stepstone'
    if 'linkedin' in refnr:
        return 'linkedin'
    if 'jsearch' in refnr:
        return 'jsearch'
    # Freie Job-APIs (Arbeitnow/Muse/Remotive/Jobicy/Himalayas) unter 'apis' gruppieren
    q = job.get('quelle', 'arge')
    if q in _API_QUELLEN or any(refnr.startswith(p + '_') for p in _API_QUELLEN):
        return 'apis'
    return q


def vorauswahl_nach_quellen(gefilterte_jobs, cfg, notify=print):
    ZIEL = 18  # gewünschte Anzahl Stellen für Detailbewertung

    def aus_quelle(q):
        return [j for j in gefilterte_jobs if quelle(j) == q]

    quellen = {
        'arge':      (aus_quelle('arge'),      6),
        'stepstone': (aus_quelle('stepstone'), 3),
        'linkedin':  (aus_quelle('linkedin'),  2),
        'apis':      (aus_quelle('apis'),      3),
        'jsearch':   (aus_quelle('jsearch'),   3),
    }
    print(' + '.join(f"{len(j)} {q.upper()}" for q, (j, _) in quellen.items()) + " Jobs — Vorauswahl via Groq...")

    # Vorauswahl über alle Quellen in einem Groq-Call statt einem pro Quelle —
    # senkt den TPD/TPM-Druck an Tagen mit hoher Free-Tier-Auslastung deutlich.
    # Slots als Gewichtung mitgeben, damit der Gesamt-Deckel proportional verteilt wird.
    vorauswahl_cache, gesehene_refnrs = vorauswahl_alle_quellen(quellen, cfg, notify=notify)

    top_refnrs = list(dict.fromkeys(
        ref for q, (_, slot) in quellen.items()
        for ref in vorauswahl_cache.get(q, [])[:slot]
    ))

    # Wenn unter Ziel: mit weiteren Treffern aus dem Cache auffüllen
    if len(top_refnrs) < ZIEL:
        bereits = set(top_refnrs)
        extra = [
            ref for q, (_, slot) in quellen.items()
            for ref in vorauswahl_cache.get(q, [])[slot:]
            if ref not in bereits
        ]
        top_refnrs += extra[:ZIEL - len(top_refnrs)]

    # Von Groq gesehen, aber nicht ausgewählt -> dauerhaft ausschließen (analog zu
    # zu_schwach bei der Detailbewertung), sonst belegen dieselben Jobs bei jedem
    # Lauf wieder Deckel-Slots und Groq lehnt sie erneut (zu Recht) ab.
    abgelehnte_refnrs = gesehene_refnrs - set(top_refnrs)

    top_jobs = [j for j in gefilterte_jobs if j['refnr'] in top_refnrs]
    return top_jobs, abgelehnte_refnrs


def _dedup_und_deckel(jobs, deckel=50):
    """Entfernt Duplikate (gleicher Titel+Firma) und deckelt die Menge.

    Nötig, weil die Suchbegriffe stark überlappen (z.B. 216 Stepstone-Stellen mit
    viel Redundanz) und der Vorauswahl-Prompt sonst Groqs Token-Limit sprengt.
    Behält die volle Info pro Stelle (inkl. Beschreibung) — reduziert nur die Anzahl.
    """
    gesehen = set()
    uniq = []
    for j in jobs:
        key = (j.get('titel', '').strip().lower(), j.get('arbeitgeber', '').strip().lower())
        if key in gesehen:
            continue
        gesehen.add(key)
        uniq.append(j)
    return uniq[:deckel]


def _kuerze_woerter(text, max_woerter):
    woerter = text.split()
    return ' '.join(woerter[:max_woerter])


def _vorauswahl_prompt_kombiniert(quellen, cfg, beschreibung_woerter=80):
    """Baut einen Prompt mit einem Abschnitt pro nicht-leerer Quelle.

    quellen: dict[str, list[job]] (bereits dedupliziert/gedeckelt).
    Erwartet JSON als Antwort: {"arge": [refs...], "stepstone": [refs...], ...}
    — ein Call für alle Quellen statt einem pro Quelle, senkt TPD/TPM-Druck.
    """
    abschnitte = []
    for q, jobs in quellen.items():
        if not jobs:
            continue
        liste = '\n'.join([
            f"{i+1}. {j['titel']} bei {j['arbeitgeber']} | Ort: {j['arbeitsort'].get('ort','?')} | "
            f"{_kuerze_woerter(j.get('beschreibung',''), beschreibung_woerter)} (Ref: {j['refnr']})"
            for i, j in enumerate(jobs)
        ])
        abschnitte.append(f"=== {q.upper()} ===\n{liste}")

    return f"""Du bist ein Karriereberater. Wähle für JEDE Quelle unten bis zu 10 der besten Stellen für diesen Kandidaten aus.

Kandidatenprofil:
{cfg['PROFIL_PUBLIC']}

Bewertungskriterien:
{cfg['CHECKLISTE']}

{chr(10).join(abschnitte)}

Antworte NUR mit JSON in diesem Format, keine Erklärung, kein Markdown-Fence:
{{"arge": ["123-456-S", "..."], "stepstone": ["stepstone_789"]}}
Quellen ohne passende Stellen: leeres Array oder Key weglassen."""


def _json_aus_antwort(text):
    """Robustes JSON-Parsing: entfernt optionale ```json-Fences, sonst Fallback
    auf ersten { bis letzten } (Modell schreibt manchmal Vor-/Nachtext dazu)."""
    text = text.strip()
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        start, end = text.find('{'), text.rfind('}')
        if start != -1 and end != -1:
            text = text[start:end + 1]
    return json.loads(text)


_KNOWN_PREFIXES = ('jsearch_', 'linkedin_', 'stepstone_',
                    'arbeitnow_', 'themuse_', 'remotive_', 'jobicy_', 'himalayas_')


def _passende_refs(werte, bekannte_refnrs):
    """Validiert vom Modell gelieferte Refs gegen die bekannten Refs einer Quelle:
    exakter Match -> Teilstring-Fallback -> Präfix-Muster-Fallback."""
    refs = []
    for eintrag in werte:
        line = str(eintrag).strip()
        if line in bekannte_refnrs:
            refs.append(line)
            continue
        for ref in bekannte_refnrs:
            if ref in line:
                refs.append(ref)
                break
        else:
            if ('-S' in line and len(line) > 5) or 'stepstone.de' in line or any(line.startswith(p) for p in _KNOWN_PREFIXES):
                refs.append(line)
    return list(dict.fromkeys(refs))


def _deckel_pro_quelle(quellen_mit_slot, gesamt_ziel=40, minimum=3):
    """Verteilt einen GESAMT-Deckel proportional zur Slot-Gewichtung der Quellen.

    Ein reiner Pro-Quelle-Deckel (z.B. 15) summiert sich bei 4-5 gleichzeitig
    gefüllten Quellen zu einem Prompt, der weit über Groqs Payload-Limit liegt —
    beobachtet: 24k Zeichen, danach 2x 413-Halbierung bis fast nichts mehr übrig
    war und das Modell mangels brauchbarer Daten 0 Refs lieferte. Statt auf die
    413-Notbremse zu setzen, wird die Gesamtmenge von vornherein klein gehalten.
    """
    slot_summe = sum(slot for _, slot in quellen_mit_slot.values()) or 1
    deckel = {}
    for q, (jobs, slot) in quellen_mit_slot.items():
        anteilig = round(gesamt_ziel * slot / slot_summe)
        deckel[q] = max(minimum, anteilig) if jobs else 0
    return deckel


def vorauswahl_alle_quellen(quellen_mit_slot, cfg, notify=print):
    """quellen_mit_slot: dict[str, (list[job], slot_gewicht)] -> dict[str, list[refnr]].

    Ein Groq-Call für alle Quellen. Warnungen gehen über notify() statt nur
    print() raus, damit sie auch bei --no-verbose-Läufen (systemd) sichtbar
    sind — sonst verschwinden Fehler aus dieser Stufe spurlos im Prozess-Stdout,
    das niemand mitliest.
    """
    deckel = _deckel_pro_quelle(quellen_mit_slot, gesamt_ziel=cfg.get('VORAUSWAHL_GESAMT_ZIEL', 40))
    quellen = {q: _dedup_und_deckel(jobs, deckel[q]) for q, (jobs, _slot) in quellen_mit_slot.items()}
    if not any(quellen.values()):
        return {}, set()

    def _payload():
        # groq/compound-mini statt gpt-oss-20b: gpt-oss wählte bei dieser
        # Ranking-Aufgabe (bis zu 10 beste Stellen pro Quelle) selbst mit
        # reasoning_effort='low' konsequent 0 Refs, obwohl valide passende Jobs
        # im Prompt standen — compound-mini lieferte nachweislich brauchbare
        # Auswahlen (siehe Controller-Treffer). Bewusster Rollback, kein Versehen.
        return {
            'model': 'groq/compound-mini',
            'messages': [{'role': 'user', 'content': _vorauswahl_prompt_kombiniert(quellen, cfg)}],
            'max_tokens': 1500,
        }

    response = _groq_post(_payload(), cfg)
    # Payload zu groß (HTTP 413) -> jede Quelle proportional halbieren statt
    # global (55 Stepstone vs. 6 ARGE dürfen nicht gleich hart getroffen werden)
    # und den kompletten Lauf killen.
    while response.status_code == 413 and any(len(v) > 1 for v in quellen.values()):
        quellen = {q: jobs[:max(1, len(jobs) // 2)] for q, jobs in quellen.items()}
        gesamt = sum(len(v) for v in quellen.values())
        notify(f"⚠️ Groq-Fehler (HTTP 413) — verkleinere alle Quellen auf zusammen {gesamt} Jobs und versuche erneut.")
        response = _groq_post(_payload(), cfg)

    # Refnrs, die tatsächlich im (evtl. nach 413 gekürzten) Prompt standen — Groq
    # hat sie gesehen und bewertet. Bei einer inhaltlich klaren Antwort (auch wenn
    # sie 0 Treffer ergibt) dürfen sie dauerhaft ausgeschlossen werden, damit sie
    # nicht bei jedem Lauf erneut Deckel-Slots belegen, obwohl sie schon einmal
    # geprüft und für unpassend befunden wurden.
    gesehene_refnrs = {j['refnr'] for jobs in quellen.values() for j in jobs}

    text = _groq_content(response)
    try:
        daten = _json_aus_antwort(text)
    except (json.JSONDecodeError, ValueError):
        notify(f"⚠️ Vorauswahl: JSON nicht parsebar. Modell-Antwort (erste 300 Zeichen): {text[:300]!r}")
        # Unklare Antwort -> nichts dauerhaft ausschließen, könnte an Groq liegen.
        return {}, set()

    ergebnis = {}
    for q, jobs in quellen.items():
        if not jobs:
            continue
        bekannte_refnrs = {j['refnr'] for j in jobs}
        werte = daten.get(q, []) if isinstance(daten, dict) else []
        ergebnis[q] = _passende_refs(werte, bekannte_refnrs)
    gesamt_refs = sum(len(v) for v in ergebnis.values())
    if gesamt_refs == 0:
        notify(f"⚠️ Vorauswahl: 0 Refs erkannt. Modell-Antwort (erste 300 Zeichen): {text[:300]!r}")
    elif gesamt_refs < len(ergebnis):
        # Weniger Refs als nicht-leere Quellen -> Modell liefert deutlich weniger
        # als die erbetenen bis zu 10 pro Quelle. Rohantwort zur Diagnose zeigen.
        notify(f"⚠️ Vorauswahl: nur {gesamt_refs} Refs über {len(ergebnis)} Quellen. Modell-Antwort (erste 800 Zeichen): {text[:800]!r}")
    return ergebnis, gesehene_refnrs


def bewerte_stelle(job, beschreibung, cfg, notify=print):
    prompt = f"""Bewerte diese Stelle für einen Berufseinsteiger.

Checkliste:
{cfg['CHECKLISTE']}

Punkteskala — sei streng:
1-3: K.O. Kriterien nicht erfüllt
4-5: Möglich aber schwierig
6-7: Gut passend
8-9: Sehr gut passend
10: Perfekte Stelle

Stelle: {job['titel']}
Firma: {job['arbeitgeber']}
Ort: {job['arbeitsort'].get('ort', 'Unbekannt')}
WICHTIG: Wenn Ort nicht Hamburg/Umgebung ist UND Beschreibung kein Homeoffice/Remote/Hybrid erwaehnt -> PUNKTE: 1
Beschreibung: {beschreibung[:1500]}

Antworte NUR so:
PUNKTE: [1-10]
PASSUNG: [ein Satz]
HOMEOFFICE: [Ja/Nein/Hybrid/Keine Angabe]
GEHALT: [Betrag oder Keine Angabe]
GRUND: [ein konkreter Grund warum interessant]"""

    response = _groq_post(
        {'model': 'groq/compound-mini', 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 150},
        cfg
    )
    text = _groq_content(response)
    bew = _parse_bewertung(text)
    if 'PUNKTE' not in bew:
        notify(f"⚠️ Bewertung: PUNKTE nicht erkannt. Modell-Antwort (erste 500 Zeichen): {text[:500]!r}")
    return bew


def _parse_bewertung(text):
    result = {}
    for zeile in text.split('\n'):
        if ':' in zeile:
            key, _, value = zeile.partition(':')
            k = key.strip()
            v = value.strip()
            if k == 'PUNKTE':
                v = v.split('/')[0].strip()
            result[k] = v
    return result


def punkte_int(bew):
    try:
        val = str(bew.get('PUNKTE', 0)).strip()
        return int(re.search(r'\d+', val).group())
    except:
        return 0


def plz_zu_distanz(plz, home_lat, home_lon):
    try:
        r = requests.get(
            f'https://nominatim.openstreetmap.org/search?postalcode={plz}&country=DE&format=json',
            headers={'User-Agent': 'job-search-tool'}, timeout=2
        )
        data = r.json()
        if data:
            lat, lon = float(data[0]['lat']), float(data[0]['lon'])
            dlat = abs(lat - home_lat) * 111
            dlon = abs(lon - home_lon) * 111 * cos(radians(home_lat))
            return round(sqrt(dlat**2 + dlon**2), 1)
    except:
        pass
    return None
