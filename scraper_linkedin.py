import requests, json, json, os, base64, math, time, sys, re

def suche_linkedin():
    """Sucht Stellen via LinkedIn API."""
    try:
        from linkedin_api import Linkedin
        import requests as req

        with open(os.path.expanduser('~/.openclaw/openclaw.json')) as f:
            _c = json.load(f)

        session = req.Session()
        session.cookies.set('li_at', _c['env'].get('LINKEDIN_LI_AT', ''))
        session.cookies.set('JSESSIONID', _c['env'].get('LINKEDIN_JSESSIONID', ''))

        api = Linkedin('', '', cookies=session.cookies)

        SUCHEN_LI = [
            'Künstliche Intelligenz Junior',
            'Python Automatisierung Junior',
            'Junior Data Analyst',
            'Junior Produktmanager Digital',
            'KI Berater Junior',
        ]

        alle_job_ids = {}
        for begriff in SUCHEN_LI:
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
                if job_id not in alle_job_ids:
                    alle_job_ids[job_id] = True
            time.sleep(1)

        stellen = []
        for job_id in list(alle_job_ids.keys())[:15]:
            try:
                details = api.get_job(job_id)
                firma = details.get('companyDetails', {})
                    .get('com.linkedin.voyager.deco.jobs.web.shared.WebCompactJobPostingCompany', {})
                    .get('companyResolutionResult', {})
                    .get('name', '')
                beschreibung = details.get('description', {})
                    .get('text', '')
                ort = details.get('formattedLocation', '')
                # Nur Hamburg/Umgebung oder Remote
                ist_hamburg = 'hamburg' in ort.lower() or ort == ''
                ist_remote = any(w in beschreibung.lower() for w in ['remote', 'homeoffice', 'home office', '100% mobil'])
                if not ist_hamburg and not ist_remote:
                    continue
                stellen.append({
                    'refnr': f'linkedin_{job_id}',
                    'titel': details.get('title', ''),
                    'arbeitgeber': firma,
                    'arbeitsort': {'ort': ort or 'Hamburg', 'entfernung': 0},
                    'beschreibung': beschreibung,
                    'quelle': 'linkedin'
                })
                time.sleep(0.5)
            except Exception as e:
                print(f"LinkedIn Job Fehler: {e}")
        return stellen
    except Exception as e:
        print(f"LinkedIn Fehler: {e}")
        return []