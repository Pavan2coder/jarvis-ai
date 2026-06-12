# Package initialization for backend.assistant
from .brain import verify_gemini, ask_gemini, gemini_ready
from .commands import handle_command
from .llm_router import router as llm_router
from .intent_classifier import classify_intent, classify_intent_json
