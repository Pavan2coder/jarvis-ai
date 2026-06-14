from typing import Dict, List, Optional
from backend.utils.logger import logger

class TabState:
    def __init__(self, tab_id: str, title: str, url: str, is_active: bool):
        self.id = tab_id
        self.title = title
        self.url = url
        self.is_active = is_active

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "is_active": self.is_active
        }

class BrowserStateTracker:
    def __init__(self):
        self.is_running = False
        self.active_tab_id = None
        self.tabs: Dict[str, TabState] = {}

    def reset(self):
        """Resets the state back to default offline state."""
        self.is_running = False
        self.active_tab_id = None
        self.tabs.clear()
        self.emit_state()

    def sync_playwright_state(self, is_running: bool, pages: list, active_page) -> None:
        """Synchronizes tracking state with the live Playwright browser pages."""
        self.is_running = is_running
        self.tabs.clear()
        self.active_tab_id = None

        if not is_running or not pages:
            self.emit_state()
            return

        for page in pages:
            try:
                # Playwright's page might have closed asynchronously, check is_closed
                if page.is_closed():
                    continue
                    
                tab_id = str(id(page))
                title = page.title()
                url = page.url
                is_active = (page == active_page)
                
                if is_active:
                    self.active_tab_id = tab_id
                    
                self.tabs[tab_id] = TabState(tab_id, title, url, is_active)
            except Exception as e:
                pass
                
        self.emit_state()

    def to_dict(self) -> dict:
        """Prepares payload dict for websocket updates."""
        return {
            "running": self.is_running,
            "active_tab_id": self.active_tab_id,
            "tabs": [tab.to_dict() for tab in self.tabs.values()]
        }

    def emit_state(self):
        """Broadcasts browser automation state to Connected Websocket Clients (HUD)."""
        try:
            from backend.websocket.events import dispatcher, JarvisEvent, JarvisEventType
            from backend.websocket.socket_manager import manager
            
            event = JarvisEvent(JarvisEventType.SYSTEM_UPDATE, {
                "browser_state": self.to_dict()
            })
            dispatcher.emit_sync(event, loop=manager.loop)
        except Exception as e:
            pass

# Singleton instance
state_tracker = BrowserStateTracker()
