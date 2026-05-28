# Sentry — Job Monitor Bot

A 24/7 automated job hunting bot that scrapes multiple job boards, filters matches using a local LLM, verifies employer ABNs, and sends Telegram notifications for jobs that fit your profile.

## Features

- Monitors Seek, Indeed, Jora, Remotive, and WeWorkRemotely continuously
- Supports jobs in Australia, UK, Europe, Canada, and remote/worldwide
- LLM-powered matching via local Ollama (Qwen 2.5 4B by default)
- Per-job analysis: TL;DR summary, red flag detection, skill gap breakdown
- ABN verification for Australian employers (Playwright headless browser)
- Cross-platform deduplication — one notification per job regardless of how many boards list it
- Multiple concurrent searches with independent keywords and locations
- Interactive filter panel in Telegram (`/filters`) for toggling all preferences at once
- Natural language chat — no slash commands required for most actions
- `/system` command for NUC hardware stats

## Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Install and start Ollama

Download from [ollama.com](https://ollama.com), then pull the default model:

```bash
ollama pull qwen2.5:3b
```

### 3. Set environment variables

```bash
export TELEGRAM_BOT_TOKEN='your_bot_token'
```

Optional overrides:

```bash
export OLLAMA_HOST='http://localhost:11434'   # default
export OLLAMA_MODEL='qwen2.5:3b'             # default
export POLL_INTERVAL_SECONDS='1800'          # default (30 minutes)
```

To make them permanent, add them to `~/.bashrc` or `~/.bash_profile`.

### 4. Run the bot

```bash
python job_bot.py
```

## Running 24/7 on Your NUC

### Option 1: systemd (Recommended)

Create `/etc/systemd/system/sentry.service`:

```ini
[Unit]
Description=Sentry Job Monitor Bot
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/Sentry
Environment="TELEGRAM_BOT_TOKEN=your_bot_token"
Environment="OLLAMA_HOST=http://localhost:11434"
ExecStart=/usr/bin/python3 /home/YOUR_USERNAME/Sentry/job_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable sentry
sudo systemctl start sentry
sudo systemctl status sentry
```

View logs:

```bash
sudo journalctl -u sentry -f
```

### Option 2: screen

```bash
screen -S sentry
python job_bot.py
# Ctrl+A then D to detach
# screen -r sentry to reattach
```

## Bot Commands

| Command | Description |
|---|---|
| `/start` / `/help` | Welcome message and full command list |
| `/search add <keywords> location:<city>` | Add a new job search |
| `/search list` | List all active searches with IDs |
| `/search remove <id>` | Delete a search |
| `/profile` | View all current preferences |
| `/profile salary <min> <max>` | Set annual salary range |
| `/profile type <types...>` | Set job type(s): `full-time`, `part-time`, `contract`, `casual` |
| `/profile arrangement <types...>` | Set work arrangement(s): `remote`, `hybrid`, `onsite` |
| `/profile skills <skill1> <skill2> ...` | Set your skills list |
| `/filters` | Open the interactive filter panel |
| `/system` | NUC hardware stats (CPU, RAM, disk, temps) |

### Natural language

You can also chat with the bot without slash commands:

> "Find me backend developer jobs in Berlin"
> "I want remote Python roles"
> "Set my salary between 90k and 130k"
> "Show me my filters"
> "Remove search 2"

### `/filters` panel

The filter panel lets you toggle all settings from a single Telegram message using inline buttons:

- **Job Type** — Full-time / Part-time / Contract / Casual (multi-select)
- **Arrangement** — Remote / Hybrid / On-site (multi-select)
- **Experience Level** — Entry / Mid / Senior / Lead (multi-select)
- **Posted Within** — 24h / 3 days / 1 week / 1 month (single-select)
- **Edit Salary** — prompts for min/max, accepts `80k 150k` or `80000 150000`
- **Edit Skills** — prompts for a comma or space-separated list
- **Save & Apply** — writes all changes to the database

## How It Works

1. **Add searches** — use `/search add` or natural language to define keywords and location
2. **Set your profile** — salary, job types, arrangements, skills, and experience level via `/profile` or `/filters`
3. **Polling** — every 30 minutes (configurable), the bot scrapes all relevant job boards for each search
4. **Deduplication** — jobs seen before are skipped; the same job on multiple boards is merged into one notification
5. **LLM analysis** — each new job is evaluated by Ollama against your profile:
   - Match decision (yes/no with confidence score)
   - 4-bullet TL;DR summary
   - Red flags (MLM signals, toxic culture phrases, unpaid work, etc.)
   - Skill gaps with priority levels (🔴 required / 🟡 preferred / 🟢 nice-to-have)
6. **ABN verification** — if an ABN is listed in the job description, it is verified against the Australian Business Register before notifying
7. **Notification** — matched jobs are sent to your Telegram chat with the full analysis

## Notification Format

```
*Senior Python Developer*
Company: Acme Corp
Location: Melbourne VIC
Salary: $130,000 – $160,000
Full-time | Hybrid
Posted: 2 days ago
ABN Verified: Acme Corporation Pty Ltd (12345678901)

*Summary:*
  • Builds internal data pipelines using Python and Airflow
  • Tech stack: Python, PostgreSQL, AWS, dbt
  • Hybrid arrangement, 2 days WFH, flexible hours
  • Mid-senior level, 4+ years experience required

*Red Flags:*
  ⚠️ "rockstar developer" language in description

*Skill Gaps:*
  🔴 dbt — listed as required for data transformation work
  🟡 Airflow — used heavily in the role but not marked required

*Links:*
  Seek: https://seek.com.au/job/...
  Indeed: https://au.indeed.com/viewjob?jk=...

_Strong Python and AWS match; hybrid arrangement fits preference._
```

## Supported Locations

The bot automatically routes to the correct job board domain based on location:

- **Australia** — Seek + Indeed AU + Jora AU (Melbourne, Sydney, Brisbane, Perth, Adelaide, etc.)
- **UK / Ireland** — Indeed UK/IE + Jora UK/IE
- **Europe** — Indeed + Jora per country (Germany, France, Netherlands, Sweden, Norway, Denmark, Belgium, Switzerland, Austria, Poland, Portugal, Finland, Spain, Italy)
- **Canada** — Indeed CA + Jora CA
- **Remote / Worldwide** — Remotive API + WeWorkRemotely + Indeed global

## File Structure

```
Sentry/
├── job_bot.py              # Main entry point — Telegram bot + background thread
├── job_storage.py          # SQLite persistence (profiles, searches, seen jobs)
├── job_matcher.py          # Ollama LLM: job analysis + natural language intent parsing
├── deduplicator.py         # Cross-platform job deduplication (MD5 keying)
├── abn_verifier.py         # Playwright ABN lookup on abn.business.gov.au
├── system_monitor.py       # /system command — CPU, RAM, disk, network, temps
├── scrapers/
│   ├── __init__.py         # Location-aware scraper routing
│   ├── base_scraper.py     # Shared httpx session, retry/backoff, rate limiting
│   ├── seek_scraper.py     # seek.com.au
│   ├── indeed_scraper.py   # Indeed (30+ country domains)
│   ├── jora_scraper.py     # Jora (AU + major EU/CA domains)
│   └── remote_scraper.py   # Remotive API + WeWorkRemotely
├── requirements.txt
├── jobs.db                 # SQLite database (auto-created on first run)
└── README.md
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | required | Bot token from @BotFather |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API base URL |
| `OLLAMA_MODEL` | `qwen2.5:3b` | Model to use for matching and intent parsing |
| `POLL_INTERVAL_SECONDS` | `1800` | How often to check for new jobs (seconds) |

## Troubleshooting

**Bot doesn't respond**
- Check it's running: `sudo systemctl status sentry`
- Verify `TELEGRAM_BOT_TOKEN` is set correctly

**No jobs found**
- Confirm Ollama is running: `curl http://localhost:11434/api/tags`
- Check logs for scraper errors: `sudo journalctl -u sentry -n 100`
- Job boards may have changed their HTML — check scraper log output

**LLM matching unavailable**
- Start Ollama: `ollama serve`
- Confirm the model is downloaded: `ollama list`
- Pull it if missing: `ollama pull qwen2.5:3b`

**ABN verification fails**
- Run `playwright install chromium` if not done after install
- The ABN registry site may be temporarily unavailable — the job is skipped rather than sent unverified

## Resource Usage

Typical usage on an Intel N95 NUC:

- CPU: <1% at idle, brief spike during LLM inference (~30s per job)
- RAM: ~200–400MB (bot + Ollama model loaded)
- Network: Minimal scraping traffic every 30 minutes
- Disk: `jobs.db` grows slowly (a few KB per job stored)
