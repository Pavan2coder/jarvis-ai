"""Command plugin registry.

Each plugin module exposes two module-level attributes:

  INTENTS   : dict[str, Callable[[str, dict], None]]
      NLP-intent handlers (Layer A). Keyed by the intent string emitted by
      backend.assistant.intent_classifier. Exactly one plugin may own an intent.

  FALLBACKS : list[tuple[int, Callable[[str], bool]]]
      Ordered predicate handlers (Layer B). Each returns True if it handled the
      command. The integer is a global ordering key — the merged chain runs in
      ascending order, preserving the original single-file dispatch sequence
      (folders=10, spotify=20, system=30, time=40, date=50, weather=60,
      joke=70, ip=80, introduce=90).

commands.handle_command classifies the intent, then calls dispatch_intent();
if unmatched, dispatch_fallback(); if still unmatched, the LLM router.
"""

from backend.assistant.plugins import browser, system, spotify, vision, media

_PLUGINS = [browser, system, spotify, vision, media]

# Merge intent maps — fail loud if two plugins claim the same intent.
_INTENT_MAP = {}
for _plugin in _PLUGINS:
    for _intent, _handler in getattr(_plugin, "INTENTS", {}).items():
        if _intent in _INTENT_MAP:
            raise RuntimeError(
                f"Duplicate intent handler for '{_intent}' "
                f"(already owned before {_plugin.__name__})"
            )
        _INTENT_MAP[_intent] = _handler

# Merge + globally order the predicate fallback chain.
_FALLBACKS = sorted(
    (fb for _plugin in _PLUGINS for fb in getattr(_plugin, "FALLBACKS", [])),
    key=lambda entry: entry[0],
)


def dispatch_intent(intent, command, entities) -> bool:
    """Run the handler that owns `intent`. Returns True if one existed."""
    handler = _INTENT_MAP.get(intent)
    if handler is None:
        return False
    handler(command, entities)
    return True


def dispatch_fallback(command) -> bool:
    """Run the ordered predicate chain. Returns True as soon as one handles it."""
    for _order, handler in _FALLBACKS:
        if handler(command):
            return True
    return False
