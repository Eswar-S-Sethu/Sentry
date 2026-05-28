"""
Job Matcher Module
Uses a local Ollama LLM (default: qwen2.5:4b) to evaluate whether a job
listing is a good match for the user's profile and search query.

Each evaluation is a single-shot call — no conversation history needed.
"""

import json
import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen2.5:3b')
MATCH_CONFIDENCE_THRESHOLD = 0.6

_ANALYSIS_PROMPT = """\
You are a job analysis assistant. Perform FOUR tasks for the job listing below and return ONLY valid JSON.

USER PROFILE:
- Salary expectation: {salary_range}
- Preferred job types: {job_types}
- Preferred work arrangements: {arrangements}
- Preferred experience levels: {experience_levels}
- Skills and experience: {skills}

SEARCH QUERY: "{keywords}" in {location}

JOB LISTING:
Title:       {title}
Company:     {company}
Location:    {job_location}
Salary:      {salary_text}
Job type:    {job_type}
Arrangement: {arrangement}
Description:
{description}

TASKS:

1. MATCH — Does this job suit the user? Check salary, type, arrangement, experience level, and skills.

2. SUMMARY — Write exactly 4 short bullet points describing: what the role involves, the tech stack or tools, the work arrangement/perks, and the seniority level.

3. RED FLAGS — Scan for any of these warning signals and list each one found:
   - Pyramid/MLM: "unlimited earning potential", "be your own boss", recruit others for pay
   - Unpaid work: "unpaid trial", "complete a test project first", excessive screening tasks
   - Missing salary: salary is "Not specified" AND no salary range appears anywhere in the description
   - Toxic culture: "rockstar", "ninja", "guru", "no 9-5 mentality", "work hard play hard", "unlimited hours"
   - Unrealistic scope: one person expected to do the work of a whole team
   - Experience mismatch: 10+ years required but compensation suggests junior level
   - Equipment burden: "must provide own laptop/car/tools" for a standard office role
   If none found, return an empty array.

4. SKILL GAPS — List skills explicitly required or strongly preferred in the description that are NOT in the user's skills list. For each gap, give a priority (high/medium/low) and one-sentence reason.
   - high: clearly stated as required / essential
   - medium: preferred, or used heavily but not labelled required
   - low: nice-to-have, mentioned once
   If no gaps, return an empty array.

Return ONLY this JSON with no extra text:
{{
  "match": true,
  "confidence": 0.85,
  "reason": "one sentence",
  "summary": ["bullet 1", "bullet 2", "bullet 3", "bullet 4"],
  "red_flags": ["description of flag"],
  "skill_gaps": [
    {{"skill": "Kubernetes", "priority": "high", "why": "listed as required for deployment pipelines"}},
    {{"skill": "Terraform", "priority": "medium", "why": "preferred for infrastructure management"}}
  ]
}}
"""


def _build_analysis_prompt(job: dict, search: dict, profile: dict) -> str:
    salary_min = profile.get('salary_min')
    salary_max = profile.get('salary_max')
    if salary_min and salary_max:
        salary_range = f"${salary_min:,.0f} – ${salary_max:,.0f} per year"
    elif salary_min:
        salary_range = f"at least ${salary_min:,.0f} per year"
    elif salary_max:
        salary_range = f"up to ${salary_max:,.0f} per year"
    else:
        salary_range = "not specified"

    job_types = ', '.join(profile.get('job_types') or []) or 'any'
    arrangements = ', '.join(profile.get('arrangements') or []) or 'any'
    experience_levels = ', '.join(profile.get('experience_levels') or []) or 'any'
    skills = ', '.join(profile.get('skills') or []) or 'not specified'
    description = (job.get('description') or '')[:3000]

    return _ANALYSIS_PROMPT.format(
        salary_range=salary_range,
        job_types=job_types,
        arrangements=arrangements,
        experience_levels=experience_levels,
        skills=skills,
        keywords=search.get('keywords', ''),
        location=search.get('location', ''),
        title=job.get('title', ''),
        company=job.get('company', ''),
        job_location=job.get('location', ''),
        salary_text=job.get('salary_text') or 'Not specified',
        job_type=job.get('job_type') or 'Not specified',
        arrangement=job.get('arrangement') or 'Not specified',
        description=description,
    )


