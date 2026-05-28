"""
Job Storage Module
SQLite persistence layer for profiles, searches, and seen jobs.
"""

import json
import logging
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

DB_FILE = 'jobs.db'


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                chat_id            INTEGER PRIMARY KEY,
                salary_min         REAL,
                salary_max         REAL,
                job_types          TEXT DEFAULT '[]',
                arrangements       TEXT DEFAULT '[]',
                skills             TEXT DEFAULT '[]',
                experience_levels  TEXT DEFAULT '[]',
                posted_within_days INTEGER DEFAULT 3,
                updated_at         TEXT
            );

            CREATE TABLE IF NOT EXISTS searches (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL,
                keywords    TEXT NOT NULL,
                location    TEXT NOT NULL,
                active      INTEGER DEFAULT 1,
                created_at  TEXT,
                last_run    TEXT
            );

            CREATE TABLE IF NOT EXISTS seen_jobs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                dedup_key    TEXT UNIQUE,
                title        TEXT,
                company      TEXT,
                location     TEXT,
                salary_text  TEXT,
                job_type     TEXT,
                arrangement  TEXT,
                description  TEXT,
                abn          TEXT,
                platforms    TEXT DEFAULT '{}',
                posted_date  TEXT,
                first_seen   TEXT,
                matched      INTEGER DEFAULT 0,
                notified     INTEGER DEFAULT 0,
                search_id    INTEGER,
                analysis     TEXT DEFAULT '{}',
                FOREIGN KEY(search_id) REFERENCES searches(id)
            );
        """)

    # Migrations: add columns to existing databases
    with get_connection() as conn:
        job_cols = {row[1] for row in conn.execute("PRAGMA table_info(seen_jobs)").fetchall()}
        if 'analysis' not in job_cols:
            conn.execute("ALTER TABLE seen_jobs ADD COLUMN analysis TEXT DEFAULT '{}'")
            logger.info("Migrated seen_jobs: added analysis column")

        profile_cols = {row[1] for row in conn.execute("PRAGMA table_info(profiles)").fetchall()}
        if 'experience_levels' not in profile_cols:
            conn.execute("ALTER TABLE profiles ADD COLUMN experience_levels TEXT DEFAULT '[]'")
            logger.info("Migrated profiles: added experience_levels column")
        if 'posted_within_days' not in profile_cols:
            conn.execute("ALTER TABLE profiles ADD COLUMN posted_within_days INTEGER DEFAULT 3")
            logger.info("Migrated profiles: added posted_within_days column")

    logger.info("Database initialised")


# ---------------------------------------------------------------------------
# Profile CRUD
# ---------------------------------------------------------------------------

def get_profile(chat_id):
    """Return profile dict for chat_id, or defaults if not set."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM profiles WHERE chat_id = ?", (chat_id,)
        ).fetchone()
    if row:
        return {
            'chat_id': row['chat_id'],
            'salary_min': row['salary_min'],
            'salary_max': row['salary_max'],
            'job_types': json.loads(row['job_types'] or '[]'),
            'arrangements': json.loads(row['arrangements'] or '[]'),
            'skills': json.loads(row['skills'] or '[]'),
            'experience_levels': json.loads(row['experience_levels'] or '[]'),
            'posted_within_days': row['posted_within_days'] or 3,
            'updated_at': row['updated_at'],
        }
    return {
        'chat_id': chat_id,
        'salary_min': None,
        'salary_max': None,
        'job_types': [],
        'arrangements': [],
        'skills': [],
        'experience_levels': [],
        'posted_within_days': 3,
        'updated_at': None,
    }


