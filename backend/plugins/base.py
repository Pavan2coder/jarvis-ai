"""
Plugin interface — the contract every capability plugin implements.

This is the FOUNDATION only. No existing commands are migrated onto it yet; the
live command dispatcher (backend/assistant/commands.py + its INTENTS/FALLBACKS
modules) is untouched and keeps working exactly as before.

A plugin:
  • exposes metadata            → the ``metadata`` property (PluginMetadata)
  • exposes supported commands  → ``commands()`` (list of CommandSpec)
  • registers itself            → discovered as a concrete Plugin subclass, or
                                   returned from a module-level ``register()``
                                   factory (see discovery.py)
  • executes independently      → ``can_handle()`` + ``execute()`` decide and run,
                                   with no knowledge of any other plugin

Lifecycle (driven by PluginManager):
    DISCOVERED → LOADED → ENABLED ⇄ DISABLED → UNLOADED   (ERROR on failure)
Each transition invokes the matching hook (on_load/on_enable/on_disable/
on_unload); all hooks default to no-ops so a minimal plugin only implements
``metadata`` and ``execute``.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Mapping, Optional, Sequence, Tuple


class PluginError(Exception):
    """Raised for registration conflicts and lifecycle violations."""


class PluginState(Enum):
    """Where a plugin sits in its lifecycle. See module docstring for the flow."""
    DISCOVERED = auto()   # found + registered, on_load not yet run
    LOADED     = auto()   # on_load succeeded, inactive
    ENABLED    = auto()   # active; eligible for dispatch
    DISABLED   = auto()   # loaded but temporarily inactive
    UNLOADED   = auto()   # on_unload run, removed from the registry
    ERROR      = auto()   # a lifecycle hook raised; see PluginRecord.error


@dataclass(frozen=True)
class CommandSpec:
    """
    One user-facing command a plugin supports. Declarative only — used for
    discovery/help/telemetry, never executed directly (execute() does the work).
    """
    name: str
    description: str = ""
    intent: Optional[str] = None
    examples: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PluginMetadata:
    """
    Immutable identity + capability declaration for a plugin.

    name:               unique id (registry key); also the dispatch label.
    version:            semantic version string.
    category:           grouping — browser / system / media / vision / automation…
    description:        one-line human summary.
    author:             optional attribution.
    intents:            NLP intents this plugin claims. Ownership is exclusive —
                        the registry rejects a second plugin claiming the same
                        intent (mirrors the current INTENTS "fail loud" rule).
    priority:           lower runs earlier in the can_handle() dispatch scan.
    enabled_by_default: whether load_all() enables it immediately after load.
    """
    name: str
    version: str = "0.1.0"
    category: str = "general"
    description: str = ""
    author: str = ""
    intents: Tuple[str, ...] = ()
    priority: int = 100
    enabled_by_default: bool = True


class Plugin(abc.ABC):
    """
    Base class for all plugins. Subclass, declare ``metadata``, implement
    ``execute``, and (optionally) override lifecycle hooks / ``can_handle``.

    Instances must be cheap to construct: do real setup in ``on_load``/
    ``on_enable``, never in ``__init__`` — construction happens during discovery,
    before the manager has decided whether to load the plugin.
    """

    # ---- required declaration -------------------------------------------------

    @property
    @abc.abstractmethod
    def metadata(self) -> PluginMetadata:
        """Immutable identity/capabilities. Must be constant for the instance."""
        raise NotImplementedError

    # ---- capability introspection --------------------------------------------

    def commands(self) -> Sequence[CommandSpec]:
        """Supported commands, for help/telemetry. Defaults to none."""
        return ()

    # ---- lifecycle hooks (override as needed; defaults are no-ops) ------------

    def on_load(self) -> None:
        """Acquire resources / warm caches. Called once, before first enable."""

    def on_enable(self) -> None:
        """Become active. Called on every DISABLED/LOADED → ENABLED transition."""

    def on_disable(self) -> None:
        """Go dormant but stay loaded. Called on ENABLED → DISABLED."""

    def on_unload(self) -> None:
        """Release resources. Called once, on removal from the registry."""

    # ---- routing + execution --------------------------------------------------

    def can_handle(
        self,
        command: str,
        intent: Optional[str] = None,
        entities: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        """
        Whether this plugin wants the command. Default: claim it if the classified
        intent is one we declared. Override for keyword/predicate style matching.
        """
        return intent is not None and intent in self.metadata.intents

    @abc.abstractmethod
    def execute(
        self,
        command: str,
        intent: Optional[str] = None,
        entities: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        """
        Handle the command independently. Return True if handled, False to let
        the dispatcher fall through to the next candidate.
        """
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        m = self.metadata
        return f"<{type(self).__name__} {m.name} v{m.version} [{m.category}]>"
