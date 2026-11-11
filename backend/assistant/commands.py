"""Thin command dispatcher.

`handle_command` is the single public entry point (used by the command worker in
backend/main.py and the /command HTTP route). It classifies the incoming text
into an intent, then dispatches in three layers:

  1. Layer A — plugin intent handlers        (exact intent match)
  2. Layer B — plugin predicate fallbacks     (ordered keyword/substring matching)
  3. Layer C — the centralized LLM router      (anything unmatched)

All command logic lives in the plugin modules under plugins/:
  browser.py, system.py, spotify.py, vision.py, media.py
See plugins/__init__.py for the registry and dispatch contract.
"""

from backend.assistant.session_memory import session_memory
from backend.api import ui_server
from backend.voice.audio_engine import speak
from backend.utils.logger import logger
from backend.assistant import plugins


def handle_command(command):
    if not command:
        speak("I didn't catch that. Call me again.")
        return

    # Normalize log output
    logger.info(f"Received user command: '{command}'")

    # Update session memory command history
    session_memory.set("last_command", command)

    # 1. Classify intent via NLP classifier
    from backend.assistant.intent_classifier import classify_intent
    result = classify_intent(command)
    intent = result["intent"]
    entities = result["entities"]

    logger.info(f"Parsed intent: '{intent}' (confidence: {result['confidence']}) with entities: {entities}")

    # 2. Layer A — plugin intent handlers
    if plugins.dispatch_intent(intent, command, entities):
        return

    # 3. Layer B — plugin predicate fallbacks (folders, spotify, system, time/date/…)
    if plugins.dispatch_fallback(command):
        return

    # 4. Layer C — anything else → the centralized LLM router
    session_memory.set("current_task", "query_llm")
    ui_server.set_ui("thinking", message="Thinking...", command=command)
    from backend.assistant.llm_router import router, AGENT_TOOLS
    answer = router.ask_llm(command, tools=AGENT_TOOLS)
    if isinstance(answer, str):
        speak(answer)
        return
    # Agent mode: Gemini chose actions. Run them through the plugin layers only
    # (never back into the LLM, so no loops).
    for call in answer:
        for sub in call.get("args", {}).get("commands", []):
            sub = sub.lower().strip()
            logger.info(f"Agent command: '{sub}'")
            r = classify_intent(sub)
            if not (plugins.dispatch_intent(r["intent"], sub, r["entities"])
                    or plugins.dispatch_fallback(sub)):
                speak(f"I couldn't do: {sub}.")
