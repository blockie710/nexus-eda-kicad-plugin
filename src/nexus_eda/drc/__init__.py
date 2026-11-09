# SPDX-License-Identifier: Apache-2.0
"""DRC (Design Rule Check) module for Nexus-EDA.

Public API
----------
- :class:`Severity`           — enum: error / warning / info / none
- :class:`ViolationType`      — extensible StrEnum of known DRC rule types
- :class:`BoardCoordinate`    — immutable board position (nm canonical)
- :class:`DRCViolation`       — frozen dataclass for a single violation
- :class:`ViolationCollection` — ordered list with filter / summary helpers
- :class:`DRCReport`          — top-level report: metadata + violations
- :func:`parse_pcbnew_drc`    — pcbnew adapter (requires KiCad runtime)
- :func:`parse_violation_object` / :func:`violation_to_dataclass` — single-item adapter

The data model (:mod:`nexus_eda.drc.data_model`) is pure Python and
importable outside KiCad.  The pcbnew adapter (:mod:`nexus_eda.drc.parser`)
is imported lazily and raises :class:`DRCParseError` when ``pcbnew`` is
unavailable.
"""

from .data_model import (
    DRCReport,
    DRCViolation,
    BoardCoordinate,
    Severity,
    ViolationCollection,
    ViolationType,
    VIOLATION_CATEGORY_LABELS,
    SEVERITY_LABELS,
)

__all__ = [
    "DRCReport",
    "DRCViolation",
    "BoardCoordinate",
    "Severity",
    "ViolationCollection",
    "ViolationType",
    "VIOLATION_CATEGORY_LABELS",
    "SEVERITY_LABELS",
    # Parser re-exports (importable but pcbnew-dependent at call time).
    "parse_pcbnew_drc",
    "parse_violation_object",
    "violation_to_dataclass",
    "DRCParseError",
    "PCBNEW_AVAILABLE",
]

# --------------------------------------------------------------------------- #
# Lazy import of the pcbnew adapter — only fails if pcbnew is unavailable.
# --------------------------------------------------------------------------- #
from .parser import (  # noqa: E402 — deferred after data_model exports
    PCBNEW_AVAILABLE,
    DRCParseError,
    parse_pcbnew_drc,
    parse_violation_object,
    violation_to_dataclass,
)
