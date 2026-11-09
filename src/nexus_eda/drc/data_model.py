# SPDX-License-Identifier: Apache-2.0
"""Data model for DRC (Design Rule Check) violations extracted from pcbnew.

This module defines a clear, extensible internal representation of DRC
violations that decouples downstream consumers (natural-language summary
generation, UI rendering, rule categorization) from the pcbnew Python API.

Design principles
-----------------
- **Pure Python**: No ``pcbnew`` or ``wx`` imports here.  The module is
  importable in any Python environment (CI, headless scripts, unit tests).
  The pcbnew-adapter lives in :mod:`nexus_eda.drc.parser`.
- **Immutable value objects**: ``DRCViolation`` and ``BoardCoordinate`` are
  ``@dataclass(frozen=True)`` so they can be safely used as dict keys /
  set members and shared across threads without defensive copies.
- **JSON-serializable**: Every public type provides ``to_dict`` /
  ``from_dict`` (or ``from_dict`` classmethod) so the model round-trips
  through JSON for logging, IPC, and persistence.
- **Extensible rule types**: ``ViolationType`` is a ``StrEnum`` with a class
  level registry.  New rule types can be added either as enum members (the
  preferred path for first-class rules) or registered at runtime via
  :meth:`ViolationType.register`.  Unknown or third-party rule ids that arrive
  from pcbnew are mapped to :attr:`ViolationType.OTHER` with the raw id
  preserved in ``raw_rule``.

Canonical units
---------------
Board coordinates are stored internally as **nanometers** (integers), which is
KiCad's native internal unit.  This avoids floating-point drift on the board
grid and gives nanosecond-precision positioning.  Convenience accessors
:attr:`BoardCoordinate.mm_x` / :attr:`BoardCoordinate.mm_y` return floats in
millimetres, and :meth:`to_mm_tuple` / :meth:`to_inch_tuple` provide common
conversions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, ClassVar, Dict, List, Optional, Tuple

__all__ = [
    "Severity",
    "ViolationType",
    "BoardCoordinate",
    "DRCViolation",
    "ViolationCollection",
    "DRCReport",
    "VIOLATION_CATEGORY_LABELS",
    "SEVERITY_LABELS",
]


# --------------------------------------------------------------------------- #
# Conversion constants (KiCad uses 10⁻⁶ mm = 1 nm internally)
# --------------------------------------------------------------------------- #
_NM_PER_MM: int = 1_000_000
_NM_PER_INCH: float = 25.4 * _NM_PER_MM  # 25_400_000.0


# --------------------------------------------------------------------------- #
# Severity
# --------------------------------------------------------------------------- #
class Severity(StrEnum):
    """DRC violation severity levels.

    Members
    -------
    ERROR
        A hard design-rule violation that prevents manufacturing or
        functioning.  The board must not be fabricated or assembled with
        this violation outstanding.
    WARNING
        A cautionary issue that may not break fabrication but should be
        reviewed (e.g. tight clearance, high fanout).
    INFO
        Advisory information — not a violation per se, but useful context
        (e.g. a component with unusually many connections).
    NONE
        A diagnostic item with no severity (used by some rule categories).
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    NONE = "none"


SEVERITY_LABELS: Dict[str, str] = {
    Severity.ERROR: "Error",
    Severity.WARNING: "Warning",
    Severity.INFO: "Info",
    Severity.NONE: "Info",
}


