import os
import time
from playwright.sync_api import sync_playwright
from backend.utils.logger import logger

_browser_context = {
    "playwright": None,
    "browser": None,
    "context": None,
    "page": None
}

def get_page():
    """Initializes and returns a running browser page instance (headful Chromium)."""
    global _browser_context
    if _browser_context["page"] and not _browser_context["page"].is_closed():
        return _browser_context["page"]
        
    logger.info("Launching headful Chromium browser via Playwright...")
    pw = sync_playwright().start()
    
    # Launch headful browser so user can see it and interact with it
    browser = pw.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    
    _browser_context["playwright"] = pw
    _browser_context["browser"] = browser
    _browser_context["context"] = context
    _browser_context["page"] = page
    return page

def close_browser():
    """Closes the active browser and cleans up resources."""
    global _browser_context
    try:
        if _browser_context["page"]:
            _browser_context["page"].close()
        if _browser_context["browser"]:
            _browser_context["browser"].close()
        if _browser_context["playwright"]:
            _browser_context["playwright"].stop()
    except Exception as e:
        logger.error(f"Error closing Playwright browser: {e}")
    finally:
        _browser_context = {
            "playwright": None,
            "browser": None,
            "context": None,
            "page": None
        }

def automate_google_search(query: str) -> bool:
    """Opens Google, searches for query, and waits for navigation."""
    try:
        page = get_page()
        page.goto("https://www.google.com")
        
        # Accept terms/consent dialog if present (common in Europe/some regions, good for compatibility)
        try:
            consent_btn = page.locator("button:has-text('Accept all'), button:has-text('I agree'), button:has-text('Consent')").first
            if consent_btn.is_visible(timeout=1000):
                consent_btn.click()
        except Exception:
            pass
            
        # Search box selector: standard is 'textarea[name="q"]' or 'input[name="q"]'
        search_box = page.locator('textarea[name="q"], input[name="q"]').first
        search_box.fill(query)
        search_box.press("Enter")
        page.wait_for_load_state("load")
        logger.info(f"Google search automation for '{query}' completed.")
        return True
    except Exception as e:
        logger.error(f"Google search automation failed: {e}")
        close_browser()
        return False

def automate_youtube_search(query: str) -> bool:
    """Opens YouTube, searches for query, and waits for results."""
    try:
        page = get_page()
        page.goto("https://www.youtube.com")
        
        # Accept consent if present
        try:
            consent_btn = page.locator("button:has-text('Accept all'), button:has-text('Reject all')").first
            if consent_btn.is_visible(timeout=1000):
                consent_btn.click()
        except Exception:
            pass
            
        # Search box selector: 'input[name="search_query"]' or 'input#search'
        search_box = page.locator('input[name="search_query"], input#search').first
        search_box.fill(query)
        search_box.press("Enter")
        page.wait_for_load_state("load")
        logger.info(f"YouTube search automation for '{query}' completed.")
        return True
    except Exception as e:
        logger.error(f"YouTube search automation failed: {e}")
        close_browser()
        return False

def automate_github_search(query: str) -> bool:
    """Opens GitHub, searches for query, and waits for results."""
    try:
        page = get_page()
        page.goto("https://github.com")
        
        # Click search button or trigger input field
        # GitHub's header search is often dynamic (requires clicking to activate)
        search_button = page.locator("button.header-search-button").first
        if search_button.is_visible(timeout=2000):
            search_button.click()
            
        search_box = page.locator("input#query-builder-input, input[name='q']").first
        search_box.fill(query)
        search_box.press("Enter")
        page.wait_for_load_state("load")
        logger.info(f"GitHub search automation for '{query}' completed.")
        return True
    except Exception as e:
        logger.error(f"GitHub search automation failed: {e}")
        close_browser()
        return False
