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

_QUERY_LEADING_FILLER = re.compile(r'^(?:(?:and|about|for|to|me|the|on)\b\s*)+')

def clean_query(text: str) -> str:
    """Tidy an extracted search query: collapse whitespace and strip leading
    connective filler ('and', 'about', 'for', …) left over after trigger words
    are removed, so 'google and search about chat gpt' yields 'chat gpt' rather
    than 'and  about chat gpt'."""
    text = re.sub(r'\s+', ' ', text).strip()
    text = _QUERY_LEADING_FILLER.sub('', text).strip()
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

# Google web apps: spoken word -> URL. Words in GOOGLE_NEEDS_PREFIX only count
# when "google" is also said ("open excel" stays the desktop app).
GOOGLE_SERVICES = {
    "gmail": "https://mail.google.com", "email": "https://mail.google.com",
    "emails": "https://mail.google.com", "mail": "https://mail.google.com",
    "inbox": "https://mail.google.com",
    "sheets": "https://docs.google.com/spreadsheets", "sheet": "https://docs.google.com/spreadsheets",
    "spreadsheet": "https://docs.google.com/spreadsheets", "excel": "https://docs.google.com/spreadsheets",
    "docs": "https://docs.google.com/document", "doc": "https://docs.google.com/document",
    "document": "https://docs.google.com/document", "word": "https://docs.google.com/document",
    "slides": "https://docs.google.com/presentation", "presentation": "https://docs.google.com/presentation",
    "powerpoint": "https://docs.google.com/presentation",
    "drive": "https://drive.google.com", "calendar": "https://calendar.google.com",
    "meet": "https://meet.google.com", "maps": "https://maps.google.com",
    "photos": "https://photos.google.com", "keep": "https://keep.google.com",
    "classroom": "https://classroom.google.com", "forms": "https://docs.google.com/forms",
    "contacts": "https://contacts.google.com",
}
GOOGLE_NEEDS_PREFIX = {"sheet", "spreadsheet", "excel", "doc", "document", "word", "presentation",
                       "powerpoint", "drive", "meet", "maps", "photos", "keep", "forms", "contacts"}
_EMAIL_WORD = re.compile(r"\b(e-?mails?|mails?|inbox|gmail)\b")
_EMAIL_ASK = re.compile(r"\b(check|read|any|what|which|new|unread|latest|recent|got|get|updates?)\b")


def google_target(normalized: str):
    """Return (service_word, leftover_name) if this asks to open a Google app, else None."""
    if not re.match(r"(open|launch|start|show|go to)\b", normalized):
        return None
    said_google = re.search(r"\bgoogle\b", normalized)
    for word in GOOGLE_SERVICES:
        if re.search(r"\b" + word + r"\b", normalized) and (said_google or word not in GOOGLE_NEEDS_PREFIX):
            name = re.sub(r"\b(open|launch|start|show|go to|google|my|the|a|in|on|from|file|called|named|please|"
                          + "|".join(GOOGLE_SERVICES) + r")\b", " ", normalized)
            return word, re.sub(r"\s+", " ", name).strip()
    return None


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
    
    # 0. VIRTUAL KEYBOARD INTENTS — checked BEFORE gesture (since "gesture keyboard"
    #    also contains "gesture") and before open/close app (so "open/close keyboard"
    #    don't route to app launch/kill).
    if "keyboard" in normalized or "air type" in normalized:
        if any(w in normalized for w in ["close", "hide", "stop", "disable", "exit", "quit"]) or re.search(r"\boff\b", normalized):
            return {"intent": "disable_keyboard", "confidence": 0.95, "entities": {}, "raw_text": raw_text}
        return {"intent": "enable_keyboard", "confidence": 0.95, "entities": {}, "raw_text": raw_text}

    # 0.1 GESTURE / VIRTUAL-MOUSE CONTROL INTENTS.
    #     Deterministic: if the command is about gesture control (or hand/virtual
    #     mouse), decide enable vs disable by explicit keywords, DEFAULTING TO
    #     ENABLE when no disable word is present. So "open hand gesture control",
    #     "gesture control", "start gestures" all ENABLE; only "stop/disable/turn
    #     off/deactivate" DISABLE. (Replaces fuzzy matching that mislabeled
    #     "open hand gesture control" as disable.)
    gesture_ctx = bool(re.search(r"\b(gesture|gestures)\b", normalized)) or \
                  any(p in normalized for p in ["virtual mouse", "mouse control", "hand mouse", "hand control"])
    if gesture_ctx:
        is_disable = bool(re.search(r"\b(stop|disable|deactivate|quit|end|close|kill|off)\b", normalized))
        return {
            "intent": "disable_gestures" if is_disable else "enable_gestures",
            "confidence": 0.95,
            "entities": {},
            "raw_text": raw_text,
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
            entities["query"] = clean_query(normalized.split("open youtube and search")[-1])
        elif "open github and search" in normalized:
            entities["action"] = "search_github"
            entities["query"] = clean_query(normalized.split("open github and search")[-1])
        elif "search google for" in normalized:
            entities["action"] = "search_google"
            entities["query"] = clean_query(normalized.split("search google for")[-1])
        
    # GOOGLE: email readout / open Google apps (before open_app, which would grab "excel")
    elif _EMAIL_WORD.search(normalized) and _EMAIL_ASK.search(normalized) and not normalized.startswith("open"):
        intent = "email_updates"
        confidence = 0.95
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
    elif any(normalized.startswith(x) for x in ["open ", "launch ", "start "]) and not any(w in normalized for w in ["gesture", "folder", "directory", "desktop", "documents", "downloads"]):
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
        entities["query"] = clean_query(query)
        
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
        # Whole words only ("hi" is inside "something"), and only short
        # utterances: "hey what is a black hole" is a question, not a greeting.
        if re.search(r"\b(hello|hi|hey|what's up)\b", normalized) and len(normalized.split()) <= 4:
            intent = "greeting"
            confidence = 0.95
        elif re.search(r"\b(goodbye|bye|exit|quit|shutdown jarvis)\b", normalized):
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
