"""
Plugin discovery + loading mechanism.

Scans a package for plugins and returns constructed (but not yet loaded) Plugin
instances. Discovery is intentionally decoupled from the registry and lifecycle:
it only finds and builds; PluginManager decides what to register/load/enable.

Convention
──────────
Each plugin lives in its OWN SUBPACKAGE of the scanned package, e.g.

    backend/plugins/browser/__init__.py
    backend/plugins/system/__init__.py

Framework modules (base.py, registry.py, discovery.py, manager.py) are plain
modules, not subpackages, so they are skipped automatically — only subpackages
are treated as plugin homes.

A subpackage is turned into plugin instances by, in priority order:
  1. a module-level ``register()`` factory returning a Plugin or list of Plugins
     (lets a plugin "register itself" with custom construction), else
  2. auto-instantiating every concrete Plugin subclass defined within it.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from types import ModuleType
from typing import List, Type

from backend.plugins.base import Plugin

log = logging.getLogger("JARVIS.plugins.discovery")


def discover(package: ModuleType) -> List[Plugin]:
    """
    Import every subpackage of ``package`` and return constructed Plugin
    instances. Import/instantiation errors are logged and skipped so one broken
    plugin never blocks the rest.
    """
    if not hasattr(package, "__path__"):
        raise TypeError(f"{package.__name__} is not a package (no __path__)")

    instances: List[Plugin] = []
    for info in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
        if not info.ispkg:
            continue  # framework modules, not plugin homes
        try:
            module = importlib.import_module(info.name)
        except Exception:
            log.exception("Failed to import plugin package %r", info.name)
            continue
        try:
            instances.extend(_instantiate(module))
        except Exception:
            log.exception("Failed to build plugins from %r", info.name)
    log.info("Discovery found %d plugin instance(s) in %s",
             len(instances), package.__name__)
    return instances


def _instantiate(module: ModuleType) -> List[Plugin]:
    """Build plugin instances from one plugin subpackage module."""
    factory = getattr(module, "register", None)
    if callable(factory):
        result = factory()
        instances = list(result) if isinstance(result, (list, tuple)) else [result]
        for obj in instances:
            if not isinstance(obj, Plugin):
                raise TypeError(
                    f"{module.__name__}.register() returned {type(obj).__name__}, "
                    f"expected Plugin"
                )
        return instances

    return [cls() for cls in _plugin_classes(module)]


def _plugin_classes(module: ModuleType) -> List[Type[Plugin]]:
    """Concrete Plugin subclasses defined within ``module`` (or its submodules)."""
    prefix = module.__name__ + "."
    found: List[Type[Plugin]] = []
    seen = set()
    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if obj is Plugin or not issubclass(obj, Plugin):
            continue
        if inspect.isabstract(obj):
            continue
        # Only classes that belong to this subpackage — not ones merely imported.
        if not (obj.__module__ == module.__name__ or obj.__module__.startswith(prefix)):
            continue
        if obj in seen:
            continue
        seen.add(obj)
        found.append(obj)
    return found
