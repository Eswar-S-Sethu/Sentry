"""
Sentry Job Monitor Bot
Main entry point — Telegram bot with job search management,
background polling across Seek, Indeed, Jora, and remote boards,
LLM-assisted matching via local Ollama, and ABN verification.
"""

import logging
import os
import re
import time
from threading import Thread

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from abn_verifier import verify_abn
from deduplicator import make_dedup_key
from job_matcher import analyse_job, check_ollama_available, parse_intent
from job_storage import (
    add_search, get_profile, get_searches, init_db, insert_job, job_exists,
    mark_job_matched, mark_job_notified, remove_search, update_job_analysis,
    update_job_platforms, update_search_last_run, upsert_profile,
)
from scrapers import get_scrapers_for_location
from system_monitor import format_system_stats, get_system_stats

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

POLL_INTERVAL = int(os.getenv('POLL_INTERVAL_SECONDS', '1800'))  # 30 min default

# ---------------------------------------------------------------------------
# In-memory session state (keyed by chat_id)
# ---------------------------------------------------------------------------

# Carries partial params between clarification turns for natural-language search setup
pending_context: dict[int, dict] = {}

# Holds the working copy of filter settings while the user edits the filter panel
filter_sessions: dict[int, dict] = {}

# Marks chats that are expecting free-text input (salary or skills) within a filter flow
awaiting_filter_input: dict[int, dict] = {}

# ---------------------------------------------------------------------------
# Filter panel constants
# ---------------------------------------------------------------------------

