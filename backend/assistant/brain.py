import os
from backend.core import config
from backend.utils.dotenv import load_dotenv

GEMINI_API_KEY = ""
GEMINI_MODEL = config.GEMINI_MODEL

load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Short conversation memory so Jarvis can follow up
chat_history = []        # list of {"role": "user"/"model", "text": ...}
MAX_HISTORY  = 8

def gemini_ready():
    return bool(GEMINI_API_KEY)

def _gemini_can_call(model):
    """Real probe: does a tiny generateContent succeed (200) on this model?
    Catches free-tier 'limit: 0' models that exist but can't actually be used."""
    import requests
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={GEMINI_API_KEY}")
    try:
        r = requests.post(url, json={"contents": [{"parts": [{"text": "hi"}]}],
                                     "generationConfig": {"maxOutputTokens": 5}}, timeout=15)
        return r.status_code, r.text[:140]
    except Exception as e:
        return None, str(e)

def verify_gemini():
    """Pick a model the key can ACTUALLY call (not just one that exists)."""
    global GEMINI_MODEL
    if not gemini_ready():
        return False, "No Gemini API key set (.env GEMINI_API_KEY is empty)."
    try:
        import requests
    except ImportError:
        return False, "The 'requests' package is missing. Run: pip install requests"

    # Try the configured model first, then known free-tier-friendly fallbacks
    candidates = [GEMINI_MODEL, "gemini-2.5-flash", "gemini-2.5-flash-lite",
                  "gemini-flash-latest", "gemini-flash-lite-latest"]
    seen, last = [], ""
    for mdl in candidates:
        if mdl in seen:
            continue
        seen.append(mdl)
        code, body = _gemini_can_call(mdl)
        if code == 200:
            GEMINI_MODEL = mdl
            return True, f"Gemini online — using model '{GEMINI_MODEL}'."
        last = f"{mdl}: {code}"
        # 429 = quota/limit 0 on this model → just try the next one
    return False, (f"Key is valid but every model was blocked (last: {last}). "
                   "Your free-tier quota may be exhausted — try again later or check billing.")

def ask_gemini(prompt):
    """Send prompt (+ short history) to Gemini and return the spoken answer."""
    if not gemini_ready():
        return ("My AI brain is offline — I need a Gemini API key. "
                "Get one free at Google AI Studio and set it in the config.")
    try:
        import requests
    except ImportError:
        return "I need the requests package for my AI brain. Run pip install requests."

    # Build the contents array: system + recent history + new prompt
    contents = []
    for turn in chat_history[-MAX_HISTORY:]:
        contents.append({"role": turn["role"], "parts": [{"text": turn["text"]}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    body = {
        "system_instruction": {"parts": [{"text": config.SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 256},
    }
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}")
    try:
        r = requests.post(url, json=body, timeout=20)
        if r.status_code != 200:
            return f"My AI brain returned an error, code {r.status_code}."
        data = r.json()
        answer = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Remember the exchange
        chat_history.append({"role": "user",  "text": prompt})
        chat_history.append({"role": "model", "text": answer})
        return answer
    except Exception as e:
        print(f"  ⚠️  Gemini error: {e}")
        return "Sorry, I couldn't reach my AI brain just now."