# --------------------------------------------------------------------------- #
# ViolationType — extensible registry
# --------------------------------------------------------------------------- #
class ViolationType(StrEnum):
    """Known pcbnew DRC violation types.

    The enum values match pcbnew's ``DRCViolation`` classification strings
    as closely as the upstream API exposes them.  When pcbnew returns a rule
    id that does not map to any member, :meth:`from_pcbnew` falls back to
    :attr:`OTHER` and stores the raw id in the violation's ``raw_rule``
    field so no information is lost.

    Extensibility
    -------------
    New rule types discovered in the wild can be registered at runtime:

    >>> ViolationType.register("my_custom_rule", "My Custom Rule", "Custom")
    >>> vt = ViolationType("my_custom_rule")
    >>> vt.display_name
    'My Custom Rule'
    """

    # --- Electrical ---------------------------------------------------------
    CLEARANCE = "clearance"
    TRACK_WIDTH = "track_width"
    VIA_DRILL = "via_drill"
    VIA_COVERAGE = "via_coverage"
    UNROUTED = "unrouted"
    SHORT = "short"
    OPEN_CONNECTED = "open_connected"
    OVERLAP = "overlap"
    DUPLICATE = "duplicate"
    MISSING_PIN = "missing_pin"
    EXTRA_PIN = "extra_pin"

    # --- Component ----------------------------------------------------------
    COMPONENT_PLACEMENT = "component_placement"
    COMPONENT_OVERLAP = "component_overlap"
    COMPONENT_CLEARANCE = "component_clearance"
    OUT_OF_BOARD = "out_of_board"
    NOT_IN_SCHEMATIC = "not_in_schematic"

    # --- Miscellaneous ------------------------------------------------------
    TEXT_OVERLAP = "text_overlap"
    ZONE_FILL = "zone_fill"
    TRACK_ANGLE = "track_angle"
    BOARD_EDGE = "board_edge"

    # --- Generic fallback ---------------------------------------------------
    OTHER = "other"

    # Class-level registry for display metadata: maps enum value -> (display, category)
    _registry: ClassVar[Dict[str, Tuple[str, str]]] = {
        CLEARANCE: ("Clearance", "Electrical"),
        TRACK_WIDTH: ("Track Width", "Electrical"),
        VIA_DRILL: ("Via Drill", "Electrical"),
        VIA_COVERAGE: ("Via Coverage", "Electrical"),
        UNROUTED: ("Unrouted Net", "Electrical"),
        SHORT: ("Short Circuit", "Electrical"),
        OPEN_CONNECTED: ("Open / Connected", "Electrical"),
        OVERLAP: ("Overlap", "Electrical"),
        DUPLICATE: ("Duplicate", "Electrical"),
        MISSING_PIN: ("Missing Pin", "Electrical"),
        EXTRA_PIN: ("Extra Pin", "Electrical"),
        COMPONENT_PLACEMENT: ("Component Placement", "Component"),
        COMPONENT_OVERLAP: ("Component Overlap", "Component"),
        COMPONENT_CLEARANCE: ("Component Clearance", "Component"),
        OUT_OF_BOARD: ("Out of Board", "Component"),
        NOT_IN_SCHEMATIC: ("Not in Schematic", "Component"),
        TEXT_OVERLAP: ("Text Overlap", "Miscellaneous"),
        ZONE_FILL: ("Zone Fill", "Miscellaneous"),
        TRACK_ANGLE: ("Track Angle", "Miscellaneous"),
        BOARD_EDGE: ("Board Edge", "Miscellaneous"),
        OTHER: ("Other", "Miscellaneous"),
    }

    @classmethod
    def register(
        cls,
        value: str,
        display_name: str,
        category: str = "Custom",
    ) -> None:
        """Dynamically register a new violation type.

        After registration, ``ViolationType(value)`` will succeed for the
        given *value* and the display/category metadata becomes available
        via :meth:`display_name` and :meth:`category`.

        Parameters
        ----------
        value:
            The string key (must be lowercase, no spaces).
        display_name:
            Human-readable label shown in UIs and summaries.
        category:
            Broad grouping for categorization (e.g. ``"Electrical"``).
        """
        cls._registry[value] = (display_name, category)
        # We cannot add to the enum dynamically without metaclasses, but we
        # can ensure the _registry is consulted in display_name / category.

    @classmethod
    def from_pcbnew(cls, rule_id: Optional[str]) -> "ViolationType":
        """Map a pcbnew rule id to a :class:`ViolationType`.

        Unknown rule ids are mapped to :attr:`OTHER`; the *raw* id is
        preserved by the caller in :attr:`DRCViolation.raw_rule`.
        """
        if rule_id is None:
            return cls.OTHER
        # pcbnew uses CamelCase / hyphenated ids; normalise to lowercase
        # for the StrEnum lookup.
        normalised = rule_id.lower().replace("-", "_").replace(" ", "_")
        try:
            return cls(normalised)
        except ValueError:
            # Check if it was registered dynamically.
            if normalised in cls._registry:
                # Construct a pseudo-member via the OTHER fallback; the
                # display name comes from the registry.
                return cls.OTHER
            return cls.OTHER

    @property
    def display_name(self) -> str:
        """Human-readable label for this violation type."""
        entry = self._registry.get(self.value)
        if entry is not None:
            return entry[0]
        # For dynamically registered types whose value isn't a real member
        # but was stored in the registry, look up by the raw value.
        return self._registry.get(self.value, (self.value.replace("_", " ").title(), "Miscellaneous"))[0]

    @property
    def category(self) -> str:
        """Broad category grouping (Electrical, Component, Miscellaneous, …)."""
        entry = self._registry.get(self.value)
        if entry is not None:
            return entry[1]
        return "Miscellaneous"


