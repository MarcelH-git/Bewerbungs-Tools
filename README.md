# job-application-tools

Automated job application system for the German job market.

## Tools

### job_search.py
Searches for new job listings daily across multiple platforms simultaneously.

- Sources: Bundesagentur für Arbeit API, Stepstone, LinkedIn, Indeed, Heise Jobs, JSearch (RapidAPI)
- All scrapers run in parallel — total runtime ~40–60s
- Automatic AI scoring of listings based on a candidate profile (Groq)
- Telegram notifications with status updates
- Filters for junior-level positions and remote/Hamburg
- Deduplication across all sources
- Lock file prevents parallel execution
- JSearch quota cache: automatically reserves API calls for the cron job

Logic is split into `modules/`:
- `job_config.py` — configuration and constants
- `job_scraper.py` — scraping all sources
- `job_filter.py` — pre-filtering (title, location, description, deduplication)
- `job_evaluator.py` — AI scoring and pre-selection via Groq
- `job_notifier.py` — Telegram dispatch

Flags:
- `--no-verbose` — suppresses Telegram status messages (for cron job)
- `--reset` — clears the list of seen jobs
- `--groq-status` — shows when the Groq daily token limit (TPD) was last exhausted on all keys, and when it should reset (~24h rolling window)

### anschreiben_generator.py
Generates personalised cover letters from job listings.

- Fetches the job description directly from the respective platform
- Fixed template with automatically extracted job-specific sentence
- Groq API key and LinkedIn cookies from environment variables (`GROQ_API_KEY`, `LINKEDIN_LI_AT`, `LINKEDIN_JSESSIONID`)
- Private data (name, address etc.) is injected via a protected local resolver — never stored in plain text in the script

### anschreiben_bot.py
Non-interactive wrapper for automated bot usage (argparse).

- Private data is loaded via `sudo -u private_data python3 /opt/openclaw/private_resolver.py`
- The finished cover letter is only saved as a file, never written to stdout

### indeed_scraper.py
Indeed scraper via Playwright + Stealth (Cloudflare bypass).

### heise_scraper.py
Heise Jobs scraper via SearX.
