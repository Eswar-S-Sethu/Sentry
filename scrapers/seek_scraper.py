"""
Seek.com.au Scraper
Searches seek.com.au for recent job listings (last 3 days).
"""

import logging
import re
import time

from .base_scraper import BaseScraper, REQUEST_DELAY

logger = logging.getLogger(__name__)

ABN_PATTERN = re.compile(r'\bABN:?\s*(\d{2}\s?\d{3}\s?\d{3}\s?\d{3})\b', re.IGNORECASE)


def _slug(text: str) -> str:
    """Convert text to URL-safe slug (lowercase, hyphens)."""
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


class SeekScraper(BaseScraper):
    platform_name = 'seek'
    BASE_URL = 'https://www.seek.com.au'

    def search(self, keywords: str, location: str, days: int = 3) -> list[dict]:
        jobs = []
        page = 1
        kw_slug = _slug(keywords)
        loc_slug = _slug(location)

        while True:
            url = f"{self.BASE_URL}/{kw_slug}-jobs/in-{loc_slug}?daterange={days}&page={page}"
            logger.info(f"[seek] Fetching page {page}: {url}")
            soup = self.get_page(url)
            if not soup:
                break

            # Job cards are articles with data-card-type="JobCard"
            cards = soup.find_all('article', attrs={'data-card-type': 'JobCard'})

            # Fallback: seek sometimes uses different selectors
            if not cards:
                cards = soup.select('article[data-automation="normalJob"]')
            if not cards:
                cards = soup.select('[data-automation="job-card"]')

            if not cards:
                logger.info(f"[seek] No job cards found on page {page}, stopping")
                break

            for card in cards:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)

            # Check for next page
            next_btn = soup.find('a', attrs={'data-automation': 'page-next'})
            if not next_btn:
                break
            page += 1
            if page > 5:  # Safety cap
                break

        logger.info(f"[seek] Found {len(jobs)} jobs for '{keywords}' in {location}")
        return jobs

    def _parse_card(self, card) -> dict | None:
        try:
            # Title and job URL
            title_el = card.find('a', attrs={'data-automation': 'jobTitle'})
            if not title_el:
                title_el = card.find('h3')
            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            job_path = title_el.get('href', '')
            job_url = f"{self.BASE_URL}{job_path}" if job_path.startswith('/') else job_path

            # Company
            company_el = card.find('a', attrs={'data-automation': 'jobCompany'})
            if not company_el:
                company_el = card.find('span', attrs={'data-automation': 'jobCompany'})
            company = company_el.get_text(strip=True) if company_el else 'Unknown'

            # Location
            location_el = card.find('a', attrs={'data-automation': 'jobLocation'})
            if not location_el:
                location_el = card.find('span', attrs={'data-automation': 'jobLocation'})
            location = location_el.get_text(strip=True) if location_el else ''

            # Salary
            salary_el = card.find('span', attrs={'data-automation': 'jobSalary'})
            salary_text = salary_el.get_text(strip=True) if salary_el else ''

            # Listed date
            date_el = card.find('span', attrs={'data-automation': 'jobListingDate'})
            posted_date = date_el.get_text(strip=True) if date_el else ''

            # Fetch job detail for description, job type, arrangement, ABN
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
            logger.error(f"[seek] Error parsing card: {e}")
            return None

    def _fetch_detail(self, url: str):
        """Fetch job detail page. Returns (description, job_type, arrangement, abn)."""
        soup = self.get_page(url)
        if not soup:
            return '', '', '', None

        # Description
        desc_el = soup.find('div', attrs={'data-automation': 'jobAdDetails'})
        if not desc_el:
            desc_el = soup.find('section', attrs={'data-automation': 'job-details-body'})
        description = desc_el.get_text(separator=' ', strip=True) if desc_el else ''

        # Job type / work type
        job_type = ''
        work_type_el = soup.find('span', attrs={'data-automation': 'job-detail-work-type'})
        if work_type_el:
            job_type = work_type_el.get_text(strip=True)

        # Work arrangement (remote/hybrid)
        arrangement = ''
        arrangement_el = soup.find('span', attrs={'data-automation': 'job-detail-work-arrangements'})
        if arrangement_el:
            arrangement = arrangement_el.get_text(strip=True)

        # ABN detection
        abn = None
        full_text = soup.get_text()
        abn_match = ABN_PATTERN.search(full_text)
        if abn_match:
            abn = re.sub(r'\s', '', abn_match.group(1))

        return description, job_type, arrangement, abn