def _call_ollama(prompt: str, num_predict: int = 800) -> str | None:
    """Call Ollama generate endpoint. Returns raw response text or None."""
    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                'model': OLLAMA_MODEL,
                'prompt': prompt,
                'stream': False,
                'options': {
                    'temperature': 0.1,
                    'num_predict': num_predict,
                },
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return data.get('response', '')
    except requests.exceptions.ConnectionError:
        logger.error(f"Cannot connect to Ollama at {OLLAMA_HOST}. Is it running?")
        return None
    except Exception as e:
        logger.error(f"Ollama call failed: {e}")
        return None


def _extract_json(raw: str) -> dict:
    """
    Robustly extract the first complete JSON object from a string.
    Handles nested arrays and objects. Returns an empty dict on failure.
    """
    if not raw:
        return {}

    # Strip markdown fences
    clean = re.sub(r'```(?:json)?', '', raw).strip('` \n')

    # Find the outermost { ... } by counting brackets
    start = clean.find('{')
    if start == -1:
        return {}

    depth = 0
    for i, ch in enumerate(clean[start:], start):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(clean[start:i + 1])
                except json.JSONDecodeError:
                    break

    # Last-ditch: try the whole cleaned string
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        logger.warning(f"Could not extract JSON from LLM response: {raw[:300]}")
        return {}


def analyse_job(job: dict, search: dict, profile: dict) -> dict:
    """
    Run a single combined LLM analysis on a job listing.

    Returns a dict with keys:
        match        (bool)
        confidence   (float 0–1)
        reason       (str)
        summary      (list[str])   — 4 bullet points
        red_flags    (list[str])   — warning signals found
        skill_gaps   (list[dict])  — [{"skill", "priority", "why"}, ...]
    """
    _EMPTY = {
        'match': False, 'confidence': 0.0, 'reason': 'LLM unavailable',
        'summary': [], 'red_flags': [], 'skill_gaps': [],
    }

    prompt = _build_analysis_prompt(job, search, profile)
    raw = _call_ollama(prompt, num_predict=800)
    if not raw:
        return _EMPTY

    result = _extract_json(raw)
    if not result:
        return _EMPTY

    matched = bool(result.get('match', False))
    confidence = float(result.get('confidence', 0.0))

    if matched and confidence < MATCH_CONFIDENCE_THRESHOLD:
        logger.info(
            f"Job '{job.get('title')}' matched but confidence too low "
            f"({confidence:.2f}), marking as no-match"
        )
        matched = False

    logger.info(
        f"Analysis for '{job.get('title')}' @ {job.get('company')}: "
        f"match={'YES' if matched else 'NO'} confidence={confidence:.2f} "
        f"flags={len(result.get('red_flags', []))} gaps={len(result.get('skill_gaps', []))}"
    )

    return {
        'match': matched,
        'confidence': confidence,
        'reason': result.get('reason', ''),
        'summary': result.get('summary') or [],
        'red_flags': result.get('red_flags') or [],
        'skill_gaps': result.get('skill_gaps') or [],
    }


