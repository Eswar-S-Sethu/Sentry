"""
Deduplicator Module
Generates stable dedup keys for cross-platform job deduplication.
"""

import hashlib
import re


# Common business suffixes to strip when normalising company names
_SUFFIXES = re.compile(
    r'\b(pty|ltd|limited|inc|incorporated|llc|corp|corporation|group|co|'
    r'australia|aust|au)\b',
    re.IGNORECASE
)

_NON_ALPHANUM = re.compile(r'[^a-z0-9\s]')
_WHITESPACE = re.compile(r'\s+')


def _clean(text: str) -> str:
    """Lowercase, remove business suffixes and non-alphanumeric chars, collapse whitespace."""
    if not text:
        return ''
    text = text.lower()
    text = _SUFFIXES.sub('', text)
    text = _NON_ALPHANUM.sub(' ', text)
    text = _WHITESPACE.sub(' ', text).strip()
    return text


def make_dedup_key(title: str, company: str, location: str) -> str:
    """
    Return an MD5 hex digest of the normalised company|title|location string.
    Stable across platforms for the same job posting.
    """
    normalised = f"{_clean(company)}|{_clean(title)}|{_clean(location)}"
    return hashlib.md5(normalised.encode('utf-8')).hexdigest()


def is_same_job(title1, company1, location1, title2, company2, location2) -> bool:
    """Quick equality check using dedup keys."""
    return make_dedup_key(title1, company1, location1) == make_dedup_key(title2, company2, location2)
