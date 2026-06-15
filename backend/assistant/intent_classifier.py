import re
import difflib
import json
from typing import Dict, Any
from backend.core import config
from backend.utils.logger import logger

# Speech recognition common mistake mappings
SPEECH_REPLACEMENTS = {
    "what's app": "whatsapp",
    "whats app": "whatsapp",
    "crome": "chrome",
    "crom": "chrome",
    "microsoft edge": "edge",
    "ms edge": "edge",
    "note pad": "notepad",
    "note-pad": "notepad",
    "paint brush": "paint",
    "ms paint": "paint",
    "file manager": "explorer",
    "file explorer": "explorer",
    "vs code": "vscode",
    "visual studio code": "vscode",
    "command prompt": "cmd",
    "power shell": "powershell",
    "task manager": "taskmgr",
    "system settings": "settings",
    "spotyfy": "spotify",
    "spotifi": "spotify",
    "g mail": "gmail",
    "face book": "facebook",
    "you tube": "youtube",
    "u tube": "youtube",
}

def normalize_text(text: str) -> str:
    """Cleans text, removes punctuation, lowercases, and maps speech errors."""
    if not text:
        return ""
    text = text.lower().strip()
    
    # Replace speech recognition errors
    for key, value in SPEECH_REPLACEMENTS.items():
        text = re.sub(r'\b' + re.escape(key) + r'\b', value, text)
        
    return text

def extract_number(text: str) -> int:
    """Extracts a percentage or value number from text (e.g. 'set volume to 80')."""
    match = re.search(r'\b(\d{1,3})\b', text)
    if match:
        val = int(match.group(1))
        return min(max(val, 0), 100)  # Bound values to 0-100%
    return None

def match_app(candidate: str, threshold: float = 0.5) -> str:
    """Matches candidate against registered apps in configurations using difflib."""
    if not candidate:
        return ""
    
    # Gather all configured app names
    apps = list(config.APPS.keys()) + list(config.CLOSE_PROCESSES.keys())
    apps = list(set(apps)) # Deduplicate
    
    candidate = candidate.strip()
    
    # 1. Direct exact or substring match
    for app in apps:
        if app == candidate or app in candidate or candidate in app:
            return app
            
    # 2. Fuzzy match
    matches = difflib.get_close_matches(candidate, apps, n=1, cutoff=threshold)
    if matches:
        return matches[0]
        
    return ""

# Gesture Command Aliases & Fuzzy Matching configurations
ENABLE_GESTURE_ALIASES = [
    "start gesture control",
    "enable gestures",
    "turn on camera",
    "activate gestures",
    "start gestures",
    "enable gesture mode",
    "turn on gesture control",
    "start gesture mode",
    "activate gesture mode"
]

DISABLE_GESTURE_ALIASES = [
    "stop gesture control",
    "disable gestures",
    "turn off gesture mode",
    "turn off camera",
    "deactivate gestures",
    "stop gestures",
    "disable gesture control",
    "stop gesture mode",
    "turn off gesture control",
    "top gesture control"  # Common misheard variant
]

def get_best_alias_match(text: str, aliases: list, threshold: float = 0.80) -> tuple:
    """Computes similarity ratios against a list of aliases and returns the best match."""
    best_match = None
    best_score = 0.0
    for alias in aliases:
        score = difflib.SequenceMatcher(None, text, alias).ratio()
        if score > best_score:
            best_score = score
            best_match = alias
    if best_score >= threshold:
        return best_match, best_score
    return None, 0.0