_INTENT_TEMPLATE = """\
You are an assistant for a job monitoring Telegram bot called Sentry.
The user sent a plain text message. Figure out what they want and whether you have enough information to act.

CURRENT PROFILE:
- Salary: {salary_range}
- Job types: {job_types}
- Arrangements: {arrangements}
- Skills: {skills}

ACTIVE SEARCHES:
{searches}

PENDING CONTEXT (partial info gathered from previous question, may be empty):
{pending}

USER MESSAGE: "{message}"

Valid location values: any city, country, region, or "Remote" / "Remote Europe" / "Worldwide".
Supported regions: Australia (Melbourne, Sydney, etc.), UK, Germany, France, Netherlands, Spain,
Italy, Sweden, Norway, Denmark, Belgium, Switzerland, Austria, Poland, Portugal, Finland, Ireland,
Canada, and Remote / Worldwide.

Classify the intent. Reply with ONLY valid JSON:

{{
  "action": "<one of: search_add | search_list | search_remove | profile_view | profile_salary | profile_type | profile_arrangement | profile_skills | needs_clarification | show_filters | chat>",
  "params": {{
    // search_add:            "keywords": "...", "location": "..."
    // search_remove:         "id": <int or null>, "keywords": "<str or null>"
    // profile_salary:        "salary_min": <float>, "salary_max": <float>
    // profile_type:          "job_types": ["full-time", ...]
    // profile_arrangement:   "arrangements": ["hybrid", "remote", ...]
    // profile_skills:        "skills": ["Python", ...]
    // needs_clarification:   "partial_params": {{"keywords": "...", "location": "..."}}, "missing": ["location"]
    // all others:            {{}}
  }},
  "reply": "<friendly response or question to show the user>"
}}

Rules:
- Use "needs_clarification" when the user clearly wants to add a search but is missing:
    * keywords (the job role is too vague, e.g. "find me a job" with no role specified), OR
    * location (no city, country, or "remote" mentioned anywhere in the message or pending context).
  In this case, set params.partial_params to whatever you do know, params.missing to a list of
  what is still needed, and reply with a friendly question asking for the missing piece.
- Merge pending context with the new message before deciding if info is complete.
- Once both keywords AND location are known (including from pending context), use "search_add".
- Location "Remote" is valid — do NOT ask for more location detail if the user said remote.
- For search_remove, prefer id if a number is mentioned, otherwise match by keywords.
- salary_min/max must be annual numbers (e.g. 90000, not "90k").
- Use "chat" only when the message is purely conversational with no actionable intent.
- Keep reply natural, brief, and warm.
"""


def parse_intent(
    message: str,
    profile: dict,
    searches: list[dict],
    pending_partial: dict | None = None,
) -> dict:
    """
    Use Ollama to parse a natural language message into a structured intent.
    Pass pending_partial to carry over partial params from a previous clarification turn.

    Returns a dict with keys: action, params, reply
    Falls back to {"action": "chat", "params": {}, "reply": <message>} on failure.
    """
    salary_min = profile.get('salary_min')
    salary_max = profile.get('salary_max')
    if salary_min and salary_max:
        salary_range = f"${salary_min:,.0f} – ${salary_max:,.0f} per year"
    else:
        salary_range = "not set"

    job_types = ', '.join(profile.get('job_types') or []) or 'not set'
    arrangements = ', '.join(profile.get('arrangements') or []) or 'not set'
    skills = ', '.join(profile.get('skills') or []) or 'not set'

    if searches:
        searches_str = '\n'.join(
            f"  #{s['id']}: {s['keywords']} in {s['location']}"
            for s in searches
        )
    else:
        searches_str = '  (none)'

    pending_str = json.dumps(pending_partial or {})

    prompt = _INTENT_TEMPLATE.format(
        salary_range=salary_range,
        job_types=job_types,
        arrangements=arrangements,
        skills=skills,
        searches=searches_str,
        pending=pending_str,
        message=message,
    )

    raw = _call_ollama(prompt)
    if not raw:
        return {
            'action': 'chat',
            'params': {},
            'reply': "Sorry, I can't reach the local LLM right now. Try using slash commands instead.",
        }

    # Extract JSON — handle markdown fences the model sometimes adds
    clean = re.sub(r'```(?:json)?', '', raw).strip('` \n')
    json_match = re.search(r'\{.*\}', clean, re.DOTALL)
    if json_match:
        try:
            result = json.loads(json_match.group())
            result.setdefault('action', 'chat')
            result.setdefault('params', {})
            result.setdefault('reply', '')
            return result
        except json.JSONDecodeError:
            pass

    logger.warning(f"Could not parse intent JSON from: {raw[:300]}")
    return {
        'action': 'chat',
        'params': {},
        'reply': raw.strip()[:500],
    }


def check_ollama_available() -> bool:
    """Return True if Ollama is reachable and the configured model is available."""
    try:
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        if response.status_code == 200:
            models = [m['name'] for m in response.json().get('models', [])]
            available = any(OLLAMA_MODEL in m for m in models)
            if not available:
                logger.warning(
                    f"Ollama running but model '{OLLAMA_MODEL}' not found. "
                    f"Available: {models}. Set OLLAMA_MODEL env var."
                )
            return available
        return False
    except Exception:
        return False
