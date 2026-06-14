from backend.utils.logger import logger

def google_search(query: str) -> bool:
    """Automates searching Google for the given query."""
    from backend.automation.browser_control import controller
    try:
        page = controller.get_active_page()
        logger.info(f"Navigating to Google for search query: '{query}'")
        page.goto("https://www.google.com")
        
        # Handle consent/TOS popups dynamically
        try:
            consent_btn = page.locator("button:has-text('Accept all'), button:has-text('I agree'), button:has-text('Consent')").first
            if consent_btn.is_visible(timeout=1000):
                consent_btn.click()
        except Exception:
            pass
            
        search_box = page.locator('textarea[name="q"], input[name="q"]').first
        search_box.fill(query)
        search_box.press("Enter")
        page.wait_for_load_state("load")
        controller.sync_state()
        logger.info(f"Google search for '{query}' completed successfully.")
        return True
    except Exception as e:
        logger.error(f"Google search automation failed: {e}")
        controller.close()
        return False

def youtube_search(query: str) -> bool:
    """Automates opening YouTube and searching for the given query."""
    from backend.automation.browser_control import controller
    try:
        page = controller.get_active_page()
        logger.info(f"Navigating to YouTube for search query: '{query}'")
        page.goto("https://www.youtube.com")
        
        # Handle cookie consent buttons dynamically
        try:
            consent_btn = page.locator("button:has-text('Accept all'), button:has-text('Reject all')").first
            if consent_btn.is_visible(timeout=1000):
                consent_btn.click()
        except Exception:
            pass
            
        search_box = page.locator('input[name="search_query"], input#search').first
        search_box.fill(query)
        search_box.press("Enter")
        page.wait_for_load_state("load")
        controller.sync_state()
        logger.info(f"YouTube search for '{query}' completed successfully.")
        return True
    except Exception as e:
        logger.error(f"YouTube search automation failed: {e}")
        controller.close()
        return False

def github_search(query: str) -> bool:
    """Automates opening GitHub and searching for the given query."""
    from backend.automation.browser_control import controller
    try:
        page = controller.get_active_page()
        logger.info(f"Navigating to GitHub for search query: '{query}'")
        page.goto("https://github.com")
        
        # Handle GitHub dynamic query input builder
        search_button = page.locator("button.header-search-button").first
        if search_button.is_visible(timeout=2000):
            search_button.click()
            
        search_box = page.locator("input#query-builder-input, input[name='q']").first
        search_box.fill(query)
        search_box.press("Enter")
        page.wait_for_load_state("load")
        controller.sync_state()
        logger.info(f"GitHub search for '{query}' completed successfully.")
        return True
    except Exception as e:
        logger.error(f"GitHub search automation failed: {e}")
        controller.close()
        return False
