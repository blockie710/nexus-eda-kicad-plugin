# SPDX-License-Identifier: Apache-2.0
"""Nexus-EDA KiCad Plugin — AI-assisted PCB design automation.

The :mod:`nexus_eda.plugin` entry point depends on KiCad's ``pcbnew`` and
``wx`` modules, which are only importable inside the KiCad Python host.
To keep this package importable from a regular Python environment (unit
tests, CI, headless scripts), the plugin import is deferred and guarded so
that the LLM, agents, and other pure-Python helpers remain usable.
"""

__version__ = "0.1.0"
__all__ = ["register"]

try:
    from .plugin import register
except ImportError:  # pcbnew / wx not available outside KiCad host
    register = None  # type: ignore[assignment]
