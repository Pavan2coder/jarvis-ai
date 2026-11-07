"""
PluginManager — orchestrates discovery, registration, lifecycle, and dispatch.

This is the single object the rest of the app talks to. It is deliberately NOT
wired into backend/assistant/commands.py yet — the existing dispatcher keeps
running unchanged. When migration begins, handle_command can consult
``MANAGER.dispatch(...)`` before falling through to today's INTENTS/FALLBACKS.

Lifecycle transitions (and the hooks they fire) all live here; the registry only
stores state. Every hook call is guarded so a misbehaving plugin lands in the
ERROR state instead of taking down the manager.
"""

from __future__ import annotations

import importlib
import logging
import threading
from types import ModuleType
from typing import Any, List, Mapping, Optional

from backend.plugins.base import Plugin, PluginError, PluginState
from backend.plugins.discovery import discover
from backend.plugins.registry import PluginRecord, PluginRegistry

log = logging.getLogger("JARVIS.plugins.manager")

#: Package scanned for plugin subpackages when none is supplied.
DEFAULT_PLUGIN_PACKAGE = "backend.plugins"


class PluginManager:
    """Owns a PluginRegistry and drives every plugin through its lifecycle."""

    def __init__(
        self,
        package: Optional[ModuleType] = None,
        registry: Optional[PluginRegistry] = None,
    ) -> None:
        self._package = package
        self._registry = registry or PluginRegistry()
        self._lock = threading.RLock()

    @property
    def registry(self) -> PluginRegistry:
        return self._registry

    # ---- discovery + bulk loading --------------------------------------------

    def discover(self) -> List[Plugin]:
        """Find + construct plugin instances from the configured package."""
        pkg = self._package or importlib.import_module(DEFAULT_PLUGIN_PACKAGE)
        return discover(pkg)

    def load_all(self) -> None:
        """
        Full boot sequence: discover → register → on_load → enable (when the
        plugin's metadata.enabled_by_default is set). Conflicts and hook failures
        are logged and skipped; they never abort the batch.
        """
        for plugin in self.discover():
            try:
                record = self._registry.register(plugin)
            except PluginError as exc:
                log.error("Skipping plugin: %s", exc)
                continue
            self._load(record)
            if (record.state == PluginState.LOADED
                    and plugin.metadata.enabled_by_default):
                self.enable(record.name)

    def unload_all(self) -> None:
        """Disable + unload every registered plugin (reverse of load_all)."""
        for name in self._registry.names():
            self.unload(name)

    # ---- manual registration (for tests / dynamic plugins) -------------------

    def register(self, plugin: Plugin, *, load: bool = True, enable: bool = False) -> PluginRecord:
        """Register a plugin instance directly, optionally loading/enabling it."""
        record = self._registry.register(plugin)
        if load:
            self._load(record)
        if enable and record.state == PluginState.LOADED:
            self.enable(record.name)
        return record

    # ---- lifecycle transitions -----------------------------------------------

    def _load(self, record: PluginRecord) -> bool:
        if record.state not in (PluginState.DISCOVERED,):
            return record.state == PluginState.LOADED
        if self._fire(record, "on_load"):
            record.state = PluginState.LOADED
            log.info("Loaded plugin %r", record.name)
            return True
        return False

    def enable(self, name: str) -> bool:
        with self._lock:
            record = self._registry.get(name)
            if record is None:
                log.warning("enable(%r): not registered", name)
                return False
            if record.state == PluginState.ENABLED:
                return True
            if record.state not in (PluginState.LOADED, PluginState.DISABLED):
                log.warning("enable(%r): illegal from %s", name, record.state.name)
                return False
            if self._fire(record, "on_enable"):
                record.state = PluginState.ENABLED
                log.info("Enabled plugin %r", name)
                return True
            return False

    def disable(self, name: str) -> bool:
        with self._lock:
            record = self._registry.get(name)
            if record is None:
                return False
            if record.state != PluginState.ENABLED:
                return record.state == PluginState.DISABLED
            if self._fire(record, "on_disable"):
                record.state = PluginState.DISABLED
                log.info("Disabled plugin %r", name)
                return True
            return False

    def unload(self, name: str) -> bool:
        with self._lock:
            record = self._registry.get(name)
            if record is None:
                return False
            if record.state == PluginState.ENABLED:
                self.disable(name)
            self._fire(record, "on_unload")  # best-effort; unregister regardless
            record.state = PluginState.UNLOADED
            self._registry.unregister(name)
            log.info("Unloaded plugin %r", name)
            return True

    # ---- dispatch (forward-looking; not yet called by commands.py) -----------

    def dispatch(
        self,
        command: str,
        intent: Optional[str] = None,
        entities: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        """
        Route a command to the first enabled plugin that handles it.

        Order: the exclusive owner of ``intent`` first (if any), then all enabled
        plugins by ascending priority. Returns True once a plugin's execute()
        returns True. A raising plugin is logged and skipped, never propagated.
        """
        tried = set()

        owner = self._registry.by_intent(intent) if intent else None
        if owner is not None and owner.state == PluginState.ENABLED:
            tried.add(owner.name)
            if self._try(owner, command, intent, entities):
                return True

        for record in self._registry.enabled():
            if record.name in tried:
                continue
            if self._try(record, command, intent, entities):
                return True
        return False

    def _try(self, record, command, intent, entities) -> bool:
        plugin = record.plugin
        try:
            if not plugin.can_handle(command, intent, entities):
                return False
            handled = plugin.execute(command, intent, entities)
            if handled:
                log.info("Command handled by plugin %r", record.name)
            return bool(handled)
        except Exception:
            log.exception("Plugin %r raised during dispatch", record.name)
            return False

    # ---- internals ------------------------------------------------------------

    def _fire(self, record: PluginRecord, hook: str) -> bool:
        """Invoke a lifecycle hook; on failure mark ERROR and return False."""
        try:
            getattr(record.plugin, hook)()
            return True
        except Exception as exc:
            record.state = PluginState.ERROR
            record.error = f"{hook}: {exc}"
            log.exception("Plugin %r failed in %s", record.name, hook)
            return False
