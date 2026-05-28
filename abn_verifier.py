"""
ABN Verifier Module
Uses Playwright (headless Chromium) to check the Australian Business Number
lookup service at abn.business.gov.au.

Only called when an ABN is explicitly found in a job listing.
"""

import logging
import re

logger = logging.getLogger(__name__)

ABN_DIGITS_PATTERN = re.compile(r'\D')   # Strips non-digits from raw ABN string


def _clean_abn(raw_abn: str) -> str:
    """Strip spaces and non-digit characters from an ABN string."""
    return ABN_DIGITS_PATTERN.sub('', raw_abn)


def verify_abn(raw_abn: str) -> dict:
    """
    Verify an ABN using the ABN Lookup website.

    Args:
        raw_abn: ABN string as found in the job listing (may contain spaces)

    Returns:
        dict with keys:
            valid (bool)         - True if ABN exists and is Active
            entity_name (str)    - Registered business name (empty if not found)
            status (str)         - "Active", "Cancelled", "Not found", or error message
            abn_formatted (str)  - ABN in standard XX XXX XXX XXX format
    """
    abn_digits = _clean_abn(raw_abn)
    abn_formatted = f"{abn_digits[:2]} {abn_digits[2:5]} {abn_digits[5:8]} {abn_digits[8:]}" if len(abn_digits) == 11 else abn_digits

    if len(abn_digits) != 11:
        logger.warning(f"ABN '{raw_abn}' does not have 11 digits after cleaning (got {len(abn_digits)})")
        return {
            'valid': False,
            'entity_name': '',
            'status': 'Invalid ABN format',
            'abn_formatted': abn_formatted,
        }

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            url = f"https://www.abn.business.gov.au/ABN/View?id={abn_digits}"
            logger.info(f"Checking ABN {abn_formatted} at {url}")

            try:
                page.goto(url, timeout=20000)
                page.wait_for_load_state('networkidle', timeout=15000)
            except PlaywrightTimeout:
                logger.warning(f"Timeout loading ABN lookup page for {abn_formatted}")
                browser.close()
                return {
                    'valid': False,
                    'entity_name': '',
                    'status': 'Lookup timeout',
                    'abn_formatted': abn_formatted,
                }

            page_text = page.inner_text('body')

            # Check for "not found" or error
            if 'ABN not found' in page_text or 'No record found' in page_text:
                browser.close()
                return {
                    'valid': False,
                    'entity_name': '',
                    'status': 'Not found',
                    'abn_formatted': abn_formatted,
                }

            # Extract entity name
            entity_name = ''
            try:
                # The page shows "Entity name: XYZ" in a table
                name_el = page.query_selector('td:has-text("Entity name") + td')
                if not name_el:
                    name_el = page.query_selector('th:has-text("Entity name") + td')
                if name_el:
                    entity_name = name_el.inner_text().strip()
                else:
                    # Fallback: look for heading
                    h_el = page.query_selector('h1, h2, h3')
                    if h_el:
                        entity_name = h_el.inner_text().strip()
            except Exception:
                pass

            # Extract status
            status = 'Unknown'
            try:
                status_el = page.query_selector('td:has-text("ABN status") + td')
                if not status_el:
                    status_el = page.query_selector('th:has-text("ABN status") + td')
                if status_el:
                    status = status_el.inner_text().strip()
                elif 'Active' in page_text:
                    status = 'Active'
                elif 'Cancelled' in page_text:
                    status = 'Cancelled'
            except Exception:
                pass

            browser.close()

            valid = 'active' in status.lower()
            logger.info(f"ABN {abn_formatted}: {entity_name} — {status} (valid={valid})")

            return {
                'valid': valid,
                'entity_name': entity_name,
                'status': status,
                'abn_formatted': abn_formatted,
            }

    except ImportError:
        logger.error("Playwright is not installed. Run: pip install playwright && playwright install chromium")
        return {
            'valid': False,
            'entity_name': '',
            'status': 'Playwright not installed',
            'abn_formatted': abn_formatted,
        }
    except Exception as e:
        logger.error(f"ABN verification error for {abn_formatted}: {e}")
        return {
            'valid': False,
            'entity_name': '',
            'status': f'Error: {e}',
            'abn_formatted': abn_formatted,
        }
