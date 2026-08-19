import requests

def sende_telegram(text):
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    requests.post(url, json={'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'HTML'})

def refnr_zu_url(refnr):
    if refnr.startswith('http'):
        return refnr
    if refnr.startswith('linkedin_'):
        job_id = refnr[len('linkedin_'):]
        return f'https://www.linkedin.com/jobs/view/{job_id}/'
    return f'https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}'