# Sentry — Job Monitor Bot

## Project Overview

Sentry is a Python-based Telegram bot that continuously monitors Seek.com.au, Indeed.com.au, and Jora.com for new job listings. When a new job matches the user's profile (salary, job type, arrangement, skills), it uses a local Ollama LLM (Qwen 3.5 4B) to evaluate the fit, optionally verifies the employer's ABN, deduplicates across platforms, and sends a Telegram notification with job links.

## Architecture

```
job_bot.py                   # Entry point — bot setup, command handlers, background thread
job_storage.py               # SQLite persistence (profiles, searches, seen_jobs)
job_matcher.py               # Local Ollama LLM matching (single-shot per job)
abn_verifier.py              # Playwright headless ABN lookup on abn.business.gov.au
deduplicator.py              # MD5-based cross-platform job deduplication
scrapers/
  __init__.py                # Exports ALL_SCRAPERS list
  base_scraper.py            # httpx client, retry logic, abstract interface
  seek_scraper.py            # seek.com.au
  indeed_scraper.py          # au.indeed.com
  jora_scraper.py            # au.jora.com
system_monitor.py            # NUC hardware stats (psutil) — unchanged from original
```

## Data Flow

1. User sets profile preferences via `/profile` commands
2. User adds job searches via `/search add`
3. Background daemon thread (`monitor_jobs`) polls all three scrapers every 30 min
4. Each scraped job is dedup-checked against `jobs.db`
5. New jobs are saved, then evaluated by the local LLM
6. If matched: check for ABN in listing → verify if present → send Telegram notification
7. Cross-platform dedup: if same job appears on multiple platforms, `platforms` field accumulates all URLs; notification shows all links

## Threading Model

Two threads:
1. Main thread: `python-telegram-bot` async polling loop
2. `monitor_jobs` daemon thread: scraping + matching loop (sync, uses direct HTTP for Telegram)

Background thread uses direct HTTP POST to Telegram (not async), mirroring the original project's pattern.

## Database Schema (`jobs.db`)

Three tables managed by `job_storage.py`:

| Table | Purpose |
|---|---|
| `profiles` | Per-user preferences: salary range, job types, arrangements, skills |
| `searches` | Active job searches: keywords + location, per chat_id |
| `seen_jobs` | All scraped jobs with dedup key, match status, notification status, platform links |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | required | Bot API token |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2.5:4b` | LLM model name |
| `POLL_INTERVAL_SECONDS` | `1800` | Scrape interval (seconds) |

## Telegram Commands

### Search Management
| Command | Description |
|---|---|
| `/search add <keywords> location:<city>` | Add a new job search |
| `/search list` | List active searches with IDs |
| `/search remove <id>` | Delete a search |

### Profile Preferences
| Command | Description |
|---|---|
| `/profile` | View current preferences |
| `/profile salary <min> <max>` | Set annual salary range |
| `/profile type <types...>` | Set job types (full-time, part-time, contract, casual) |
| `/profile arrangement <types...>` | Set arrangements (onsite, hybrid, remote) |
| `/profile skills <skills...>` | Set skills/keywords |

### System
| Command | Description |
|---|---|
| `/system` | NUC hardware stats (CPU, RAM, disk, network, temp) |

## Scraper Strategy

All scrapers use `httpx` (sync) + `BeautifulSoup4`. Each scraper:
- Fetches the last 3 days of results only
- Fetches individual job detail pages for full description and ABN detection
- Applies 2-second delay between requests
- Retries up to 3 times with exponential backoff
- Caps at 5 pages per search

## LLM Matching

Single-shot prompt per job, no conversation history. Profile + search query + job listing (first 1500 chars of description) injected into prompt. Model must return JSON: `{"match": bool, "confidence": float, "reason": string}`. A job is accepted if `match=true` and `confidence >= 0.6`.

## ABN Verification

Only triggered when the regex `\bABN:?\s*(\d{2}\s?\d{3}\s?\d{3}\s?\d{3})\b` matches in the job description. Uses Playwright (headless Chromium) to check `abn.business.gov.au`. If ABN is listed but status is not "Active" → job is silently rejected (no notification). If no ABN in listing → verification is skipped and notification proceeds normally.

## Deduplication

`deduplicator.py:make_dedup_key(title, company, location)` generates an MD5 hash of the normalised `company|title|location` string. Normalisation strips business suffixes (Pty, Ltd, Inc), lowercases, removes punctuation. When the same key is seen from a new platform, the `platforms` JSON field in `seen_jobs` is updated — no re-notification.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
export TELEGRAM_BOT_TOKEN='your_token'
# Ensure Ollama is running with your model loaded
python job_bot.py
```

## Systemd Service (NUC)

```ini
[Unit]
Description=Sentry Job Monitor Bot
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/Sentry
Environment="TELEGRAM_BOT_TOKEN=your_token"
Environment="OLLAMA_HOST=http://localhost:11434"
Environment="OLLAMA_MODEL=qwen2.5:4b"
ExecStart=/usr/bin/python3 /home/YOUR_USERNAME/Sentry/job_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```
