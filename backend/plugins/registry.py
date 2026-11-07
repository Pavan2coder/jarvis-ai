"""
PluginRegistry — the authoritative table of known plugins.

Holds one PluginRecord per plugin (instance + lifecycle state + last error),
and maintains an intent → plugin-name index with exclusive ownership. Registration
fails loud on a duplicate plugin name or a duplicate intent claim, matching the
existing dispatcher's "one owner per intent" rule.

The registry stores state; it does NOT drive lifecycle transitions or run hooks —
that is PluginManager's job. Thread-safe: main.py dispatches commands on a worker
thread while other code may query the registry.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional

from backend.plugins.base import Plugin, PluginError, PluginState

log = logging.getLogger("JARVIS.plugins.registry")


@dataclass
class PluginRecord:
    """A registered plugin plus its mutable lifecycle bookkeeping."""
    plugin: Plugin
    state: PluginState = PluginState.DISCOVERED
    error: Optional[str] = None

    @property
    def name(self) -> str:
        return self.plugin.metadata.name

    @property
    def category(self) -> str:
        return self.plugin.metadata.category


class PluginRegistry:
    """In-memory registry of plugins, keyed by unique metadata.name."""

    def __init__(self) -> None:
        self._records: Dict[str, PluginRecord] = {}
        self._intent_owner: Dict[str, str] = {}   # intent -> plugin name
        self._lock = threading.RLock()

    # ---- registration ---------------------------------------------------------

    def register(self, plugin: Plugin) -> PluginRecord:
        """
        Add a plugin. Returns its record (state DISCOVERED).

        Raises PluginError if the name is taken or any declared intent is already
        owned by another plugin.
        """
        meta = plugin.metadata
        with self._lock:
            if meta.name in self._records:
                raise PluginError(f"Duplicate plugin name {meta.name!r}")
            conflicts = [i for i in meta.intents if i in self._intent_owner]
            if conflicts:
                raise PluginError(
                    f"Plugin {meta.name!r} claims intent(s) {conflicts} already "
                    f"owned by {[self._intent_owner[i] for i in conflicts]}"
                )
            record = PluginRecord(plugin=plugin)
            self._records[meta.name] = record
            for intent in meta.intents:
                self._intent_owner[intent] = meta.name
            log.info("Registered plugin %r (category=%s, intents=%s)",
                     meta.name, meta.category, list(meta.intents))
            return record

    def unregister(self, name: str) -> bool:
        """Remove a plugin and release its intents. Returns True if it existed."""
        with self._lock:
            record = self._records.pop(name, None)
            if record is None:
                return False
            for intent in record.plugin.metadata.intents:
                if self._intent_owner.get(intent) == name:
                    del self._intent_owner[intent]
            log.info("Unregistered plugin %r", name)
            return True

    # ---- lookup ---------------------------------------------------------------

    def get(self, name: str) -> Optional[PluginRecord]:
        with self._lock:
            return self._records.get(name)

    def by_intent(self, intent: str) -> Optional[PluginRecord]:
        with self._lock:
            owner = self._intent_owner.get(intent)
            return self._records.get(owner) if owner else None

    def by_category(self, category: str) -> List[PluginRecord]:
        with self._lock:
            return [r for r in self._records.values() if r.category == category]

    def all(self) -> List[PluginRecord]:
        with self._lock:
            return list(self._records.values())

    def enabled(self) -> List[PluginRecord]:
        """Enabled plugins, ordered by ascending priority (dispatch order)."""
        with self._lock:
            active = [r for r in self._records.values()
                      if r.state == PluginState.ENABLED]
        return sorted(active, key=lambda r: r.plugin.metadata.priority)

    def names(self) -> List[str]:
        with self._lock:
            return list(self._records.keys())

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)
