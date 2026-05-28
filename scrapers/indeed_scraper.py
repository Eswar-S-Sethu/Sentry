"""
Indeed Scraper — Australia + International
Selects the correct Indeed country domain based on the location string.
"""

import logging
import re
import urllib.parse

from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

ABN_PATTERN = re.compile(r'\bABN:?\s*(\d{2}\s?\d{3}\s?\d{3}\s?\d{3})\b', re.IGNORECASE)

# Maps lowercase location keywords → Indeed domain
COUNTRY_DOMAINS = {
    # Australia (default)
    'australia':        'au.indeed.com',
    'melbourne':        'au.indeed.com',
    'sydney':           'au.indeed.com',
    'brisbane':         'au.indeed.com',
    'perth':            'au.indeed.com',
    'adelaide':         'au.indeed.com',
    'canberra':         'au.indeed.com',
    'hobart':           'au.indeed.com',
    # UK / Ireland
    'uk':               'uk.indeed.com',
    'united kingdom':   'uk.indeed.com',
    'england':          'uk.indeed.com',
    'london':           'uk.indeed.com',
    'manchester':       'uk.indeed.com',
    'ireland':          'ie.indeed.com',
    'dublin':           'ie.indeed.com',
    # Germany
    'germany':          'de.indeed.com',
    'berlin':           'de.indeed.com',
    'munich':           'de.indeed.com',
    'hamburg':          'de.indeed.com',
    # France
    'france':           'fr.indeed.com',
    'paris':            'fr.indeed.com',
    # Netherlands
    'netherlands':      'nl.indeed.com',
    'amsterdam':        'nl.indeed.com',
    # Spain
    'spain':            'es.indeed.com',
    'madrid':           'es.indeed.com',
    'barcelona':        'es.indeed.com',
    # Italy
    'italy':            'it.indeed.com',
    'milan':            'it.indeed.com',
    'rome':             'it.indeed.com',
    # Sweden
    'sweden':           'se.indeed.com',
    'stockholm':        'se.indeed.com',
    # Norway
    'norway':           'no.indeed.com',
    'oslo':             'no.indeed.com',
    # Denmark
    'denmark':          'dk.indeed.com',
    'copenhagen':       'dk.indeed.com',
    # Belgium
    'belgium':          'be.indeed.com',
    'brussels':         'be.indeed.com',
    # Switzerland
    'switzerland':      'ch.indeed.com',
    'zurich':           'ch.indeed.com',
    # Austria
    'austria':          'at.indeed.com',
    'vienna':           'at.indeed.com',
    # Poland
    'poland':           'pl.indeed.com',
    'warsaw':           'pl.indeed.com',
    # Portugal
    'portugal':         'pt.indeed.com',
    'lisbon':           'pt.indeed.com',
    # Finland
    'finland':          'fi.indeed.com',
    'helsinki':         'fi.indeed.com',
    # Canada
    'canada':           'ca.indeed.com',
    'toronto':          'ca.indeed.com',
    'vancouver':        'ca.indeed.com',
    # Remote / global fallback
    'remote':           'www.indeed.com',
    'worldwide':        'www.indeed.com',
    'global':           'www.indeed.com',
}

# Indeed's remote job filter parameter
_REMOTE_PARAM = 'remotejob=032b3046-06a3-4876-8dfd-474eb5e7ed11'


def _get_domain(location: str) -> tuple[str, bool]:
    """
    Return (indeed_domain, is_remote_filter) for a given location string.
    Falls back to au.indeed.com for unknown locations.
    """
    loc_lower = location.lower()
    for keyword, domain in COUNTRY_DOMAINS.items():
        if keyword in loc_lower:
            is_remote = 'remote' in loc_lower or domain == 'www.indeed.com'
            return domain, is_remote
    # Default: Australia
    return 'au.indeed.com', False


