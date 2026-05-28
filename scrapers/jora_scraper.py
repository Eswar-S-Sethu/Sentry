"""
Jora Scraper — Australia + International
Selects the correct Jora subdomain based on location.
"""

import logging
import re
import urllib.parse

from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

ABN_PATTERN = re.compile(r'\bABN:?\s*(\d{2}\s?\d{3}\s?\d{3}\s?\d{3})\b', re.IGNORECASE)

COUNTRY_DOMAINS = {
    'australia':        'au.jora.com',
    'melbourne':        'au.jora.com',
    'sydney':           'au.jora.com',
    'brisbane':         'au.jora.com',
    'perth':            'au.jora.com',
    'adelaide':         'au.jora.com',
    'uk':               'uk.jora.com',
    'united kingdom':   'uk.jora.com',
    'london':           'uk.jora.com',
    'germany':          'de.jora.com',
    'berlin':           'de.jora.com',
    'france':           'fr.jora.com',
    'paris':            'fr.jora.com',
    'netherlands':      'nl.jora.com',
    'amsterdam':        'nl.jora.com',
    'sweden':           'se.jora.com',
    'norway':           'no.jora.com',
    'denmark':          'dk.jora.com',
    'belgium':          'be.jora.com',
    'switzerland':      'ch.jora.com',
    'austria':          'at.jora.com',
    'ireland':          'ie.jora.com',
    'canada':           'ca.jora.com',
}


def _get_domain(location: str) -> str:
    loc_lower = location.lower()
    for keyword, domain in COUNTRY_DOMAINS.items():
        if keyword in loc_lower:
            return domain
    # Remote / unknown → international Jora
    if 'remote' in loc_lower:
        return 'www.jora.com'
    return 'au.jora.com'  # Default


class JoraScraper(BaseScraper):
    platform_name = 'jora'

    def search(self, keywords: str, location: str, days: int = 3) -> list[dict]:
        jobs = []
        page = 1
        domain = _get_domain(location)
        base_url = f"https://{domain}"
        logger.info(f"[jora] Domain: {domain}")
        # Jora tf param: 1d, 3d, 7d, 1m
        tf = '1m' if days >= 30 else f'{days}d'

        while True:
            params = urllib.parse.urlencode({
                'q': keywords,
                'l': location,
                'tf': tf,
                'p': page,
            })
            url = f"{base_url}/jobs?{params}"
            logger.info(f"[jora] Fetching page {page}: {url}")
            soup = self.get_page(url)
            if not soup:
                break

            # Jora job cards
            cards = soup.select('article.job-card')
            if not cards:
                cards = soup.select('[data-job-id]')
            if not cards:
                cards = soup.select('.job-result')

            if not cards:
                logger.info(f"[jora] No job cards found on page {page}, stopping")
                break

            for card in cards:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)

            # Next page
            next_btn = soup.find('a', attrs={'rel': 'next'})
            if not next_btn or page >= 5:
                break
            page += 1

        logger.info(f"[jora] Found {len(jobs)} jobs for '{keywords}' in {location}")
        return jobs

    def _parse_card(self, card) -> dict | None:
        try:
            # Job link
            link_el = card.find('a', class_=lambda c: c and 'job-link' in (c or ''))
            if not link_el:
                link_el = card.find('a', href=True)
            if not link_el:
                return None

            href = link_el.get('href', '')
            if href.startswith('/'):
                job_url = f"{self.BASE_URL}{href}"
            elif href.startswith('http'):
                job_url = href
            else:
                return None

            # Title
            title_el = card.find('h2') or card.find('h3')
            if not title_el:
                title_el = link_el
            title = title_el.get_text(strip=True)

            # Company
            company_el = card.find(class_=lambda c: c and 'company' in (c or '').lower())
            company = company_el.get_text(strip=True) if company_el else 'Unknown'

            # Location
            location_el = card.find(class_=lambda c: c and 'location' in (c or '').lower())
            location = location_el.get_text(strip=True) if location_el else ''

            # Salary
            salary_el = card.find(class_=lambda c: c and 'salary' in (c or '').lower())
            salary_text = salary_el.get_text(strip=True) if salary_el else ''

            # Posted date
            date_el = card.find('time') or card.find(class_=lambda c: c and 'date' in (c or '').lower())
            posted_date = date_el.get_text(strip=True) if date_el else ''

            if not title:
                return None

            # Fetch Jora detail page for description
            description, job_type, arrangement, abn = self._fetch_detail(job_url)

            return {
                'title': title,
                'company': company,
                'location': location,
                'salary_text': salary_text,
                'job_type': job_type,
                'arrangement': arrangement,
                'description': description,
                'abn': abn,
                'posted_date': posted_date,
                'url': job_url,
            }
        except Exception as e:
            logger.error(f"[jora] Error parsing card: {e}")
            return None

    def _fetch_detail(self, url: str):
        """Fetch Jora job detail page. Returns (description, job_type, arrangement, abn)."""
        soup = self.get_page(url)
        if not soup:
            return '', '', '', None

        # Description - Jora shows original content in an iframe or main section
        desc_el = soup.find('div', class_=lambda c: c and 'description' in (c or '').lower())
        if not desc_el:
            desc_el = soup.find('section', class_=lambda c: c and 'detail' in (c or '').lower())
        if not desc_el:
            desc_el = soup.find('main')
        description = desc_el.get_text(separator=' ', strip=True) if desc_el else ''

        # Job type
        job_type = ''
        full_text_lower = soup.get_text().lower()
        for t in ('full-time', 'full time', 'part-time', 'part time', 'contract', 'casual', 'permanent'):
            if t in full_text_lower:
                job_type = t.title()
                break

        # Work arrangement
        arrangement = ''
        if 'remote' in full_text_lower:
            arrangement = 'Remote'
        elif 'hybrid' in full_text_lower:
            arrangement = 'Hybrid'
        elif 'on-site' in full_text_lower or 'onsite' in full_text_lower:
            arrangement = 'On-site'

        # ABN detection
        abn = None
        abn_match = ABN_PATTERN.search(soup.get_text())
        if abn_match:
            abn = re.sub(r'\s', '', abn_match.group(1))

        return description, job_type, arrangement, abn
