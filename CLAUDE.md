# CLAUDE.md - Job-Such-System

## Dateistruktur
- `job_search.py` — Hauptskript, orchestriert alle Quellen
- `modules/job_config.py` — Konfiguration, lädt Keys aus ~/.openclaw/.env
- `modules/job_scraper.py` — Alle Scraper (parallel via ThreadPoolExecutor)
- `modules/job_filter.py` — Vorfilterung und Deduplizierung
- `modules/job_evaluator.py` — KI-Vorauswahl und Bewertung via Groq
- `modules/job_notifier.py` — Telegram-Versand
- `indeed_scraper.py` — Indeed via Playwright+Stealth
- `heise_scraper.py` — Heise Jobs via SearXNG
- `jsearch_scraper.py` — JSearch via RapidAPI (Quota-Cache in ~/.openclaw/jsearch_quota.json)

## ❌ Niemals automatisch einlesen
- `job_search_seen.json` — Zustandsdatei (resettbar via --reset), nie automatisch überschreiben
- `job_search_ausgeschlossen.json` — dauerhafte Sperrliste (Titel-/Beschreibungs-K.O. + KI-Bewertung <MIN_PUNKTE), bleibt auch bei --reset bestehen, nie automatisch überschreiben
- `*.json` — Alle JSON-Zustandsdateien
- `__pycache__/`

## Regeln
1. Nur Dateien laden die für die aktuelle Aufgabe nötig sind
2. `job_search_seen.json` und `job_search_ausgeschlossen.json` nie automatisch überschreiben

## Beim Pushen
- README.md aktualisieren bei: neuen Quellen, neuen Flags, neuen Abhängigkeiten, strukturellen Änderungen
- Kein "Co-Authored-By" in Commit-Messages — nur natürliche Personen können Autoren sein