class IndeedScraper(BaseScraper):
    platform_name = 'indeed'

    def search(self, keywords: str, location: str, days: int = 3) -> list[dict]:
        domain, use_remote_filter = _get_domain(location)
        base_url = f"https://{domain}"
        jobs = []
        start = 0

        # For the 'l' (location) param: use the location string unless remote
        loc_param = '' if use_remote_filter else location

        logger.info(f"[indeed] Domain: {domain}, remote_filter: {use_remote_filter}")

        while True:
            params = {
                'q': keywords,
                'fromage': str(days),
                'start': start,
                'sort': 'date',
            }
            if loc_param:
                params['l'] = loc_param

            url = f"{base_url}/jobs?{urllib.parse.urlencode(params)}"
            if use_remote_filter:
                url += f"&{_REMOTE_PARAM}"

            logger.info(f"[indeed] Fetching start={start}: {url}")
            soup = self.get_page(url)
            if not soup:
                break

            cards = soup.select('div.job_seen_beacon')
            if not cards:
                cards = soup.select('li[class*="css-"][data-jk]')
            if not cards:
                cards = soup.select('[data-jk]')

            if not cards:
                logger.info(f"[indeed] No job cards found at start={start}, stopping")
                break

            for card in cards:
                job = self._parse_card(card, base_url)
                if job:
                    jobs.append(job)

            if len(cards) < 10:
                break
            start += 10
            if start >= 50:
                break

        logger.info(f"[indeed] Found {len(jobs)} jobs for '{keywords}' in {location}")
        return jobs

    def _parse_card(self, card, base_url: str) -> dict | None:
        try:
            job_id = card.get('data-jk')
            if not job_id:
                el = card.find(attrs={'data-jk': True})
                if el:
                    job_id = el.get('data-jk')
            job_url = f"{base_url}/viewjob?jk={job_id}" if job_id else ''

            title_el = card.find('h2', class_=lambda c: c and 'jobTitle' in c)
            if not title_el:
                title_el = card.find('a', attrs={'data-jk': True})
            title = title_el.get_text(strip=True).replace('new', '').strip() if title_el else ''

            company_el = card.find('span', attrs={'data-testid': 'company-name'})
            if not company_el:
                company_el = card.find('span', class_=lambda c: c and 'companyName' in c)
            company = company_el.get_text(strip=True) if company_el else 'Unknown'

            location_el = card.find('div', attrs={'data-testid': 'text-location'})
            if not location_el:
                location_el = card.find('div', class_=lambda c: c and 'companyLocation' in c)
            job_location = location_el.get_text(strip=True) if location_el else ''

            salary_el = card.find('div', attrs={'data-testid': 'attribute_snippet_testid'})
            if not salary_el:
                salary_el = card.find('span', class_=lambda c: c and 'salary' in (c or '').lower())
            salary_text = salary_el.get_text(strip=True) if salary_el else ''

            date_el = card.find('span', class_=lambda c: c and 'date' in (c or '').lower())
            posted_date = date_el.get_text(strip=True) if date_el else ''

            if not title or not job_url:
                return None

            description, job_type, arrangement, abn = self._fetch_detail(job_url)

            return {
                'title': title,
                'company': company,
                'location': job_location,
                'salary_text': salary_text,
                'job_type': job_type,
                'arrangement': arrangement,
                'description': description,
                'abn': abn,
                'posted_date': posted_date,
                'url': job_url,
            }
        except Exception as e:
            logger.error(f"[indeed] Error parsing card: {e}")
            return None

    def _fetch_detail(self, url: str):
        soup = self.get_page(url)
        if not soup:
            return '', '', '', None

        desc_el = soup.find('div', id='jobDescriptionText')
        if not desc_el:
            desc_el = soup.find('div', class_=lambda c: c and 'jobsearch-JobComponent-description' in (c or ''))
        description = desc_el.get_text(separator=' ', strip=True) if desc_el else ''

        job_type = ''
        for el in soup.find_all('div', attrs={'data-testid': True}):
            text = el.get_text(strip=True).lower()
            if any(t in text for t in ('full-time', 'part-time', 'contract', 'casual', 'permanent')):
                job_type = el.get_text(strip=True)
                break

        arrangement = ''
        full_text_lower = soup.get_text().lower()
        if 'remote' in full_text_lower:
            arrangement = 'Remote'
        elif 'hybrid' in full_text_lower:
            arrangement = 'Hybrid'
        elif 'on-site' in full_text_lower or 'onsite' in full_text_lower:
            arrangement = 'On-site'

        abn = None
        abn_match = ABN_PATTERN.search(soup.get_text())
        if abn_match:
            abn = re.sub(r'\s', '', abn_match.group(1))

        return description, job_type, arrangement, abn