def upsert_profile(chat_id, **kwargs):
    """Create or update profile fields. Pass keyword args matching column names."""
    profile = get_profile(chat_id)
    for key, value in kwargs.items():
        if key in ('job_types', 'arrangements', 'skills'):
            profile[key] = value
        else:
            profile[key] = value
    profile['updated_at'] = datetime.now().isoformat()

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO profiles
                (chat_id, salary_min, salary_max, job_types, arrangements, skills,
                 experience_levels, posted_within_days, updated_at)
            VALUES
                (:chat_id, :salary_min, :salary_max, :job_types, :arrangements, :skills,
                 :experience_levels, :posted_within_days, :updated_at)
            ON CONFLICT(chat_id) DO UPDATE SET
                salary_min         = excluded.salary_min,
                salary_max         = excluded.salary_max,
                job_types          = excluded.job_types,
                arrangements       = excluded.arrangements,
                skills             = excluded.skills,
                experience_levels  = excluded.experience_levels,
                posted_within_days = excluded.posted_within_days,
                updated_at         = excluded.updated_at
        """, {
            'chat_id': chat_id,
            'salary_min': profile['salary_min'],
            'salary_max': profile['salary_max'],
            'job_types': json.dumps(profile['job_types']),
            'arrangements': json.dumps(profile['arrangements']),
            'skills': json.dumps(profile['skills']),
            'experience_levels': json.dumps(profile['experience_levels']),
            'posted_within_days': profile['posted_within_days'],
            'updated_at': profile['updated_at'],
        })
    logger.info(f"Profile updated for chat {chat_id}")
    return get_profile(chat_id)


# ---------------------------------------------------------------------------
# Search CRUD
# ---------------------------------------------------------------------------

def add_search(chat_id, keywords, location):
    """Add a new active search. Returns the new search id."""
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO searches (chat_id, keywords, location, active, created_at) VALUES (?, ?, ?, 1, ?)",
            (chat_id, keywords, location, now)
        )
    logger.info(f"Search added for chat {chat_id}: '{keywords}' in {location}")
    return cursor.lastrowid


def get_searches(chat_id=None, active_only=True):
    """Return list of search dicts. Filter by chat_id and/or active status."""
    query = "SELECT * FROM searches WHERE 1=1"
    params = []
    if chat_id is not None:
        query += " AND chat_id = ?"
        params.append(chat_id)
    if active_only:
        query += " AND active = 1"
    query += " ORDER BY id"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def remove_search(search_id, chat_id):
    """Delete a search by id (only if it belongs to chat_id). Returns True if deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM searches WHERE id = ? AND chat_id = ?",
            (search_id, chat_id)
        )
    deleted = cursor.rowcount > 0
    if deleted:
        logger.info(f"Search {search_id} removed")
    return deleted


def update_search_last_run(search_id):
    """Update the last_run timestamp for a search."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE searches SET last_run = ? WHERE id = ?",
            (datetime.now().isoformat(), search_id)
        )


# ---------------------------------------------------------------------------
# Seen Jobs CRUD
# ---------------------------------------------------------------------------

def job_exists(dedup_key):
    """Return True if this dedup_key has already been seen."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM seen_jobs WHERE dedup_key = ?", (dedup_key,)
        ).fetchone()
    return row is not None


def get_job_by_key(dedup_key):
    """Return full job record by dedup_key, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM seen_jobs WHERE dedup_key = ?", (dedup_key,)
        ).fetchone()
    if row:
        d = dict(row)
        d['platforms'] = json.loads(d['platforms'] or '{}')
        return d
    return None


def insert_job(job):
    """
    Insert a new job record. `job` is a dict with keys matching seen_jobs columns.
    `job['platforms']` should be a dict (will be JSON-serialised).
    Returns the new row id.
    """
    platforms = json.dumps(job.get('platforms', {}))
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT OR IGNORE INTO seen_jobs
                (dedup_key, title, company, location, salary_text, job_type,
                 arrangement, description, abn, platforms, posted_date, first_seen, search_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job['dedup_key'],
            job.get('title'),
            job.get('company'),
            job.get('location'),
            job.get('salary_text'),
            job.get('job_type'),
            job.get('arrangement'),
            job.get('description'),
            job.get('abn'),
            platforms,
            job.get('posted_date'),
            now,
            job.get('search_id'),
        ))
    return cursor.lastrowid


def update_job_platforms(dedup_key, platform, url):
    """Add or update a platform URL for an existing job."""
    job = get_job_by_key(dedup_key)
    if not job:
        return
    platforms = job['platforms']
    platforms[platform] = url
    with get_connection() as conn:
        conn.execute(
            "UPDATE seen_jobs SET platforms = ? WHERE dedup_key = ?",
            (json.dumps(platforms), dedup_key)
        )


def mark_job_matched(dedup_key, matched=1):
    with get_connection() as conn:
        conn.execute(
            "UPDATE seen_jobs SET matched = ? WHERE dedup_key = ?",
            (matched, dedup_key)
        )


def mark_job_notified(dedup_key):
    with get_connection() as conn:
        conn.execute(
            "UPDATE seen_jobs SET notified = 1 WHERE dedup_key = ?",
            (dedup_key,)
        )


def update_job_analysis(dedup_key: str, analysis: dict):
    """Store the full LLM analysis result for a job."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE seen_jobs SET analysis = ? WHERE dedup_key = ?",
            (json.dumps(analysis), dedup_key)
        )
