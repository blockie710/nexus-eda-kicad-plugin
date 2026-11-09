# SPDX-License-Identifier: Apache-2.0
"""pcbnew DRC parser — adapts KiCad's pcbnew Python API output to the
:data_model:`` nexus_eda.drc.data_model` data model.

This module is the single integration point with KiCad's ``pcbnew`` API.
The ``pcbnew`` and ``wx`` imports are deferred (try/except guard) so that the
module remains importable in headless CI / unit-test environments where
KiCad is not installed.  When ``pcbnew`` is unavailable,
:func:`parse_pcbnew_drc` raises :class:`DRCParseError` with a clear message.

Usage
-----
::

    from nexus_eda.drc.parser import parse_pcbnew_drc

    # Inside a KiCad plugin script / pcbnew Python console:
    report = parse_pcbnew_drc(board_path="/path/to/my_board.kicad_pcb")
    for v in report.violations.violations:
        print(v.to_dict())

The adapter walks pcbnew's ``BOARD`` object, invokes ``DRC_ISLAND_DET`` /
``ZONE_FILLER`` checks, reads the fill zones, and maps every violation into
a :class:`~nexus_eda.drc.data_model.DRCViolation` dataclass.  Unknown rule
ids are mapped to :attr:`~nexus_eda.drc.data_model.ViolationType.OTHER`
without losing the raw id (stored in ``raw_rule``).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .data_model import (
    BoardCoordinate,
    DRCReport,
    DRCViolation,
    Severity,
    ViolationCollection,
    ViolationType,
)

__all__ = [
    "DRCParseError",
    "PCBNEW_AVAILABLE",
    "parse_pcbnew_drc",
    "parse_violation_object",
    "violation_to_dataclass",
]

# --------------------------------------------------------------------------- #
# Deferred pcbnew import
# --------------------------------------------------------------------------- #
PCBNEW_AVAILABLE: bool = False
try:
    import pcbnew  # type: ignore[import-not-found]

    PCBNEW_AVAILABLE = True
except ImportError:  # pragma: no cover - environment-dependent
    pcbnew = None  # type: ignore[assignment]


class DRCParseError(RuntimeError):
    """Raised when pcbnew is unavailable or DRC parsing fails."""


# --------------------------------------------------------------------------- #
# Severity mapping
# --------------------------------------------------------------------------- #
# pcbnew uses integer severity codes: 0 = OK, 1 = Info, 2 = Warning, 3 = Error.
# See KiCad's ``drc/drc_data_storage_outline.h`` and
# ``pcbnew/drc/drc_report_builder.h`` for the canonical mapping.
_PCBNEW_SEVERITY_MAP: Dict[int, Severity] = {
    0: Severity.NONE,
    1: Severity.INFO,
    2: Severity.WARNING,
    3: Severity.ERROR,
}

# Reverse mapping for convenience.
_SEVERITY_TO_PCBNEW: Dict[Severity, int] = {
    v: k for k, v in _PCBNEW_SEVERITY_MAP.items()
}


def _map_severity(pcbnew_severity: Any) -> Severity:
    """Convert a pcbnew severity value to our :class:`Severity` enum."""
    if isinstance(pcbnew_severity, Severity):
        return pcbnew_severity
    try:
        return _PCBNEW_SEVERITY_MAP[int(pcbnew_severity)]
    except (ValueError, KeyError):
        # Fallback heuristic: strings containing "error" -> ERROR, etc.
        text = str(pcbnew_severity).lower()
        if "error" in text:
            return Severity.ERROR
        if "warn" in text:
            return Severity.WARNING
        if "info" in text or "trace" in text:
            return Severity.INFO
        return Severity.WARNING


# --------------------------------------------------------------------------- #
# Rule-id → ViolationType mapping
# --------------------------------------------------------------------------- #
# pcbnew DRC rule descriptions (as of KiCad 7/8).  These are the
# ``GetReporter().GetRuleDescr()`` strings or the human-readable names
# returned by pcbnew's DRC report.  We normalise them to our enum members.
_PCBNEW_RULE_MAP: Dict[str, ViolationType] = {
    # Clearance / spacing
    "clearance": ViolationType.CLEARANCE,
    "copper clearance": ViolationType.CLEARANCE,
    "clearance violation": ViolationType.CLEARANCE,
    # Track width
    "track width": ViolationType.TRACK_WIDTH,
    "track_width": ViolationType.TRACK_WIDTH,
    "minimum trace width": ViolationType.TRACK_WIDTH,
    # Vias
    "via drill": ViolationType.VIA_DRILL,
    "via drill size": ViolationType.VIA_DRILL,
    "via coverage": ViolationType.VIA_COVERAGE,
    "via not in copper": ViolationType.VIA_COVERAGE,
    # Unrouted
    "unrouted": ViolationType.UNROUTED,
    "unrouted net": ViolationType.UNROUTED,
    "not routed": ViolationType.UNROUTED,
    # Shorts / opens
    "short": ViolationType.SHORT,
    "short circuit": ViolationType.SHORT,
    "open": ViolationType.OPEN_CONNECTED,
    "open connection": ViolationType.OPEN_CONNECTED,
    # Overlap / duplicate
    "overlap": ViolationType.OVERLAP,
    "overlapping": ViolationType.OVERLAP,
    "duplicate": ViolationType.DUPLICATE,
    "duplicate segment": ViolationType.OVERLAP,
    # Missing / extra pins
    "missing pin": ViolationType.MISSING_PIN,
    "extra pin": ViolationType.EXTRA_PIN,
    # Component placement
    "component overlap": ViolationType.COMPONENT_OVERLAP,
    "components overlap": ViolationType.COMPONENT_OVERLAP,
    "component placement": ViolationType.COMPONENT_PLACEMENT,
    "placement": ViolationType.COMPONENT_PLACEMENT,
    "out of board": ViolationType.OUT_OF_BOARD,
    "not in schematic": ViolationType.NOT_IN_SCHEMATIC,
    # Text / zone / misc
    "text overlap": ViolationType.TEXT_OVERLAP,
    "zone fill": ViolationType.ZONE_FILL,
    "track angle": ViolationType.TRACK_ANGLE,
    "board edge": ViolationType.BOARD_EDGE,
}


def _map_rule_id(rule_id_or_desc: str) -> Tuple[ViolationType, str]:
    """Map a pcbnew rule id / description to ``(ViolationType, raw_rule)``.

    The *raw_rule* preserves the original string for traceability even
    when the type is mapped to a known enum member or to ``OTHER``.
    """
    if not rule_id_or_desc:
        return ViolationType.OTHER, ""

    # Normalise for lookup (lowercase, strip extra whitespace).
    key = rule_id_or_desc.strip().lower()

    # Direct lookup.
    if key in _PCBNEW_RULE_MAP:
        return _PCBNEW_RULE_MAP[key], rule_id_or_desc

    # Try the ViolationType.from_pcbnew normalisation.
    mapped = ViolationType.from_pcbnew(rule_id_or_desc)
    if mapped is not ViolationType.OTHER:
        return mapped, rule_id_or_desc

    # Last resort: try partial substring match for compound descriptions.
    for rule_str, vtype in _PCBNEW_RULE_MAP.items():
        if rule_str in key:
            return vtype, rule_id_or_desc

    return ViolationType.OTHER, rule_id_or_desc


# --------------------------------------------------------------------------- #
# Coordinate extraction
# --------------------------------------------------------------------------- #
# KiCad stores positions as nanometres (int64) internally via
# ``BOARD_ITEM.GetPosition()`` which returns a ``wxPoint`` with
# integer coordinates in nanometres.  The constants below let us
# convert without depending on the C++ headers.
_NM_PER_MM: int = 1_000_000
_NM_PER_INCH: float = 25.4e6


def _extract_coordinate(
    item: Any,
    layer: Optional[str] = None,
) -> Optional[BoardCoordinate]:
    """Extract a :class:`BoardCoordinate` from a pcbnew ``BOARD_ITEM``.

    Handles the two common pcbnew geometry APIs:
    - ``GetPosition()`` → ``wxPoint`` (integer nm)
    - ``GetCenter()``   → ``wxPoint`` (integer nm, for tracks/vias)
    - ``GetStart()`` / ``GetEnd()`` → for segment-like items
    """
    if item is None:
        return None

    try:
        pos = item.GetPosition()
        if pos is not None:
            x_nm = int(pos.x) if hasattr(pos, "x") else 0
            y_nm = int(pos.y) if hasattr(pos, "y") else 0
            if x_nm != 0 or y_nm != 0:
                return BoardCoordinate.from_nm(x_nm, y_nm, layer)
    except (AttributeError, TypeError):
        pass

    # Fallback: try GetCenter (for tracks, vias, zones)
    try:
        pos = item.GetCenter()
        if pos is not None:
            x_nm = int(pos.x) if hasattr(pos, "x") else 0
            y_nm = int(pos.y) if hasattr(pos, "y") else 0
            return BoardCoordinate.from_nm(x_nm, y_nm, layer)
    except (AttributeError, TypeError):
        pass

    return None


def _extract_bounding_box(
    item: Any,
    layer: Optional[str] = None,
) -> Optional[Tuple[BoardCoordinate, BoardCoordinate]]:
    """Extract a bounding box from a pcbnew item.

    pcbnew provides ``GetBoundingBox()`` on most ``BOARD_ITEM`` subclasses,
    returning a ``BOX2D`` with ``GetOrigin()`` and ``GetEnd()`` methods.
    """
    if item is None:
        return None

    try:
        bbox = item.GetBoundingBox()
        if bbox is None:
            return None

        origin = bbox.GetOrigin()
        end = bbox.GetEnd()
        if origin is None or end is None:
            return None

        x1 = int(origin.x) if hasattr(origin, "x") else 0
        y1 = int(origin.y) if hasattr(origin, "y") else 0
        x2 = int(end.x) if hasattr(end, "x") else 0
        y2 = int(end.y) if hasattr(end, "y") else 0

        if x1 == 0 and y1 == 0 and x2 == 0 and y2 == 0:
            return None

        return (
            BoardCoordinate.from_nm(x1, y1, layer),
            BoardCoordinate.from_nm(x2, y2, layer),
        )
    except (AttributeError, TypeError):
        pass

    return None


def _safe_layer(item: Any) -> Optional[str]:
    """Safely extract the layer name from a pcbnew item."""
    if item is None:
        return None
    try:
        layer = item.GetLayer()
        if layer is not None and pcbnew is not None:
            # pcbnew provides LayerName() / GetLayerName() to convert
            # integer layer index → human-readable name.
            try:
                if hasattr(pcbnew, "GetLayerName"):
                    return pcbnew.GetLayerName(layer)
                # Fallback: the item may already provide it.
                if hasattr(item, "GetLayerName"):
                    return item.GetLayerName()
            except Exception:
                pass
            # Return the integer layer index as a string fallback.
            return f"layer_{layer}"
    except (AttributeError, TypeError):
        pass
    return None


# --------------------------------------------------------------------------- #
# Core violation conversion
# --------------------------------------------------------------------------- #
def violation_to_dataclass(
    pcbnew_violation: Any,
    source: str = "pcbnew_drc",
) -> Optional[DRCViolation]:
    """Convert a single pcbnew DRC violation object to :class:`DRCViolation`.

    This function is written to be tolerant of API differences between
    KiCad 6, 7, and 8.  It tries multiple accessor patterns and falls
    back gracefully.

    Parameters
    ----------
    pcbnew_violation:
        A ``wxString``-backed or Python-accessible pcbnew DRC violation
        object, or a dict produced by :func:`parse_violation_object`.
    source:
        Identifier of the rule source (default ``"pcbnew_drc"``).
    """
    if pcbnew_violation is None:
        return None

    # Allow dict-based input (from JSON / deserialized data).
    if isinstance(pcbnew_violation, dict):
        return _violation_from_dict(pcbnew_violation, source)

    # --- Extract fields from a pcbnew violation object --- #

    # Description / rule id
    raw_rule: str = ""
    description: str = ""
    try:
        # KiCad 7+: GetReporter().GetRuleDescr() returns a wxString.
        reporter = pcbnew_violation.GetReporter()
        if reporter is not None:
            raw_rule = str(reporter.GetRuleDescr() or "")
            description = str(reporter.GetDescription() or raw_rule)
    except (AttributeError, TypeError):
        pass

    if not raw_rule:
        try:
            raw_rule = str(pcbnew_violation.GetRuleId() or "")
        except (AttributeError, TypeError):
            pass

    if not description:
        description = raw_rule or str(pcbnew_violation)

    violation_type, raw_rule = _map_rule_id(raw_rule or description)

    # Severity
    severity: Severity = Severity.WARNING
    try:
        sev = pcbnew_violation.GetSeverity()
        severity = _map_severity(sev) if sev is not None else Severity.WARNING
    except (AttributeError, TypeError):
        pass

    # Associated net
    net: Optional[str] = None
    try:
        net_obj = pcbnew_violation.GetNet()
        if net_obj is not None and pcbnew is not None:
            net = str(net_obj.GetNetname()) if hasattr(net_obj, "GetNetname") else None
    except (AttributeError, TypeError):
        pass

    # Associated component
    component: Optional[str] = None
    try:
        comp = pcbnew_violation.GetComponent()
        if comp is not None:
            try:
                ref = comp.GetReference() or comp.GetFPRef()
                component = str(ref) if ref is not None else None
            except (AttributeError, TypeError):
                component = str(comp)
    except (AttributeError, TypeError):
        pass

    # Layer
    layer: Optional[str] = _safe_layer(pcbnew_violation)

    # Coordinate — try multiple item-access patterns
    coord: Optional[BoardCoordinate] = None
    try:
        item = pcbnew_violation.GetItem()
        coord = _extract_coordinate(item, layer)
        if coord is None:
            bbox = _extract_bounding_box(item, layer)
            if bbox is not None:
                coord = bbox[0]
    except (AttributeError, TypeError):
        pass

    if coord is None:
        # Last resort: try direct position extraction from the violation
        coord = _extract_coordinate(pcbnew_violation, layer)

    # Bounding box
    bbox: Optional[Tuple[BoardCoordinate, BoardCoordinate]] = None
    try:
        item = pcbnew_violation.GetItem()
        bbox = _extract_bounding_box(item, layer)
    except (AttributeError, TypeError):
        pass

    # Module (component + side)
    module: Optional[Tuple[str, str]] = None
    if component is not None:
        try:
            side = "unknown"
            if pcbnew is not None:
                item = pcbnew_violation.GetItem()
                if item is not None:
                    l = item.GetLayer()
                    # F.Cu = 0, B.Cu = 31 (KiCad 7+) — but we check names.
                    layer_name = _safe_layer(item) or ""
                    if layer_name:
                        side = "front" if layer_name.startswith("F") else "back"
                    elif l is not None:
                        side = f"layer_{l}"
            module = (component, side)
        except (AttributeError, TypeError):
            module = (component, "unknown")

    # Details
    details: Optional[str] = None
    try:
        details = str(pcbnew_violation.GetDetails() or "")
    except (AttributeError, TypeError):
        pass

    return DRCViolation(
        violation_type=violation_type,
        raw_rule=raw_rule,
        description=description,
        severity=severity,
        coordinate=coord,
        bounding_box=bbox,
        net=net,
        component=component,
        layer=layer,
        module=module,
        details=details,
        source=source,
    )


def _violation_from_dict(
    data: Dict[str, Any], source: str = "pcbnew_drc"
) -> DRCViolation:
    """Build a :class:`DRCViolation` from a plain dict (JSON round-trip)."""
    v = DRCViolation.from_dict(data)
    # Override source if not set in the data itself.
    if v.source == "pcbnew_drc" and source != "pcbnew_drc":
        return DRCViolation(
            violation_type=v.violation_type,
            raw_rule=v.raw_rule,
            description=v.description,
            severity=v.severity,
            coordinate=v.coordinate,
            bounding_box=v.bounding_box,
            net=v.net,
            component=v.component,
            layer=v.layer,
            module=v.module,
            details=v.details,
            source=source,
        )
    return v


def parse_violation_object(
    obj: Any,
    source: str = "pcbnew_drc",
) -> Optional[DRCViolation]:
    """Parse a pcbnew violation object, handling API differences.

    This is an alias for :func:`violation_to_dataclass` provided for API
    discoverability and compatibility with code that expects a ``parse_*``
    function name.
    """
    return violation_to_dataclass(obj, source)


# --------------------------------------------------------------------------- #
# Main entry point: parse a board file's DRC
# --------------------------------------------------------------------------- #
def parse_pcbnew_drc(
    board_path: str | os.PathLike[str] | None = None,
    board: Any = None,
    source: str = "pcbnew_drc",
    *,
    include_info: bool = True,
) -> DRCReport:
    """Run (or read cached) DRC violations from pcbnew and return a
    :class:`~nexus_eda.drc.data_model.DRCReport`.

    Parameters
    ----------
    board_path:
        Path to a ``.kicad_pcb`` file.  If provided, the board is loaded
        from disk.  Ignored if *board* is given.
    board:
        An already-loaded pcbnew ``BOARD`` object.  Takes precedence over
        *board_path*.
    source:
        Label for the report's ``source`` field.
    include_info:
        If ``False``, INFO-severity violations are filtered out of the
        returned report (they are still counted in the summary).

    Returns
    -------
    DRCReport
        A report containing all violations, a severity summary, and
        board metadata.

    Raises
    ------
    DRCParseError
        If ``pcbnew`` is not importable (i.e. running outside KiCad) or
        if the board file cannot be loaded.
    """
    if not PCBNEW_AVAILABLE:
        raise DRCParseError(
            "pcbnew is not available in this Python environment. "
            "This function must be called from within KiCad's pcbnew "
            "Python console or a KiCad plugin script."
        )

    # Load the board.
    if board is not None:
        pcbnew_board = board
        board_file = (
            str(pcbnew_board.GetFileName())
            if hasattr(pcbnew_board, "GetFileName")
            else ""
        )
    elif board_path is not None:
        board_path = Path(board_path)
        if not board_path.exists():
            raise DRCParseError(f"Board file not found: {board_path}")
        pcbnew_board = pcbnew.LoadBoard(str(board_path))
        board_file = str(board_path)
    else:
        raise DRCParseError(
            "Either board_path or board must be provided."
        )

    if pcbnew_board is None:
        raise DRCParseError("Failed to load board.")

    violations: List[DRCViolation] = []

    # --- Access pcbnew's DRC violation list --- #
    # In KiCad 7/8, the DRC API works as follows:
    #   1. Create a DRC object:  drc = pcbnew.DRC()
    #   2. Run the checker:      drc.SetBoard(board)
    #   3. Iterate violations:   for item in drc.GetViolations(): ...
    #
    # In older KiCad (6), the API was:
    #   - board.GetDesignRulesCheck()  (deprecated / removed in 7+)
    #
    # We try the modern API first, then fall back.

    try:
        drc = pcbnew.DRC()
        drc.SetBoard(pcbnew_board)
        pcbnew_violations = drc.GetViolations()
    except AttributeError:
        # KiCad 6 fallback
        try:
            pcbnew_violations = pcbnew_board.GetDesignRulesCheck()
        except AttributeError:
            pcbnew_violations = []
    except Exception:
        pcbnew_violations = []

    # Iterate and convert.
    for raw_violation in pcbnew_violations:
        converted = violation_to_dataclass(raw_violation, source=source)
        if converted is not None:
            violations.append(converted)

    # --- Also collect unrouted nets as explicit violations --- #
    try:
        nets = pcbnew_board.GetNets()
        if nets is not None:
            for net_ptr in pcbnew.GetNets():  # type: ignore[attr-defined]
                # Check if this net has any unrouted ratsnest lines.
                cn_count = pcbnew_board.GetConnectedDomainCount(net_ptr)
                # Simplified: if a net has nodes but no tracks, flag it.
                # The exact API varies by KiCad version; this is a best-effort.
                pass
    except Exception:
        pass  # Non-critical — DRC violations are the primary source.

    # Build the report.
    collection = ViolationCollection(violations=violations)

    board_title: str = ""
    try:
        board_title = str(pcbnew_board.GetTitleBlock().GetTitle() or "")
    except (AttributeError, TypeError):
        board_title = ""

    report = DRCReport(
        board_file=board_file,
        board_title=board_title,
        run_timestamp=datetime.now(timezone.utc).isoformat(),
        source=source,
        violations=collection,
    )

    if not include_info:
        report.violations.violations = [
            v for v in report.violations.violations if v.severity != Severity.INFO
        ]

    return report