# Convenience mapping for the NL summary generator.
VIOLATION_CATEGORY_LABELS: Dict[str, str] = {
    "Electrical": "Electrical rule",
    "Component": "Component placement",
    "Miscellaneous": "Layout / miscellaneous",
    "Custom": "Custom rule",
}


# --------------------------------------------------------------------------- #
# BoardCoordinate
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BoardCoordinate:
    """A point on the PCB board with optional layer information.

    Coordinates are stored as nanometres (integers — KiCad's internal unit).
    Use the ``from_mm`` / ``from_inch`` classmethods for construction from
    common units, and the ``.mm_x`` / ``.mm_y`` properties for display.

    Attributes
    ----------
    x_nm:
        X position in nanometres (1 mm = 1 000 000 nm).
    y_nm:
        Y position in nanometres.
    layer:
        PCB layer name (e.g. ``"F.Cu"``, ``"B.SilkS"``, ``"Edge.Cuts"``).
        ``None`` when the violation is not layer-specific (e.g. unrouted net).
    """

    x_nm: int
    y_nm: int
    layer: Optional[str] = None

    # -- construction helpers ------------------------------------------------ #
    @classmethod
    def from_nm(cls, x_nm: int, y_nm: int, layer: Optional[str] = None) -> "BoardCoordinate":
        """Construct from nanometre integers (the canonical KiCad unit)."""
        return cls(x_nm=x_nm, y_nm=y_nm, layer=layer)

    @classmethod
    def from_mm(cls, x_mm: float, y_mm: float, layer: Optional[str] = None) -> "BoardCoordinate":
        """Construct from millimetre floats."""
        return cls(
            x_nm=round(x_mm * _NM_PER_MM),
            y_nm=round(y_mm * _NM_PER_MM),
            layer=layer,
        )

    @classmethod
    def from_inch(cls, x_in: float, y_in: float, layer: Optional[str] = None) -> "BoardCoordinate":
        """Construct from inch floats."""
        return cls(
            x_nm=round(x_in * _NM_PER_INCH),
            y_nm=round(y_in * _NM_PER_INCH),
            layer=layer,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BoardCoordinate":
        """Deserialize from a plain dict (inverse of :meth:`to_dict`)."""
        return cls(
            x_nm=int(data["x_nm"]),
            y_nm=int(data["y_nm"]),
            layer=data.get("layer"),
        )

    # -- display properties -------------------------------------------------- #
    @property
    def mm_x(self) -> float:
        """X position in millimetres."""
        return self.x_nm / _NM_PER_MM

    @property
    def mm_y(self) -> float:
        """Y position in millimetres."""
        return self.y_nm / _NM_PER_MM

    @property
    def inch_x(self) -> float:
        """X position in inches."""
        return self.x_nm / _NM_PER_INCH

    @property
    def inch_y(self) -> float:
        """Y position in inches."""
        return self.y_nm / _NM_PER_INCH

    def to_mm_tuple(self) -> Tuple[float, float]:
        """Return ``(x_mm, y_nm)`` as floats."""
        return (self.mm_x, self.mm_y)

    def to_inch_tuple(self) -> Tuple[float, float]:
        """Return ``(x_inch, y_inch)`` as floats."""
        return (self.inch_x, self.inch_y)

    # -- serialization ------------------------------------------------------- #
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "x_nm": self.x_nm,
            "y_nm": self.y_nm,
            "layer": self.layer,
        }

    def __str__(self) -> str:
        return f"({self.mm_x:.3f} mm, {self.mm_y:.3f} mm{layersuffix(self.layer)})"


