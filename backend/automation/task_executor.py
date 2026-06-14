import os
import sys
import time
import subprocess
from backend.utils.logger import logger

def execute_task(step: dict) -> bool:
    """
    Executes a single workflow step action.
    
    Supported Action Types:
        - speak: Speaks a text message.
        - open_folder: Opens a file folder or workspace directory.
        - launch_app: Launches an executable by registered name.
        - browser_search: Automates a browser search tab via Playwright.
        - gesture_profile: Switches the active vision gesture profile.
        - system_control: Sets system volume or brightness level.
        - sleep: Pauses execution for a specified duration.
    """
    action = step.get("action", "").lower()
    target = step.get("target")
    
    logger.info(f"Executing workflow action: '{action}' targeting '{target}'")
    
    try:
        if action == "speak":
            from backend.voice.audio_engine import speak
            speak(str(target))
            return True
            
        elif action == "open_folder":
            from backend.core import config
            # Resolve friendly config folders (e.g. "projects", "downloads")
            path = config.FOLDERS.get(target, target)
            if os.path.exists(path):
                if sys.platform == "win32":
                    os.startfile(path)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", path])
                else:
                    subprocess.Popen(["xdg-open", path])
                return True
            else:
                logger.warning(f"Workflow failed to open folder: path does not exist '{path}'")
                return False
                
        elif action == "launch_app":
            from backend.system.system_ops import launch_app
            return launch_app(str(target))
            
        elif action == "browser_search":
            from backend.automation.browser_control import automate_google_search, automate_youtube_search, automate_github_search
            engine = step.get("engine", "google").lower()
            query = step.get("query", str(target))
            
            if engine == "google":
                return automate_google_search(query)
            elif engine == "youtube":
                return automate_youtube_search(query)
            elif engine == "github":
                return automate_github_search(query)
            else:
                logger.warning(f"Unrecognized search engine in workflow: '{engine}'")
                return False
                
        elif action == "gesture_profile":
            from backend.vision.profile_manager import profile_manager
            return profile_manager.set_active_profile(str(target))
            
        elif action == "system_control":
            from backend.system.system_ops import set_volume_percent, set_brightness_percent
            target_type = step.get("control_type", "volume").lower()
            value = int(target)
            
            if target_type == "volume":
                success = set_volume_percent(value)
                if not success:
                    logger.warning(f"Failed to set system volume to {value}%. Continuing workflow execution.")
                return True
            elif target_type == "brightness":
                success = set_brightness_percent(value)
                if not success:
                    logger.warning(f"Failed to set system brightness to {value}%. Continuing workflow execution.")
                return True
            else:
                logger.warning(f"Unrecognized system control type: '{target_type}'")
                return False
                
        elif action == "sleep":
            duration = float(target)
            time.sleep(duration)
            return True
            
        else:
            logger.warning(f"Unknown workflow action type: '{action}'")
            return False
            
    except Exception as e:
        logger.error(f"Error executing step action '{action}': {e}")
        return False
