from backend.core import config

GEMINI_API_KEY = config.GEMINI_API_KEY
GEMINI_MODEL = config.GEMINI_MODEL


from brain.conversation_memory import ThreadSafeConversationMemory

# Short conversation memory so Jarvis can follow up (thread-safe)
chat_history = ThreadSafeConversationMemory()
MAX_HISTORY  = 8

def gemini_ready():
    return bool(GEMINI_API_KEY)

def _gemini_can_call(model):
    """Real probe: does a tiny generateContent succeed on this model?
    Catches free-tier 'limit: 0' models that exist but can't actually be used.
    """
    from network.api_client import GeminiProvider
    provider = GeminiProvider(api_key=GEMINI_API_KEY, model_name=model)
    return provider.verify()

def verify_gemini():
    """Pick a model the key can ACTUALLY call (not just one that exists)."""
    global GEMINI_MODEL
    if not gemini_ready():
        return False, "No Gemini API key set (.env GEMINI_API_KEY is empty)."

    # Try the configured model first, then known free-tier-friendly fallbacks
    candidates = [GEMINI_MODEL, "gemini-2.5-flash", "gemini-2.5-flash-lite",
                  "gemini-flash-latest", "gemini-flash-lite-latest"]
    seen, last = [], ""
    for mdl in candidates:
        if mdl in seen:
            continue
        seen.append(mdl)
        success, msg = _gemini_can_call(mdl)
        if success:
            GEMINI_MODEL = mdl
            # Update registry provider model configuration
            from network.api_client import registry, GeminiProvider as NetGeminiProvider
            try:
                provider = registry.get("gemini")
                if isinstance(provider, NetGeminiProvider):
                    provider.model_name = mdl
            except Exception:
                pass
            return True, f"Gemini online — using model '{GEMINI_MODEL}'."
        last = f"{mdl}: {msg}"
    return False, (f"Key is valid but every model was blocked (last: {last}). "
                   "Your free-tier quota may be exhausted — try again later or check billing.")

def ask_gemini(prompt):
    """Send prompt (+ short history) to Gemini and return the spoken answer."""
    if not gemini_ready():
        return ("My AI brain is offline — I need a Gemini API key. "
                "Get one free at Google AI Studio and set it in the config.")

    from network.api_client import registry, GeminiProvider as NetGeminiProvider
    try:
        provider = registry.get("gemini")
        if isinstance(provider, NetGeminiProvider):
            # Sync any dynamic updates to GEMINI_MODEL
            provider.model_name = GEMINI_MODEL

        # Convert history format
        history_list = list(chat_history[-MAX_HISTORY:])
        answer = provider.generate(
            prompt=prompt,
            history=history_list,
            system_instruction=config.SYSTEM_PROMPT
        )
        
        # Remember the exchange
        chat_history.append({"role": "user",  "text": prompt})
        chat_history.append({"role": "model", "text": answer})
        return answer
    except Exception as e:
        print(f"  ⚠️  Gemini error: {e}")
        # Return fallback error indicators expected by caller or fallback router
        if "Authentication failed" in str(e) or "401" in str(e) or "403" in str(e):
            return "My AI brain returned an error: Authentication failed. Please check your key."
        elif "429" in str(e) or "Quota exceeded" in str(e):
            return "My AI brain returned an error: Quota exceeded or rate limited."
        return "Sorry, I couldn't reach my AI brain just now."