def layersuffix(layer: Optional[str]) -> str:
    """Return `` on <layer>`` or empty string."""
    return f", layer={layer}" if layer else ""


# Re-bind __str__ since it references the helper above.
BoardCoordinate.__str__ = lambda self: (  # type: ignore[method-assign]
    f"({self.mm_x:.3f} mm, {self.mm_y:.3f} mm"
    + layersuffix(self.layer)
    + ")"
)


# --------------------------------------------------------------------------- #
# DRCViolation
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DRCViolation:
    """A single DRC violation extracted from pcbnew.

    This is the canonical internal representation consumed by all downstream
    modules — the natural-language summary generator (:mod:`nexus_eda.drc`)
    and any future rule categorization, filtering, or UI rendering logic.

    Attributes
    ----------
    violation_type:
        Categorised :class:`ViolationType` enum value.
    raw_rule:
        The original pcbnew rule id / description string (preserved for
        traceability and for dynamically-registered rules).  Always set.
    description:
        Human-readable description (from pcbnew or generated).
    severity:
        :class:`Severity` enum value.
    coordinate:
        :class:`BoardCoordinate` for the primary location of the violation.
        May be ``None`` when pcbnew does not report a position.
    bounding_box:
        Optional pair of ``(BoardCoordinate, BoardCoordinate)`` defining the
        axis-aligned bounding box of the violation area.
    net:
        Name of the net involved, if applicable.
    component:
        Reference designator of the component involved, if applicable.
    layer:
        PCB layer where the violation was detected (separate from the
        coordinate's layer for convenience).
    module:
        Component ``(ref, side)`` tuple, if reported by pcbnew.
    details:
        Free-form additional details from pcbnew (e.g. clearance values,
        trace widths involved).
    source:
        Identifier of the rule source / checker that produced the violation
        (e.g. ``"pcbnew_drc"``, ``"netlist_checker"``).  Defaults to
        ``"pcbnew_drc"``.
    """

    violation_type: ViolationType
    raw_rule: str
    description: str
    severity: Severity = Severity.WARNING
    coordinate: Optional[BoardCoordinate] = None
    bounding_box: Optional[Tuple[BoardCoordinate, BoardCoordinate]] = None
    net: Optional[str] = None
    component: Optional[str] = None
    layer: Optional[str] = None
    module: Optional[Tuple[str, str]] = None
    details: Optional[str] = None
    source: str = "pcbnew_drc"

    # -- serialization ------------------------------------------------------- #
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "violation_type": self.violation_type.value,
            "raw_rule": self.raw_rule,
            "description": self.description,
            "severity": self.severity.value,
            "coordinate": self.coordinate.to_dict() if self.coordinate else None,
            "bounding_box": (
                [self.bounding_box[0].to_dict(), self.bounding_box[1].to_dict()]
                if self.bounding_box
                else None
            ),
            "net": self.net,
            "component": self.component,
            "layer": self.layer,
            "module": list(self.module) if self.module else None,
            "details": self.details,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DRCViolation":
        """Deserialize from a dict (inverse of :meth:`to_dict`).

        Handles the case where ``violation_type`` is a dynamically-registered
        or unknown value by mapping to :attr:`ViolationType.OTHER`.
        """
        vtype_val = data.get("violation_type", ViolationType.OTHER.value)
        try:
            vtype = ViolationType(vtype_val)
        except ValueError:
            vtype = ViolationType.OTHER

        severity_val = data.get("severity", Severity.WARNING.value)
        try:
            severity = Severity(severity_val)
        except ValueError:
            severity = Severity.WARNING

        coord_data = data.get("coordinate")
        coordinate = BoardCoordinate.from_dict(coord_data) if coord_data else None

        bb_data = data.get("bounding_box")
        bounding_box: Optional[Tuple[BoardCoordinate, BoardCoordinate]] = None
        if bb_data and len(bb_data) == 2:
            bounding_box = (
                BoardCoordinate.from_dict(bb_data[0]),
                BoardCoordinate.from_dict(bb_data[1]),
            )

        module = data.get("module")
        if module is not None:
            module = tuple(module)

        return cls(
            violation_type=vtype,
            raw_rule=data["raw_rule"],
            description=data["description"],
            severity=severity,
            coordinate=coordinate,
            bounding_box=bounding_box,
            net=data.get("net"),
            component=data.get("component"),
            layer=data.get("layer"),
            module=module,
            details=data.get("details"),
            source=data.get("source", "pcbnew_drc"),
        )

    # -- convenience --------------------------------------------------------- #
    @property
    def display_type(self) -> str:
        """Human-readable violation type label."""
        return self.violation_type.display_name

    @property
    def category(self) -> str:
        """Broad category (Electrical, Component, …)."""
        return self.violation_type.category

    def location_str(self) -> str:
        """Best-effort single-line location description for summaries."""
        parts: List[str] = []
        if self.coordinate is not None:
            parts.append(f"at {self.coordinate}")
        if self.layer:
            parts.append(f"on layer {self.layer}")
        if self.net:
            parts.append(f"net '{self.net}'")
        if self.component:
            parts.append(f"near {self.component}")
        return " ".join(parts) if parts else "(location not specified)"