_DAYS_LABELS = {1: '24 hours', 3: '3 days', 7: '1 week', 30: '1 month'}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _send_message(bot_token: str, chat_id: int, text: str):
    """Direct HTTP Telegram message — safe to call from background threads."""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(
            url,
            json={'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.error(f"Telegram send failed: {resp.status_code} — {resp.text[:200]}")
    except Exception as e:
        logger.error(f"Telegram send error: {e}")


def _format_job_notification(job: dict, analysis: dict, abn_result: dict | None) -> str:
    """Build the Telegram notification message for a matched job."""
    platforms = job.get('platforms', {})
    lines = []

    # --- Header ---
    lines.append(f"*{job.get('title', 'Job')}*")
    company = job.get('company', '')
    location = job.get('location', '')
    if company:
        lines.append(f"Company: {company}")
    if location:
        lines.append(f"Location: {location}")

    salary = job.get('salary_text', '')
    if salary:
        lines.append(f"Salary: {salary}")

    meta = ' | '.join(filter(None, [job.get('job_type', ''), job.get('arrangement', '')]))
    if meta:
        lines.append(meta)

    posted = job.get('posted_date', '')
    if posted:
        lines.append(f"Posted: {posted}")

    if abn_result and abn_result.get('valid'):
        lines.append(f"ABN Verified: {abn_result['entity_name']} ({abn_result['abn_formatted']})")

    # --- Summary ---
    summary = analysis.get('summary') or []
    if summary:
        lines.append('')
        lines.append('*Summary:*')
        for bullet in summary:
            lines.append(f"  • {bullet}")

    # --- Red Flags ---
    red_flags = analysis.get('red_flags') or []
    if red_flags:
        lines.append('')
        lines.append('*Red Flags:*')
        for flag in red_flags:
            lines.append(f"  ⚠️ {flag}")

    # --- Skill Gaps ---
    skill_gaps = analysis.get('skill_gaps') or []
    if skill_gaps:
        lines.append('')
        lines.append('*Skill Gaps:*')
        priority_icon = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}
        for gap in skill_gaps:
            skill = gap.get('skill', '')
            priority = gap.get('priority', 'medium').lower()
            why = gap.get('why', '')
            icon = priority_icon.get(priority, '•')
            lines.append(f"  {icon} {skill} — {why}")

    # --- Links ---
    lines.append('')
    if platforms:
        lines.append('*Links:*')
        for platform, url in platforms.items():
            lines.append(f"  {platform.title()}: {url}")

    # --- Match reason ---
    reason = analysis.get('reason', '')
    if reason:
        lines.append('')
        lines.append(f"_{reason}_")

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Filter panel — text + keyboard builders
# ---------------------------------------------------------------------------

def _build_filter_text(session: dict) -> str:
    """Build the text portion of the filter panel message."""
    salary_min = session.get('salary_min')
    salary_max = session.get('salary_max')
    if salary_min and salary_max:
        salary_str = f"${salary_min:,.0f} – ${salary_max:,.0f}/yr"
    elif salary_min:
        salary_str = f"from ${salary_min:,.0f}/yr"
    elif salary_max:
        salary_str = f"up to ${salary_max:,.0f}/yr"
    else:
        salary_str = "not set"

    skills = session.get('skills') or []
    if skills:
        skills_str = ', '.join(skills[:5])
        if len(skills) > 5:
            skills_str += f' +{len(skills) - 5} more'
    else:
        skills_str = 'not set'

    days = session.get('posted_within_days', 3)
    days_str = _DAYS_LABELS.get(days, f'{days} days')

    job_types = session.get('job_types') or []
    arrangements = session.get('arrangements') or []
    exp_levels = session.get('experience_levels') or []

    return (
        "⚙️ *Filter Settings*\n\n"
        f"Salary: {salary_str}\n"
        f"Skills: {skills_str}\n"
        f"Posted within: {days_str}\n"
        f"Job types: {', '.join(job_types) or 'any'}\n"
        f"Arrangements: {', '.join(arrangements) or 'any'}\n"
        f"Experience: {', '.join(exp_levels) or 'any'}\n\n"
        "_Toggle options below, then tap Save & Apply._"
    )


def _build_filter_keyboard(session: dict) -> InlineKeyboardMarkup:
    """Build the inline keyboard for the filter panel."""

    def toggle_btn(label: str, value: str, collection: list, cb: str) -> InlineKeyboardButton:
        icon = '✅ ' if value in (collection or []) else ''
        return InlineKeyboardButton(f"{icon}{label}", callback_data=cb)

    def day_btn(label: str, days_val: int, current: int) -> InlineKeyboardButton:
        icon = '▶ ' if days_val == current else ''
        return InlineKeyboardButton(f"{icon}{label}", callback_data=f'fm:set:days:{days_val}')

    job_types = session.get('job_types') or []
    arrangements = session.get('arrangements') or []
    exp_levels = session.get('experience_levels') or []
    days = session.get('posted_within_days', 3)

    keyboard = [
        [InlineKeyboardButton('— Job Type —', callback_data='fm:noop')],
        [
            toggle_btn('Full-time', 'full-time', job_types, 'fm:toggle:type:full-time'),
            toggle_btn('Part-time', 'part-time', job_types, 'fm:toggle:type:part-time'),
            toggle_btn('Contract',  'contract',  job_types, 'fm:toggle:type:contract'),
            toggle_btn('Casual',    'casual',    job_types, 'fm:toggle:type:casual'),
        ],
        [InlineKeyboardButton('— Arrangement —', callback_data='fm:noop')],
        [
            toggle_btn('Remote',  'remote',  arrangements, 'fm:toggle:arr:remote'),
            toggle_btn('Hybrid',  'hybrid',  arrangements, 'fm:toggle:arr:hybrid'),
            toggle_btn('On-site', 'on-site', arrangements, 'fm:toggle:arr:on-site'),
        ],
        [InlineKeyboardButton('— Experience Level —', callback_data='fm:noop')],
        [
            toggle_btn('Entry',  'entry',  exp_levels, 'fm:toggle:exp:entry'),
            toggle_btn('Mid',    'mid',    exp_levels, 'fm:toggle:exp:mid'),
            toggle_btn('Senior', 'senior', exp_levels, 'fm:toggle:exp:senior'),
            toggle_btn('Lead',   'lead',   exp_levels, 'fm:toggle:exp:lead'),
        ],
        [InlineKeyboardButton('— Posted Within —', callback_data='fm:noop')],
        [
            day_btn('24h',    1,  days),
            day_btn('3 days', 3,  days),
            day_btn('1 week', 7,  days),
            day_btn('1 month', 30, days),
        ],
        [InlineKeyboardButton('✏️ Edit Salary', callback_data='fm:edit:salary')],
        [InlineKeyboardButton('✏️ Edit Skills', callback_data='fm:edit:skills')],
        [
            InlineKeyboardButton('💾 Save & Apply', callback_data='fm:save'),
            InlineKeyboardButton('❌ Cancel',        callback_data='fm:cancel'),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# Background monitoring thread
# ---------------------------------------------------------------------------

def monitor_jobs(bot_token: str):
    """
    Background daemon thread.
    Polls all job boards every POLL_INTERVAL seconds for each active search.
    """
    logger.info("Job monitoring thread started")

    while True:
        try:
            searches = get_searches(active_only=True)
            if not searches:
                logger.info("No active searches. Sleeping.")
                time.sleep(POLL_INTERVAL)
                continue

            logger.info(f"Running job poll — {len(searches)} active search(es)")

            for search in searches:
                chat_id   = search['chat_id']
                keywords  = search['keywords']
                location  = search['location']
                search_id = search['id']
                profile   = get_profile(chat_id)
                days      = profile.get('posted_within_days') or 3

                for ScraperClass in get_scrapers_for_location(location):
                    scraper = ScraperClass()
                    try:
                        jobs = scraper.search(keywords, location, days=days)
                    except Exception as e:
                        logger.error(f"[{scraper.platform_name}] Search error: {e}")
                        jobs = []
                    finally:
                        scraper.close()

                    for job_data in jobs:
                        platform = scraper.platform_name
                        url = job_data.get('url', '')
                        dedup_key = make_dedup_key(
                            job_data.get('title', ''),
                            job_data.get('company', ''),
                            job_data.get('location', ''),
                        )

                        if job_exists(dedup_key):
                            update_job_platforms(dedup_key, platform, url)
                            continue

                        # New job — persist it
                        job_data['dedup_key'] = dedup_key
                        job_data['platforms'] = {platform: url}
                        job_data['search_id'] = search_id
                        insert_job(job_data)

                        # Combined LLM analysis: match + summary + red flags + skill gaps
                        analysis = analyse_job(job_data, search, profile)
                        update_job_analysis(dedup_key, analysis)

                        if not analysis['match']:
                            mark_job_matched(dedup_key, matched=-1)
                            continue

                        mark_job_matched(dedup_key, matched=1)

                        # ABN verification (only if ABN found in listing)
                        abn_result = None
                        if job_data.get('abn'):
                            abn_result = verify_abn(job_data['abn'])
                            if not abn_result.get('valid'):
                                logger.info(
                                    f"ABN check failed for '{job_data.get('title')}' "
                                    f"({abn_result.get('status')}) — skipping notification"
                                )
                                mark_job_matched(dedup_key, matched=-1)
                                continue

                        notification = _format_job_notification(job_data, analysis, abn_result)
                        _send_message(bot_token, chat_id, notification)
                        mark_job_notified(dedup_key)
                        logger.info(
                            f"Notified chat {chat_id} about: {job_data.get('title')} "
                            f"@ {job_data.get('company')} "
                            f"flags={len(analysis['red_flags'])} gaps={len(analysis['skill_gaps'])}"
                        )

                update_search_last_run(search_id)

        except Exception as e:
            logger.error(f"Error in monitor_jobs loop: {e}")

        logger.info(f"Poll complete. Next poll in {POLL_INTERVAL // 60} minutes.")
        time.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Filter panel handlers
# ---------------------------------------------------------------------------

async def cmd_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open the interactive filter panel populated from the user's current profile."""
    chat_id = update.effective_chat.id
    profile = get_profile(chat_id)

    filter_sessions[chat_id] = {
        'job_types':          list(profile.get('job_types') or []),
        'arrangements':       list(profile.get('arrangements') or []),
        'experience_levels':  list(profile.get('experience_levels') or []),
        'posted_within_days': profile.get('posted_within_days') or 3,
        'salary_min':         profile.get('salary_min'),
        'salary_max':         profile.get('salary_max'),
        'skills':             list(profile.get('skills') or []),
    }

    session = filter_sessions[chat_id]
    await update.message.reply_text(
        text=_build_filter_text(session),
        reply_markup=_build_filter_keyboard(session),
        parse_mode='Markdown',
    )


async def handle_filter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses inside the filter panel."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    data = query.data  # e.g. 'fm:toggle:type:full-time'

    if data == 'fm:noop':
        return

    session = filter_sessions.get(chat_id)
    if not session:
        await query.edit_message_text(
            "This filter panel has expired. Use /filters to open a new one."
        )
        return

    parts = data.split(':')
    action = parts[1]

    if action == 'toggle':
        category = parts[2]             # 'type', 'arr', 'exp'
        value = ':'.join(parts[3:])     # preserves hyphens, e.g. 'on-site'

        key_map = {'type': 'job_types', 'arr': 'arrangements', 'exp': 'experience_levels'}
        key = key_map.get(category)
        if not key:
            return

        current = list(session.get(key) or [])
        if value in current:
            current.remove(value)
        else:
            current.append(value)
        session[key] = current

        await query.edit_message_text(
            text=_build_filter_text(session),
            reply_markup=_build_filter_keyboard(session),
            parse_mode='Markdown',
        )

    elif action == 'set' and parts[2] == 'days':
        session['posted_within_days'] = int(parts[3])
        await query.edit_message_text(
            text=_build_filter_text(session),
            reply_markup=_build_filter_keyboard(session),
            parse_mode='Markdown',
        )

    elif action == 'edit':
        field = parts[2]  # 'salary' or 'skills'
        awaiting_filter_input[chat_id] = {'field': field}

        if field == 'salary':
            prompt = (
                "Enter your salary range (annual minimum and maximum):\n"
                "Example: `80000 150000` or `80k 150k`"
            )
        else:
            prompt = (
                "Enter your skills, separated by commas or spaces:\n"
                "Example: `Python Django PostgreSQL AWS`"
            )

        await query.edit_message_text(
            text=f"⚙️ *Edit {field.title()}*\n\n{prompt}",
            parse_mode='Markdown',
        )

    elif action == 'save':
        upsert_profile(
            chat_id,
            job_types=session.get('job_types'),
            arrangements=session.get('arrangements'),
            experience_levels=session.get('experience_levels'),
            posted_within_days=session.get('posted_within_days'),
            salary_min=session.get('salary_min'),
            salary_max=session.get('salary_max'),
            skills=session.get('skills'),
        )
        filter_sessions.pop(chat_id, None)
        await query.edit_message_text(
            "Filters saved! The bot will use these settings for all future job searches."
        )

    elif action == 'cancel':
        filter_sessions.pop(chat_id, None)
        await query.edit_message_text("Filter changes cancelled — no settings were changed.")


async def _handle_filter_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle free-text input when the user is typing salary or skills
    in response to an 'Edit' button in the filter panel.
    """
    chat_id = update.effective_chat.id
    message = update.message.text.strip()
    waiting = awaiting_filter_input.pop(chat_id, {})
    field = waiting.get('field')

    session = filter_sessions.get(chat_id)
    if not session:
        await update.message.reply_text(
            "The filter session expired. Use /filters to start again."
        )
        return

    if field == 'salary':
        # Match integers, floats, and values ending in 'k'
        numbers = re.findall(r'[\d,]+(?:\.\d+)?k?', message, re.IGNORECASE)
        parsed = []
        for n in numbers[:2]:
            n = n.replace(',', '')
            if n.lower().endswith('k'):
                parsed.append(float(n[:-1]) * 1000)
            else:
                try:
                    parsed.append(float(n))
                except ValueError:
                    pass

        if len(parsed) >= 2:
            session['salary_min'] = min(parsed)
            session['salary_max'] = max(parsed)
            intro = f"Salary set to ${session['salary_min']:,.0f} – ${session['salary_max']:,.0f}/yr."
        elif len(parsed) == 1:
            session['salary_min'] = parsed[0]
            session['salary_max'] = None
            intro = f"Salary minimum set to ${session['salary_min']:,.0f}/yr."
        else:
            awaiting_filter_input[chat_id] = waiting  # restore so the next message is also caught
            await update.message.reply_text(
                "I couldn't read that salary. Please enter two numbers, "
                "e.g. `80000 150000` or `80k 150k`.",
                parse_mode='Markdown',
            )
            return

    elif field == 'skills':
        skills = [s.strip() for s in re.split(r'[,\s]+', message) if s.strip()]
        session['skills'] = skills
        intro = f"Skills updated: {', '.join(skills)}."

    else:
        return

    await update.message.reply_text(
        text=f"{intro} Here's your updated filter panel:\n\n{_build_filter_text(session)}",
        reply_markup=_build_filter_keyboard(session),
        parse_mode='Markdown',
    )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "*Sentry — Job Monitor Bot*\n\n"
        "*Search Management:*\n"
        "`/search add <keywords> location:<city>` — add a job search\n"
        "`/search list` — list all your searches\n"
        "`/search remove <id>` — delete a search\n\n"
        "*Profile & Filters:*\n"
        "`/profile` — view your current preferences\n"
        "`/profile salary <min> <max>` — set annual salary range\n"
        "`/profile type <full-time|part-time|contract|casual>` — job type(s)\n"
        "`/profile arrangement <onsite|hybrid|remote>` — work arrangement(s)\n"
        "`/profile skills <skill1> <skill2> ...` — skills/keywords\n"
        "`/filters` — open the interactive filter panel\n\n"
        "*System:*\n"
        "`/system` — NUC hardware stats\n\n"
        "_Tip: Set your profile first, then add searches. "
        "Use /filters for a visual editor that covers all settings at once._"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search add|list|remove commands."""
    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "`/search add <keywords> location:<city>`\n"
            "`/search list`\n"
            "`/search remove <id>`",
            parse_mode='Markdown',
        )
        return

    subcommand = context.args[0].lower()
    chat_id = update.effective_chat.id

    # /search list
    if subcommand == 'list':
        searches = get_searches(chat_id=chat_id, active_only=True)
        if not searches:
            await update.message.reply_text(
                "You have no active searches. Use `/search add` to create one.",
                parse_mode='Markdown',
            )
            return

        lines = ["*Your active searches:*\n"]
        for s in searches:
            last = s.get('last_run', 'never')
            if last and last != 'never':
                last = last[:16].replace('T', ' ')
            lines.append(f"*#{s['id']}* — {s['keywords']} in {s['location']}")
            lines.append(f"   Last checked: {last}\n")
        await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')
        return

    # /search remove <id>
    if subcommand == 'remove':
        if len(context.args) < 2:
            await update.message.reply_text("Usage: `/search remove <id>`", parse_mode='Markdown')
            return
        try:
            search_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("Search ID must be a number.")
            return
        if remove_search(search_id, chat_id):
            await update.message.reply_text(f"Search #{search_id} removed.")
        else:
            await update.message.reply_text(f"No search #{search_id} found.")
        return

    # /search add <keywords> location:<city>
    if subcommand == 'add':
        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage: `/search add <keywords> location:<city>`\n"
                "Example: `/search add Software Engineer location:Melbourne`",
                parse_mode='Markdown',
            )
            return

        raw = ' '.join(context.args[1:])

        loc_match = re.search(r'location:(\S+)', raw, re.IGNORECASE)
        if loc_match:
            location = loc_match.group(1).replace('-', ' ').title()
            keywords = raw[:loc_match.start()].strip()
        else:
            parts = raw.rsplit(' ', 1)
            if len(parts) == 2:
                keywords, location = parts[0].strip(), parts[1].strip().title()
            else:
                await update.message.reply_text(
                    "Please include a location.\n"
                    "Example: `/search add Software Engineer location:Melbourne`",
                    parse_mode='Markdown',
                )
                return

        if not keywords:
            await update.message.reply_text("Please provide job keywords.")
            return

        search_id = add_search(chat_id, keywords, location)
        await update.message.reply_text(
            f"Search #{search_id} added:\n"
            f"*{keywords}* in *{location}*\n\n"
            f"The bot will check every {POLL_INTERVAL // 60} minutes.",
            parse_mode='Markdown',
        )
        return

    await update.message.reply_text(
        "Unknown subcommand. Use: `add`, `list`, or `remove`.",
        parse_mode='Markdown',
    )


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /profile [subcommand args...]"""
    chat_id = update.effective_chat.id

    # /profile — view current profile
    if not context.args:
        profile = get_profile(chat_id)
        salary_min = profile.get('salary_min')
        salary_max = profile.get('salary_max')

        if salary_min and salary_max:
            salary_str = f"${salary_min:,.0f} – ${salary_max:,.0f} per year"
        elif salary_min:
            salary_str = f"At least ${salary_min:,.0f} per year"
        elif salary_max:
            salary_str = f"Up to ${salary_max:,.0f} per year"
        else:
            salary_str = 'Not set'

        types_str = ', '.join(profile.get('job_types') or []) or 'Not set'
        arr_str   = ', '.join(profile.get('arrangements') or []) or 'Not set'
        exp_str   = ', '.join(profile.get('experience_levels') or []) or 'Not set'
        skills_str = ', '.join(profile.get('skills') or []) or 'Not set'
        days = profile.get('posted_within_days') or 3
        days_str = _DAYS_LABELS.get(days, f'{days} days')

        msg = (
            "*Your Profile*\n\n"
            f"Salary: {salary_str}\n"
            f"Job types: {types_str}\n"
            f"Arrangements: {arr_str}\n"
            f"Experience levels: {exp_str}\n"
            f"Skills: {skills_str}\n"
            f"Posted within: {days_str}\n\n"
            "_Use /filters to edit everything visually._"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')
        return

    subcommand = context.args[0].lower()

    # /profile salary <min> <max>
    if subcommand == 'salary':
        if len(context.args) < 3:
            await update.message.reply_text(
                "Usage: `/profile salary <min> <max>`\nExample: `/profile salary 80000 150000`",
                parse_mode='Markdown',
            )
            return
        try:
            sal_min = float(context.args[1].replace(',', '').replace('k', '000').replace('K', '000'))
            sal_max = float(context.args[2].replace(',', '').replace('k', '000').replace('K', '000'))
        except ValueError:
            await update.message.reply_text("Please provide numeric salary values.")
            return
        if sal_min >= sal_max:
            await update.message.reply_text("Minimum salary must be less than maximum.")
            return
        upsert_profile(chat_id, salary_min=sal_min, salary_max=sal_max)
        await update.message.reply_text(
            f"Salary range set: ${sal_min:,.0f} – ${sal_max:,.0f} per year",
            parse_mode='Markdown',
        )
        return

    # /profile type <types...>
    if subcommand == 'type':
        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage: `/profile type <type(s)>`\n"
                "Valid: `full-time`, `part-time`, `contract`, `casual`\n"
                "Example: `/profile type full-time contract`",
                parse_mode='Markdown',
            )
            return
        valid = {'full-time', 'part-time', 'contract', 'casual', 'permanent'}
        types = [t.lower() for t in context.args[1:] if t.lower() in valid]
        if not types:
            await update.message.reply_text(f"No valid types provided. Valid: {', '.join(sorted(valid))}")
            return
        upsert_profile(chat_id, job_types=types)
        await update.message.reply_text(f"Job types set: {', '.join(types)}")
        return

    # /profile arrangement <arrangements...>
    if subcommand == 'arrangement':
        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage: `/profile arrangement <type(s)>`\n"
                "Valid: `onsite`, `hybrid`, `remote`\n"
                "Example: `/profile arrangement hybrid remote`",
                parse_mode='Markdown',
            )
            return
        valid = {'onsite', 'hybrid', 'remote', 'on-site'}
        arrangements = [a.lower() for a in context.args[1:] if a.lower() in valid]
        if not arrangements:
            await update.message.reply_text(
                f"No valid arrangements provided. Valid: {', '.join(sorted(valid))}"
            )
            return
        upsert_profile(chat_id, arrangements=arrangements)
        await update.message.reply_text(f"Arrangements set: {', '.join(arrangements)}")
        return

    # /profile skills <skills...>
    if subcommand == 'skills':
        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage: `/profile skills <skill1> <skill2> ...`\n"
                "Example: `/profile skills Python Django AWS`",
                parse_mode='Markdown',
            )
            return
        skills = context.args[1:]
        upsert_profile(chat_id, skills=skills)
        await update.message.reply_text(f"Skills set: {', '.join(skills)}")
        return

    await update.message.reply_text(
        "Unknown profile setting. Options: `salary`, `type`, `arrangement`, `skills`",
        parse_mode='Markdown',
    )


async def cmd_system(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show NUC system stats."""
    try:
        checking = await update.message.reply_text("Gathering system stats...")
        stats = get_system_stats()
        msg = format_system_stats(stats)
        await checking.edit_text(msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in /system: {e}")
        await update.message.reply_text(f"Error: {e}")


async def cmd_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle plain text messages (no slash command).
    Uses Ollama to parse intent and dispatch to the appropriate action.
    """
    chat_id = update.effective_chat.id
    message = update.message.text.strip()

    if not message:
        return

    # If the user is mid-flow entering salary or skills for the filter panel,
    # intercept here before hitting the LLM.
    if chat_id in awaiting_filter_input:
        await _handle_filter_text_input(update, context)
        return

    # Show typing indicator while LLM thinks
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    profile = get_profile(chat_id)
    searches = get_searches(chat_id=chat_id, active_only=True)

    pending = pending_context.get(chat_id, {})
    intent = parse_intent(message, profile, searches, pending_partial=pending)

    action = intent.get('action', 'chat')
    params = intent.get('params', {})
    llm_reply = intent.get('reply', '')

    # --- needs_clarification ---
    if action == 'needs_clarification':
        pending_context[chat_id] = params.get('partial_params', pending)
        await update.message.reply_text(llm_reply or "Could you give me a bit more detail?")
        return

    pending_context.pop(chat_id, None)

    # --- show_filters ---
    if action == 'show_filters':
        await cmd_filters(update, context)
        return

    # --- search_add ---
    if action == 'search_add':
        keywords = params.get('keywords', '').strip()
        location = params.get('location', '').strip()
        if keywords and location:
            search_id = add_search(chat_id, keywords, location)
            await update.message.reply_text(
                llm_reply or f"Search #{search_id} added: *{keywords}* in *{location}*",
                parse_mode='Markdown',
            )
        else:
            await update.message.reply_text(
                "I couldn't figure out the job title or location. "
                "Could you be more specific? e.g. \"find me Python developer jobs in Brisbane\""
            )
        return

    # --- search_list ---
    if action == 'search_list':
        searches = get_searches(chat_id=chat_id, active_only=True)
        if not searches:
            await update.message.reply_text(
                llm_reply or "You have no active searches yet. Tell me what kind of job you're looking for!"
            )
            return
        lines = ["*Your active searches:*\n"]
        for s in searches:
            last = s.get('last_run') or 'never'
            if last != 'never':
                last = last[:16].replace('T', ' ')
            lines.append(f"*#{s['id']}* — {s['keywords']} in {s['location']}")
            lines.append(f"   Last checked: {last}\n")
        await update.message.reply_text('\n'.join(lines), parse_mode='Markdown')
        return

    # --- search_remove ---
    if action == 'search_remove':
        search_id = params.get('id')
        kw = params.get('keywords', '')

        if not search_id and kw:
            for s in searches:
                if kw.lower() in s['keywords'].lower():
                    search_id = s['id']
                    break

        if search_id:
            if remove_search(int(search_id), chat_id):
                await update.message.reply_text(llm_reply or f"Done — search #{search_id} removed.")
            else:
                await update.message.reply_text(f"Couldn't find search #{search_id}.")
        else:
            await update.message.reply_text(
                "Which search should I remove? Say something like \"remove search 2\" "
                "or \"stop looking for truck driver jobs\"."
            )
        return

    # --- profile_view ---
    if action == 'profile_view':
        profile = get_profile(chat_id)
        sal_min = profile.get('salary_min')
        sal_max = profile.get('salary_max')
        salary_str = (
            f"${sal_min:,.0f} – ${sal_max:,.0f}/yr" if sal_min and sal_max
            else f"from ${sal_min:,.0f}/yr" if sal_min
            else f"up to ${sal_max:,.0f}/yr" if sal_max
            else "not set"
        )
        types_str  = ', '.join(profile.get('job_types') or []) or 'not set'
        arr_str    = ', '.join(profile.get('arrangements') or []) or 'not set'
        exp_str    = ', '.join(profile.get('experience_levels') or []) or 'not set'
        skills_str = ', '.join(profile.get('skills') or []) or 'not set'
        days = profile.get('posted_within_days') or 3
        days_str = _DAYS_LABELS.get(days, f'{days} days')
        msg = (
            "*Your Profile*\n\n"
            f"Salary: {salary_str}\n"
            f"Job types: {types_str}\n"
            f"Arrangements: {arr_str}\n"
            f"Experience levels: {exp_str}\n"
            f"Skills: {skills_str}\n"
            f"Posted within: {days_str}"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')
        return

    # --- profile_salary ---
    if action == 'profile_salary':
        sal_min = params.get('salary_min')
        sal_max = params.get('salary_max')
        if sal_min is not None and sal_max is not None:
            upsert_profile(chat_id, salary_min=float(sal_min), salary_max=float(sal_max))
            await update.message.reply_text(
                llm_reply or f"Salary range updated: ${float(sal_min):,.0f} – ${float(sal_max):,.0f} per year"
            )
        else:
            await update.message.reply_text(
                "I couldn't read the salary range. "
                "Try something like \"I want to earn between 90k and 130k\"."
            )
        return

    # --- profile_type ---
    if action == 'profile_type':
        job_types = params.get('job_types', [])
        if job_types:
            upsert_profile(chat_id, job_types=job_types)
            await update.message.reply_text(
                llm_reply or f"Job types updated: {', '.join(job_types)}"
            )
        else:
            await update.message.reply_text(
                "I didn't catch which job types you want. "
                "Try: full-time, part-time, contract, or casual."
            )
        return

    # --- profile_arrangement ---
    if action == 'profile_arrangement':
        arrangements = params.get('arrangements', [])
        if arrangements:
            upsert_profile(chat_id, arrangements=arrangements)
            await update.message.reply_text(
                llm_reply or f"Work arrangements updated: {', '.join(arrangements)}"
            )
        else:
            await update.message.reply_text(
                "I didn't catch which arrangements you want. Try: remote, hybrid, or onsite."
            )
        return

    # --- profile_skills ---
    if action == 'profile_skills':
        skills = params.get('skills', [])
        if skills:
            upsert_profile(chat_id, skills=skills)
            await update.message.reply_text(
                llm_reply or f"Skills updated: {', '.join(skills)}"
            )
        else:
            await update.message.reply_text(
                "I didn't catch your skills. "
                "Try listing them, e.g. \"Python, Django, PostgreSQL\"."
            )
        return

    # --- chat (general conversation / fallback) ---
    await update.message.reply_text(
        llm_reply or "I'm Sentry, your job hunting bot. Tell me what kind of job you're looking for!"
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    init_db()

    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        print("TELEGRAM_BOT_TOKEN environment variable not set.")
        return

    if not check_ollama_available():
        logger.warning(
            "Ollama is not reachable or model not found. "
            "Job matching will be unavailable until Ollama starts."
        )

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler('start',   cmd_start))
    app.add_handler(CommandHandler('help',    cmd_help))
    app.add_handler(CommandHandler('search',  cmd_search))
    app.add_handler(CommandHandler('profile', cmd_profile))
    app.add_handler(CommandHandler('filters', cmd_filters))
    app.add_handler(CommandHandler('system',  cmd_system))
    # Inline keyboard callbacks for the filter panel (pattern matches 'fm:...')
    app.add_handler(CallbackQueryHandler(handle_filter_callback, pattern=r'^fm:'))
    # Natural language chat — must be registered AFTER all command handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_chat))
    app.add_error_handler(error_handler)

    monitor_thread = Thread(target=monitor_jobs, args=(token,), daemon=True)
    monitor_thread.start()
    logger.info("Bot started. Press Ctrl+C to stop.")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
