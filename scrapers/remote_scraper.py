"""
Remote Jobs Scraper
Sources:
  1. Remotive.io — free REST API, no auth needed, global remote jobs
  2. WeWorkRemotely.com — scraped search page, large volume
"""

import logging
import re
import urllib.parse

import requests as _requests  # Using requests directly — the API returns JSON, no HTML parsing

from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)

ABN_PATTERN = re.compile(r'\bABN:?\s*(\d{2}\s?\d{3}\s?\d{3}\s?\d{3})\b', re.IGNORECASE)

REMOTIVE_API = 'https://remotive.com/api/remote-jobs'
WWR_SEARCH_URL = 'https://weworkremotely.com/remote-jobs/search'


class RemoteScraper(BaseScraper):
    platform_name = 'remote'

    def search(self, keywords: str, location: str, days: int = 3) -> list[dict]:
        """
        Search both Remotive and WeWorkRemotely.
        `location` is used only for filtering (e.g. "Remote Europe") if present in listing text.
        `days` is accepted for interface compatibility but Remotive does not support date filtering.
        """
        jobs = []
        jobs += self._search_remotive(keywords, location)
        jobs += self._search_wwr(keywords, location)
        logger.info(f"[remote] Found {len(jobs)} remote jobs for '{keywords}'")
        return jobs

    # ------------------------------------------------------------------
    # Remotive.io
    # ------------------------------------------------------------------

    def _search_remotive(self, keywords: str, location: str) -> list[dict]:
        try:
            resp = _requests.get(
                REMOTIVE_API,
                params={'search': keywords, 'limit': 20},
                timeout=15,
                headers={'User-Agent': 'Sentry-JobBot/1.0'},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[remotive] API call failed: {e}")
            return []

        jobs = []
        location_lower = location.lower()

        for item in data.get('jobs', []):
            # Optional: filter by candidate_required_location when user specified a region
            candidate_location = (item.get('candidate_required_location') or '').lower()
            if location_lower not in ('remote', 'worldwide', 'global', ''):
                # User wants a specific region — skip if listing explicitly excludes it
                # (e.g. "US Only" when user wants Europe)
                if candidate_location and _location_excluded(candidate_location, location_lower):
                    continue

            description = item.get('description', '')
            abn = None
            abn_match = ABN_PATTERN.search(description)
            if abn_match:
                abn = re.sub(r'\s', '', abn_match.group(1))

            jobs.append({
                'title': item.get('title', ''),
                'company': item.get('company_name', ''),
                'location': item.get('candidate_required_location') or 'Remote',
                'salary_text': item.get('salary') or '',
                'job_type': item.get('job_type') or '',
                'arrangement': 'Remote',
                'description': description,
                'abn': abn,
                'posted_date': (item.get('publication_date') or '')[:10],
                'url': item.get('url', ''),
            })

        logger.info(f"[remotive] {len(jobs)} jobs after location filter")
        return jobs

    # ------------------------------------------------------------------
    # WeWorkRemotely
    # ------------------------------------------------------------------

    def _search_wwr(self, keywords: str, location: str) -> list[dict]:
        url = f"{WWR_SEARCH_URL}?term={urllib.parse.quote_plus(keywords)}"
        soup = self.get_page(url)
        if not soup:
            return []

        jobs = []
        # WWR job listings are in <li> elements inside sections
        for li in soup.select('li[class*="feature"]') + soup.select('section ul li'):
            job = self._parse_wwr_card(li, location)
            if job:
                jobs.append(job)

        logger.info(f"[weworkremotely] {len(jobs)} jobs")
        return jobs

    def _parse_wwr_card(self, li, location: str) -> dict | None:
        try:
            link = li.find('a', href=True)
            if not link:
                return None

            href = link.get('href', '')
            job_url = f"https://weworkremotely.com{href}" if href.startswith('/') else href

            title_el = li.find(class_=lambda c: c and 'title' in (c or '').lower())
            if not title_el:
                title_el = li.find('span', class_='title')
            title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)

            company_el = li.find(class_=lambda c: c and 'company' in (c or '').lower())
            company = company_el.get_text(strip=True) if company_el else 'Unknown'

            region_el = li.find(class_=lambda c: c and 'region' in (c or '').lower())
            job_location = region_el.get_text(strip=True) if region_el else 'Remote'

            if not title or not job_url or title.lower() == 'jobs':
                return None

            # Fetch detail for description
            desc_soup = self.get_page(job_url)
            description = ''
            abn = None
            if desc_soup:
                desc_el = desc_soup.find(class_=lambda c: c and 'listing-container' in (c or ''))
                if not desc_el:
                    desc_el = desc_soup.find('div', id=lambda i: i and 'job' in (i or '').lower())
                if desc_el:
                    description = desc_el.get_text(separator=' ', strip=True)
                abn_match = ABN_PATTERN.search(desc_soup.get_text())
                if abn_match:
                    abn = re.sub(r'\s', '', abn_match.group(1))

            return {
                'title': title,
                'company': company,
                'location': job_location,
                'salary_text': '',
                'job_type': '',
                'arrangement': 'Remote',
                'description': description,
                'abn': abn,
                'posted_date': '',
                'url': job_url,
            }
        except Exception as e:
            logger.error(f"[weworkremotely] Card parse error: {e}")
            return None


def _location_excluded(candidate_location: str, desired_location: str) -> bool:
    """
    Return True if the listing's candidate_required_location explicitly
    restricts to a region that does NOT include the desired location.

    Examples:
      candidate="usa only", desired="europe" → True (excluded)
      candidate="europe", desired="germany"  → False (compatible)
      candidate="worldwide", desired="europe" → False (compatible)
    """
    exclusion_pairs = [
        (['usa', 'us only', 'united states', 'north america'], ['europe', 'eu', 'uk', 'germany', 'france']),
        (['europe', 'eu', 'emea'], ['usa', 'us', 'united states', 'australia', 'latam']),
        (['australia', 'au'], ['europe', 'usa']),
    ]
    for exclusive_regions, incompatible_with in exclusion_pairs:
        if any(r in candidate_location for r in exclusive_regions):
            if any(r in desired_location for r in incompatible_with):
                return True
    return False