# --------------------------------------------------------------------------- #
# ViolationCollection
# --------------------------------------------------------------------------- #
@dataclass
class ViolationCollection:
    """An ordered collection of :class:`DRCViolation` instances with helpers.

    Provides filtering, grouping, severity counting, and JSON
    serialization.  Downstream consumers (e.g. the NL summary generator)
    typically receive a ``ViolationCollection`` rather than a bare list.
    """

    violations: List[DRCViolation] = field(default_factory=list)

    # -- queries ------------------------------------------------------------- #
    def by_severity(self, severity: Severity | str) -> List[DRCViolation]:
        """Return violations matching *severity*."""
        sev = severity if isinstance(severity, Severity) else Severity(severity)
        return [v for v in self.violations if v.severity == sev]

    def by_type(self, vtype: ViolationType | str) -> List[DRCViolation]:
        """Return violations matching *vtype*."""
        vt = vtype if isinstance(vtype, ViolationType) else ViolationType(vtype)
        return [v for v in self.violations if v.violation_type == vt]

    def by_net(self, net: str) -> List[DRCViolation]:
        """Return violations associated with a specific net."""
        return [v for v in self.violations if v.net == net]

    def by_component(self, comp: str) -> List[DRCViolation]:
        """Return violations associated with a specific component reference."""
        return [v for v in self.violations if v.component == comp]

    def by_category(self, category: str) -> List[DRCViolation]:
        """Return violations in a given broad category."""
        return [v for v in self.violations if v.category == category]

    @property
    def total(self) -> int:
        """Total number of violations."""
        return len(self.violations)

    @property
    def error_count(self) -> int:
        """Number of ERROR-severity violations."""
        return len(self.by_severity(Severity.ERROR))

    @property
    def warning_count(self) -> int:
        """Number of WARNING-severity violations."""
        return len(self.by_severity(Severity.WARNING))

    @property
    def info_count(self) -> int:
        """Number of INFO-severity violations."""
        return len(self.by_severity(Severity.INFO))

    def severity_summary(self) -> Dict[str, int]:
        """Return a ``{severity: count}`` summary."""
        return {
            Severity.ERROR.value: self.error_count,
            Severity.WARNING.value: self.warning_count,
            Severity.INFO.value: self.info_count,
        }

    def type_summary(self) -> Dict[str, int]:
        """Return a ``{violation_type: count}`` summary."""
        counts: Dict[str, int] = {}
        for v in self.violations:
            key = v.violation_type.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    # -- serialization ------------------------------------------------------- #
    def to_list(self) -> List[Dict[str, Any]]:
        """Serialize to a list of plain dicts (JSON-friendly)."""
        return [v.to_dict() for v in self.violations]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the collection to a JSON-friendly dict."""
        return {
            "violations": self.to_list(),
            "summary": {
                "total": self.total,
                "errors": self.error_count,
                "warnings": self.warning_count,
                "info": self.info_count,
            },
        }

    @classmethod
    def from_list(cls, data: List[Dict[str, Any]]) -> "ViolationCollection":
        """Deserialize from a list of dicts."""
        violations = [DRCViolation.from_dict(d) for d in data]
        return cls(violations=violations)


# --------------------------------------------------------------------------- #
# DRCReport — top-level report wrapper
# --------------------------------------------------------------------------- #
@dataclass
class DRCReport:
    """A complete DRC report: metadata + violations.

    Attributes
    ----------
    board_file:
        Path to the ``.kicad_pcb`` file that was checked.
    board_title:
        Human-readable board title / project name.
    run_timestamp:
        ISO-8601 string timestamp of when the DRC was run.
    source:
        Origin of the report (e.g. ``"pcbnew"``, ``"netlist_checker"``).
    total_violations:
        Shortcut — mirrors ``len(self.violations)``.
    error_count, warning_count, info_count:
        Severity breakdown shortcuts.
    violations:
        The :class:`ViolationCollection` of all violations found.
    """

    board_file: str
    board_title: str = ""
    run_timestamp: str = ""
    source: str = "pcbnew_drc"
    violations: ViolationCollection = field(default_factory=ViolationCollection)

    # -- serialization ------------------------------------------------------- #
    def to_dict(self) -> Dict[str, Any]:
        """Serialize the entire report to a JSON-friendly dict."""
        return {
            "board_file": self.board_file,
            "board_title": self.board_title,
            "run_timestamp": self.run_timestamp,
            "source": self.source,
            "summary": {
                "total": self.total_violations,
                "errors": self.error_count,
                "warnings": self.warning_count,
                "info": self.info_count,
            },
            "violations": self.violations.to_list(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DRCReport":
        """Deserialize from a dict (inverse of :meth:`to_dict`)."""
        vc = ViolationCollection.from_list(data.get("violations", []))
        return cls(
            board_file=data["board_file"],
            board_title=data.get("board_title", ""),
            run_timestamp=data.get("run_timestamp", ""),
            source=data.get("source", "pcbnew_drc"),
            violations=vc,
        )

    # -- derived properties -------------------------------------------------- #
    @property
    def total_violations(self) -> int:
        return self.violations.total

    @property
    def error_count(self) -> int:
        return self.violations.error_count

    @property
    def warning_count(self) -> int:
        return self.violations.warning_count

    @property
    def info_count(self) -> int:
        return self.violations.info_count
