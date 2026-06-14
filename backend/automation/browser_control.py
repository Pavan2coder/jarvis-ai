import os
import time
from playwright.sync_api import sync_playwright
from backend.utils.logger import logger
from backend.automation.browser_state import state_tracker

class BrowserController:
    def __init__(self):
        self.pw = None
        self.browser = None
        self.context = None
        self.active_page = None

    def launch(self):
        """Launches headful Chromium browser via Playwright with error recovery."""
        if self.browser:
            return True

        logger.info("Initializing headful Playwright Chromium...")
        try:
            self.pw = sync_playwright().start()
            self.browser = self.pw.chromium.launch(headless=False)
            self.context = self.browser.new_context()
            self.context.on("page", self._on_page_created)
            
            # Create default first page
            self.active_page = self.context.new_page()
            self.sync_state()
            return True
        except Exception as e:
            logger.error(f"Failed to launch Playwright browser: {e}")
            self.close()
            if "Executable doesn't exist" in str(e) or "playwright install" in str(e).lower():
                raise RuntimeError(
                    "Playwright browser binaries are missing. "
                    "Please run: playwright install"
                ) from e
            raise e

    def _on_page_created(self, page):
        """Callback invoked when a new tab/page is opened."""
        page.on("close", lambda p: self._on_page_closed(p))
        page.on("load", lambda p: self.sync_state())
        self.sync_state()

    def _on_page_closed(self, page):
        """Callback invoked when a tab/page is closed."""
        self.sync_state()
        # If all pages are closed, shut down the browser
        if self.browser and len(self.context.pages) == 0:
            logger.info("All tabs closed. Shutting down browser context...")
            self.close()

    def sync_state(self):
        """Synchronizes current tab list and active state with BrowserStateTracker."""
        if not self.browser:
            state_tracker.reset()
            return
            
        try:
            pages = self.context.pages if self.context else []
            open_pages = [p for p in pages if not p.is_closed()]
            state_tracker.sync_playwright_state(
                is_running=True,
                pages=open_pages,
                active_page=self.active_page
            )
        except Exception:
            pass

    def get_active_page(self):
        """Returns the currently active page reference, launching the browser if offline."""
        self.launch()
        if not self.active_page or self.active_page.is_closed():
            pages = [p for p in self.context.pages if not p.is_closed()]
            if pages:
                self.active_page = pages[-1]
            else:
                self.active_page = self.context.new_page()
        self.sync_state()
        return self.active_page

    def new_tab(self, url: str):
        """Opens a new browser tab and navigates to the URL."""
        self.launch()
        page = self.context.new_page()
        self.active_page = page
        page.goto(url)
        self.sync_state()
        return page

    def switch_tab(self, tab_id: str) -> bool:
        """Brings a specific tab to the front by its ID."""
        if not self.browser:
            return False
            
        for page in self.context.pages:
            if not page.is_closed() and str(id(page)) == tab_id:
                self.active_page = page
                page.bring_to_front()
                self.sync_state()
                return True
        return False

    def close_tab(self, tab_id: str) -> bool:
        """Closes a specific tab by its ID."""
        if not self.browser:
            return False
            
        for page in self.context.pages:
            if not page.is_closed() and str(id(page)) == tab_id:
                page.close()
                if self.active_page == page:
                    remaining = [p for p in self.context.pages if not p.is_closed()]
                    self.active_page = remaining[-1] if remaining else None
                self.sync_state()
                return True
        return False

    def get_tabs_list(self) -> list:
        """Returns list of open tab details."""
        self.sync_state()
        return state_tracker.to_dict().get("tabs", [])

    def close(self):
        """Closes the browser context and cleans up Playwright."""
        try:
            if self.browser:
                self.browser.close()
            if self.pw:
                self.pw.stop()
        except Exception as e:
            logger.error(f"Error during browser teardown: {e}")
        finally:
            self.pw = None
            self.browser = None
            self.context = None
            self.active_page = None
            state_tracker.reset()

# Global controller instance
controller = BrowserController()

# Convenience wrapper functions for backwards compatibility:
def get_page():
    return controller.get_active_page()

def close_browser():
    controller.close()

# Forward search automations from search_engine.py
def automate_google_search(query: str) -> bool:
    from backend.automation.search_engine import google_search
    return google_search(query)

def automate_youtube_search(query: str) -> bool:
    from backend.automation.search_engine import youtube_search
    return youtube_search(query)

def automate_github_search(query: str) -> bool:
    from backend.automation.search_engine import github_search
    return github_search(query)
