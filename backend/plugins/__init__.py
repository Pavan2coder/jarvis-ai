"""
Generic plugin framework for J.A.R.V.I.S — the foundation for a plugin-based,
desktop-app-style architecture.

This package is the FRAMEWORK ONLY. No commands are migrated onto it yet, and it
is not wired into the live dispatcher. The existing command system
(backend/assistant/commands.py and its INTENTS/FALLBACKS modules under
backend/assistant/plugins/) continues to run unchanged.

Public surface
──────────────
  Plugin, PluginMetadata, CommandSpec   — the interface a plugin implements
  PluginState, PluginError              — lifecycle states + error type
  PluginRegistry, PluginRecord          — the registry
  PluginManager                         — discovery + lifecycle + dispatch
  get_manager()                         — lazily-created shared manager singleton

Future capability plugins live in their own subpackages here, e.g.
  backend/plugins/browser/   backend/plugins/system/   backend/plugins/vision/
Discovery scans subpackages only, so these framework modules are never mistaken
for plugins.

Nothing is discovered or loaded at import time — call get_manager().load_all()
explicitly (e.g. from backend/main.py) once migration begins.
"""

from __future__ import annotations

from typing import Optional

from backend.plugins.base import (
    CommandSpec,
    Plugin,
    PluginError,
    PluginMetadata,
    PluginState,
)
from backend.plugins.discovery import discover
from backend.plugins.manager import PluginManager
from backend.plugins.registry import PluginRecord, PluginRegistry

__all__ = [
    "Plugin",
    "PluginMetadata",
    "CommandSpec",
    "PluginState",
    "PluginError",
    "PluginRegistry",
    "PluginRecord",
    "PluginManager",
    "discover",
    "get_manager",
]

# Lazily-created shared manager. Not populated until load_all() is called, so
# importing this package has no side effects.
_MANAGER: Optional[PluginManager] = None


def get_manager() -> PluginManager:
    """Return the process-wide PluginManager, creating it on first use."""
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = PluginManager()
    return _MANAGER
