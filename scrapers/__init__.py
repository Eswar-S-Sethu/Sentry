from .seek_scraper import SeekScraper
from .indeed_scraper import IndeedScraper
from .jora_scraper import JoraScraper
from .remote_scraper import RemoteScraper

# Location keywords that trigger the remote job boards
_REMOTE_KEYWORDS = {'remote', 'worldwide', 'global', 'wfh', 'work from home'}

# European country keywords — use international scrapers only (no Seek)
_EUROPEAN_KEYWORDS = {
    'europe', 'eu', 'germany', 'france', 'netherlands', 'spain', 'italy',
    'sweden', 'norway', 'denmark', 'belgium', 'switzerland', 'austria',
    'poland', 'portugal', 'finland', 'ireland', 'berlin', 'munich', 'paris',
    'amsterdam', 'madrid', 'barcelona', 'milan', 'stockholm', 'oslo',
    'copenhagen', 'brussels', 'zurich', 'vienna', 'warsaw', 'lisbon',
    'helsinki', 'dublin', 'london', 'manchester', 'uk', 'united kingdom',
}


def get_scrapers_for_location(location: str) -> list:
    """
    Return the appropriate list of scraper classes for the given location string.

    - Remote / worldwide     → RemoteScraper + IndeedScraper (remote filter)
    - European country/city  → IndeedScraper + JoraScraper (international domains)
    - AU / unknown           → SeekScraper + IndeedScraper + JoraScraper
    """
    loc_lower = location.lower()

    if any(kw in loc_lower for kw in _REMOTE_KEYWORDS):
        return [RemoteScraper, IndeedScraper]

    if any(kw in loc_lower for kw in _EUROPEAN_KEYWORDS):
        return [IndeedScraper, JoraScraper]

    # Default: Australian search
    return [SeekScraper, IndeedScraper, JoraScraper]


# Kept for backwards compatibility if anything imports ALL_SCRAPERS directly
ALL_SCRAPERS = [SeekScraper, IndeedScraper, JoraScraper, RemoteScraper]