def classify_intent(raw_text: str) -> Dict[str, Any]:
    """Classifies the user input command into a structured intent and extracts entities."""
    logger.info(f"Classifying intent for input: '{raw_text}'")
    
    normalized = normalize_text(raw_text)
    
    # Default intent
    intent = "query_llm"
    confidence = 0.5
    entities = {}
    
    # 0. GESTURE CONTROL INTENTS (fuzzy matching & conflict prevention)
    best_enable, enable_score = get_best_alias_match(normalized, ENABLE_GESTURE_ALIASES, threshold=0.80)
    best_disable, disable_score = get_best_alias_match(normalized, DISABLE_GESTURE_ALIASES, threshold=0.80)
    
    if enable_score >= 0.80 and disable_score >= 0.80 and abs(enable_score - disable_score) < 0.03:
        # Contradictory fuzzy scoring (both match above threshold with negligible difference)
        logger.warning(f"Contradictory gesture command detected via fuzzy matching: '{raw_text}' (enable={enable_score:.2f}, disable={disable_score:.2f})")
    elif enable_score > disable_score and enable_score >= 0.80:
        return {
            "intent": "enable_gestures",
            "confidence": float(enable_score),
            "entities": {},
            "raw_text": raw_text
        }
    elif disable_score > enable_score and disable_score >= 0.80:
        return {
            "intent": "disable_gestures",
            "confidence": float(disable_score),
            "entities": {},
            "raw_text": raw_text
        }

    # Keyword fallback for standard regex-based matching
    has_gesture_kw = bool(re.search(r'\b(gesture|gestures|camera)\b', normalized))
    if has_gesture_kw:
        has_enable = bool(re.search(r'\b(start|enable|on|activate|initialize)\b', normalized))
        has_disable = bool(re.search(r'\b(stop|disable|off|quit|deactivate)\b', normalized))
        
        if has_enable and has_disable:
            logger.warning(f"Contradictory gesture command detected: '{raw_text}'")
        elif has_enable:
            return {
                "intent": "enable_gestures",
                "confidence": 0.90,
                "entities": {},
                "raw_text": raw_text
            }
        elif has_disable:
            return {
                "intent": "disable_gestures",
                "confidence": 0.90,
                "entities": {},
                "raw_text": raw_text
            }
            
    # 1. CAMERA_CAPTURE INTENT
    if any(phrase in normalized for phrase in ["take photo", "capture image", "save picture", "selfie", "take a photo", "take a selfie", "take picture", "take a picture"]):
        intent = "camera_capture"
        confidence = 0.95
        
    # 2. SCREENSHOT INTENT
    elif any(phrase in normalized for phrase in ["screenshot", "screen capture", "take picture of screen", "capture screen"]):
        intent = "screenshot"
        confidence = 0.95
        
    # 3. WORKFLOW_AUTOMATION INTENT
    elif any(phrase in normalized for phrase in ["prepare coding setup", "prepare study mode", "prepare meeting mode"]):
        intent = "workflow_automation"
        confidence = 0.98
        if "coding setup" in normalized:
            entities["workflow_id"] = "coding_setup"
        elif "study mode" in normalized:
            entities["workflow_id"] = "study_mode"
        elif "meeting mode" in normalized:
            entities["workflow_id"] = "meeting_mode"
            
    # 4. BROWSER_AUTOMATION INTENT
    elif any(x in normalized for x in ["open youtube and search", "search google for", "open github and search"]):
        intent = "browser_automation"
        confidence = 0.98
        if "open youtube and search" in normalized:
            entities["action"] = "search_youtube"
            entities["query"] = normalized.split("open youtube and search")[-1].strip()
        elif "open github and search" in normalized:
            entities["action"] = "search_github"
            entities["query"] = normalized.split("open github and search")[-1].strip()
        elif "search google for" in normalized:
            entities["action"] = "search_google"
            entities["query"] = normalized.split("search google for")[-1].strip()
        
    # 2. DIAGNOSTICS INTENT
    elif any(phrase in normalized for phrase in ["cpu", "ram", "gpu", "processor", "memory", "graphics", "system info", "diagnostics"]):
        intent = "diagnostics"
        confidence = 0.90
        # Determine specific target entity
        target = "all"
        for t in ["cpu", "ram", "gpu"]:
            if t in normalized:
                target = t
                break
        entities["target"] = target
        
    # 3. CLOSE_APP INTENT
    elif any(normalized.startswith(x) for x in ["close ", "kill ", "stop ", "terminate "]) and not any(w in normalized for w in ["shutdown", "restart", "reboot", "sleep", "gesture"]):
        # Extract candidate app target
        candidate = normalized
        for word in ["close", "kill", "stop", "terminate", "the app", "app", "window", "program", "please", "the"]:
            candidate = re.sub(r'\b' + re.escape(word) + r'\b', '', candidate)
            
        app_name = match_app(candidate)
        if app_name:
            intent = "close_app"
            confidence = 0.95
            entities["app_name"] = app_name
        else:
            # Fallback to general close target
            intent = "close_app"
            confidence = 0.80
            entities["app_name"] = candidate.strip()
            
    # 4. OPEN_APP INTENT
    elif any(normalized.startswith(x) for x in ["open ", "launch ", "start "]) and not any(w in normalized for w in ["gesture", "folder", "directory"]):
        # Extract candidate app target
        candidate = normalized
        for word in ["open", "launch", "start", "the app", "app", "window", "program", "please", "the"]:
            candidate = re.sub(r'\b' + re.escape(word) + r'\b', '', candidate)
            
        app_name = match_app(candidate)
        if app_name:
            intent = "open_app"
            confidence = 0.95
            entities["app_name"] = app_name
        else:
            # Try matching folder paths or keep as general launch target
            intent = "open_app"
            confidence = 0.80
            entities["app_name"] = candidate.strip()
            
    # 5. SEARCH INTENT
    elif any(normalized.startswith(x) for x in ["search for ", "search ", "google ", "look up ", "lookup "]):
        intent = "search"
        confidence = 0.95
        # Extract search query
        query = normalized
        for word in ["search for", "search", "google", "look up", "lookup", "please"]:
            query = re.sub(r'\b' + re.escape(word) + r'\b', '', query)
        entities["query"] = query.strip()
        
    # 6. SYSTEM_CONTROL INTENT
    elif any(x in normalized for x in ["volume", "brightness", "dim", "mute", "silence", "shutdown", "shut down", "restart", "reboot", "lock", "sleep"]):
        intent = "system_control"
        confidence = 0.90
        
        # Determine specific action & value entities
        if "volume" in normalized or "mute" in normalized or "silence" in normalized:
            val = extract_number(normalized)
            if val is not None:
                entities["action"] = "set_volume"
                entities["value"] = val
            elif any(w in normalized for w in ["up", "increase", "louder", "raise"]):
                entities["action"] = "volume_up"
            elif any(w in normalized for w in ["down", "decrease", "quieter", "lower", "reduce"]):
                entities["action"] = "volume_down"
            elif any(w in normalized for w in ["mute", "silence"]):
                entities["action"] = "mute"
                
        elif "brightness" in normalized or "dim" in normalized:
            val = extract_number(normalized)
            if val is not None:
                entities["action"] = "set_brightness"
                entities["value"] = val
            elif any(w in normalized for w in ["up", "increase", "brighter", "raise"]):
                entities["action"] = "brightness_up"
            elif any(w in normalized for w in ["down", "decrease", "dim", "lower"]):
                entities["action"] = "brightness_down"
                
        elif any(w in normalized for w in ["shutdown", "shut down"]):
            entities["action"] = "shutdown"
        elif any(w in normalized for w in ["restart", "reboot"]):
            entities["action"] = "restart"
        elif "lock" in normalized:
            entities["action"] = "lock"
        elif "sleep" in normalized:
            entities["action"] = "sleep"

    # Match confidence tuning (if intent remains default query_llm but uses trigger words)
    if intent == "query_llm":
        if any(w in normalized for w in ["hello", "hi", "hey", "what's up"]):
            intent = "greeting"
            confidence = 0.95
        elif any(w in normalized for w in ["goodbye", "bye", "exit", "quit", "shutdown jarvis"]):
            intent = "exit"
            confidence = 0.95

    return {
        "intent": intent,
        "confidence": confidence,
        "entities": entities,
        "raw_text": raw_text
    }

def classify_intent_json(raw_text: str) -> str:
    """Classifies user input and returns a structured JSON string."""
    return json.dumps(classify_intent(raw_text), indent=2)
