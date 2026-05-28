"""
Base Scraper
Shared httpx client, rate limiting, retry logic, and abstract interface.
"""

import logging
import time
from abc import ABC, abstractmethod

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'en-AU,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

REQUEST_DELAY = 2      # seconds between requests
MAX_RETRIES = 3
TIMEOUT = 15           # seconds


class BaseScraper(ABC):
    """Abstract base class for all job board scrapers."""

    platform_name: str = 'unknown'

    def __init__(self):
        self.client = httpx.Client(
            headers=HEADERS,
            follow_redirects=True,
            timeout=TIMEOUT,
        )

    def get_page(self, url: str) -> BeautifulSoup | None:
        """Fetch a URL with retries and return a BeautifulSoup object, or None on failure."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                time.sleep(REQUEST_DELAY)
                response = self.client.get(url)
                response.raise_for_status()
                return BeautifulSoup(response.text, 'html.parser')
            except httpx.HTTPStatusError as e:
                logger.warning(f"[{self.platform_name}] HTTP {e.response.status_code} for {url} (attempt {attempt})")
                if e.response.status_code in (403, 429):
                    time.sleep(10 * attempt)
            except Exception as e:
                logger.warning(f"[{self.platform_name}] Request failed for {url}: {e} (attempt {attempt})")
                time.sleep(5 * attempt)
        logger.error(f"[{self.platform_name}] All retries exhausted for {url}")
        return None

    def get_text(self, url: str) -> str | None:
        """Fetch raw response text."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                time.sleep(REQUEST_DELAY)
                response = self.client.get(url)
                response.raise_for_status()
                return response.text
            except Exception as e:
                logger.warning(f"[{self.platform_name}] get_text failed for {url}: {e} (attempt {attempt})")
                time.sleep(5 * attempt)
        return None

    @abstractmethod
    def search(self, keywords: str, location: str, days: int = 3) -> list[dict]:
        """
        Search for jobs matching keywords in location.
        Returns a list of job dicts with keys:
          title, company, location, salary_text, job_type,
          arrangement, description, abn, posted_date, url
        """
        raise NotImplementedError

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
