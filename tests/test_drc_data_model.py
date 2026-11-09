# SPDX-License-Identifier: Apache-2.0
"""Tests for the DRC data model and pcbnew adapter.

Covers:
- BoardCoordinate construction, unit conversion, serialization.
- ViolationType enum mapping, registry, dynamic registration.
- DRCViolation serialization round-trip, from_dict resilience.
- ViolationCollection filtering, summaries, severity/type counts.
- DRCReport serialization, summary correctness.
- Parser adapter: dict-based parsing, rule mapping, severity mapping.
"""

import json
import os
import sys

import pytest

# Ensure src is on path (mirrors conftest / existing test pattern).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nexus_eda.drc import (  # noqa: E402
    BoardCoordinate,
    DRCReport,
    DRCViolation,
    PCBNEW_AVAILABLE,
    Severity,
    ViolationCollection,
    ViolationType,
)
from nexus_eda.drc.parser import (  # noqa: E402
    DRCParseError,
    _map_rule_id,
    _map_severity,
    parse_violation_object,
    violation_to_dataclass,
)


# --------------------------------------------------------------------------- #
# BoardCoordinate
# --------------------------------------------------------------------------- #
class TestBoardCoordinate:
    def test_from_nm(self):
        coord = BoardCoordinate.from_nm(1_000_000, 500_000, layer="F.Cu")
        assert coord.x_nm == 1_000_000
        assert coord.y_nm == 500_000
        assert coord.layer == "F.Cu"

    def test_from_mm(self):
        coord = BoardCoordinate.from_mm(10.0, 5.0)
        assert coord.x_nm == 10_000_000
        assert coord.y_nm == 5_000_000
        assert coord.mm_x == pytest.approx(10.0)
        assert coord.mm_y == pytest.approx(5.0)

    def test_from_inch(self):
        coord = BoardCoordinate.from_inch(1.0, 0.5)
        assert coord.inch_x == pytest.approx(1.0)
        assert coord.inch_y == pytest.approx(0.5)
        # Round-trip: 1 inch = 25.4 mm
        assert coord.mm_x == pytest.approx(25.4)

    def test_layer_is_optional(self):
        coord = BoardCoordinate.from_nm(100, 200)
        assert coord.layer is None

    def test_mm_x_y_properties(self):
        coord = BoardCoordinate.from_nm(1_500_000, 750_000, "B.SilkS")
        assert coord.mm_x == pytest.approx(1.5)
        assert coord.mm_y == pytest.approx(0.75)

    def test_to_dict_round_trip(self):
        coord = BoardCoordinate.from_nm(1234567, 8901234, "F.Mask")
        d = coord.to_dict()
        assert d["x_nm"] == 1234567
        assert d["y_nm"] == 8901234
        assert d["layer"] == "F.Mask"
        restored = BoardCoordinate.from_dict(d)
        assert restored == coord

    def test_to_dict_no_layer(self):
        coord = BoardCoordinate.from_nm(100, 200)
        d = coord.to_dict()
        assert d["layer"] is None

    def test_to_mm_tuple(self):
        coord = BoardCoordinate.from_mm(3.5, 7.25)
        mm_x, mm_y = coord.to_mm_tuple()
        assert mm_x == pytest.approx(3.5)
        assert mm_y == pytest.approx(7.25)

    def test_to_inch_tuple(self):
        coord = BoardCoordinate.from_inch(2.0, 1.0)
        inch_x, inch_y = coord.to_inch_tuple()
        assert inch_x == pytest.approx(2.0)
        assert inch_y == pytest.approx(1.0)

    def test_immutability(self):
        coord = BoardCoordinate.from_nm(0, 0)
        with pytest.raises(Exception):  # frozen dataclass raises FrozenInstanceError
            coord.x_nm = 100

    def test_equality(self):
        c1 = BoardCoordinate.from_nm(1_000_000, 2_000_000, "F.Cu")
        c2 = BoardCoordinate.from_nm(1_000_000, 2_000_000, "F.Cu")
        c3 = BoardCoordinate.from_nm(1_000_000, 2_000_000, "B.Cu")
        assert c1 == c2
        assert c1 != c3

    def test_location_str(self):
        coord = BoardCoordinate.from_mm(10.5, 20.0, "F.Cu")
        assert "10.500" in str(coord)
        assert "20.000" in str(coord)
        assert "F.Cu" in str(coord)

    def test_location_str_no_layer(self):
        coord = BoardCoordinate.from_nm(1000, 2000)
        assert "layer=" not in str(coord)


# --------------------------------------------------------------------------- #
# Severity
# --------------------------------------------------------------------------- #
class TestSeverity:
    def test_values(self):
        assert Severity.ERROR.value == "error"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"
        assert Severity.NONE.value == "none"

    def test_is_str_enum(self):
        assert isinstance(Severity.ERROR, str)


# --------------------------------------------------------------------------- #
# ViolationType
# --------------------------------------------------------------------------- #
class TestViolationType:
    def test_known_members(self):
        assert ViolationType.CLEARANCE.value == "clearance"
        assert ViolationType.TRACK_WIDTH.value == "track_width"
        assert ViolationType.UNROUTED.value == "unrouted"
        assert ViolationType.SHORT.value == "short"

    def test_from_pcbnew_known(self):
        assert ViolationType.from_pcbnew("clearance") == ViolationType.CLEARANCE
        assert ViolationType.from_pcbnew("Track Width") == ViolationType.TRACK_WIDTH
        assert ViolationType.from_pcbnew("Unrouted") == ViolationType.UNROUTED
        assert ViolationType.from_pcbnew("unrouted net") == ViolationType.UNROUTED

    def test_from_pcbnew_unknown(self):
        assert ViolationType.from_pcbnew("some_custom_rule") == ViolationType.OTHER
        assert ViolationType.from_pcbnew("not_a_real_rule") == ViolationType.OTHER

    def test_from_pcbnew_none(self):
        assert ViolationType.from_pcbnew(None) == ViolationType.OTHER

    def test_from_pcbnew_hyphenated(self):
        # Hyphens and spaces should be normalised.
        assert ViolationType.from_pcbnew("copper-clearance") == ViolationType.OTHER
        # "copper clearance" is in the _PCBNEW_RULE_MAP
        assert ViolationType.from_pcbnew("copper clearance") == ViolationType.CLEARANCE

    def test_display_name(self):
        assert ViolationType.CLEARANCE.display_name == "Clearance"
        assert ViolationType.UNROUTED.display_name == "Unrouted Net"
        assert ViolationType.OTHER.display_name == "Other"

    def test_category(self):
        assert ViolationType.CLEARANCE.category == "Electrical"
        assert ViolationType.COMPONENT_OVERLAP.category == "Component"
        assert ViolationType.TEXT_OVERLAP.category == "Miscellaneous"
        assert ViolationType.OTHER.category == "Miscellaneous"

    def test_register_dynamic(self):
        ViolationType.register("test_custom_rule", "Test Custom Rule", "Custom")
        assert "test_custom_rule" in ViolationType._registry
        display, cat = ViolationType._registry["test_custom_rule"]
        assert display == "Test Custom Rule"
        assert cat == "Custom"


# --------------------------------------------------------------------------- #
# _map_rule_id
# --------------------------------------------------------------------------- #
class TestMapRuleId:
    def test_known_mapping(self):
        vtype, raw = _map_rule_id("clearance")
        assert vtype == ViolationType.CLEARANCE
        assert raw == "clearance"

    def test_unknown_returns_other_with_raw_preserved(self):
        vtype, raw = _map_rule_id("my_custom_violation")
        assert vtype == ViolationType.OTHER
        assert raw == "my_custom_violation"

    def test_empty_string(self):
        vtype, raw = _map_rule_id("")
        assert vtype == ViolationType.OTHER
        assert raw == ""

    def test_partial_match(self):
        vtype, raw = _map_rule_id("Clearance violation at (0, 0)")
        assert vtype == ViolationType.CLEARANCE
        assert raw == "Clearance violation at (0, 0)"

    def test_via_coverage(self):
        vtype, raw = _map_rule_id("via not in copper")
        assert vtype == ViolationType.VIA_COVERAGE


# --------------------------------------------------------------------------- #
# _map_severity
# --------------------------------------------------------------------------- #
class TestMapSeverity:
    def test_int_0(self):
        assert _map_severity(0) == Severity.NONE

    def test_int_1(self):
        assert _map_severity(1) == Severity.INFO

    def test_int_2(self):
        assert _map_severity(2) == Severity.WARNING

    def test_int_3(self):
        assert _map_severity(3) == Severity.ERROR

    def test_severity_enum_passthrough(self):
        assert _map_severity(Severity.ERROR) == Severity.ERROR

    def test_unknown_int(self):
        assert _map_severity(99) == Severity.WARNING

    def test_string_fallback(self):
        assert _map_severity("error") == Severity.ERROR
        assert _map_severity("warning") == Severity.WARNING
        assert _map_severity("info") == Severity.INFO

    def test_string_partial(self):
        assert _map_severity("ERROR!") == Severity.ERROR
        assert _map_severity("warn") == Severity.WARNING


# --------------------------------------------------------------------------- #
# DRCViolation
# --------------------------------------------------------------------------- #
class TestDRCViolation:
    def _make_violation(self, **kwargs) -> DRCViolation:
        defaults = dict(
            violation_type=ViolationType.CLEARANCE,
            raw_rule="clearance",
            description="Copper clearance too small",
            severity=Severity.WARNING,
            coordinate=BoardCoordinate.from_mm(10.0, 5.0, "F.Cu"),
            net="GND",
            component="R1",
            layer="F.Cu",
            details="Clearance: 0.10mm (min: 0.15mm)",
        )
        defaults.update(kwargs)
        return DRCViolation(**defaults)

    def test_construction(self):
        v = self._make_violation()
        assert v.violation_type == ViolationType.CLEARANCE
        assert v.raw_rule == "clearance"
        assert v.description == "Copper clearance too small"
        assert v.severity == Severity.WARNING
        assert v.coordinate is not None
        assert v.coordinate.mm_x == pytest.approx(10.0)
        assert v.net == "GND"
        assert v.component == "R1"
        assert v.layer == "F.Cu"
        assert v.details == "Clearance: 0.10mm (min: 0.15mm)"
        assert v.source == "pcbnew_drc"

    def test_defaults(self):
        v = DRCViolation(
            violation_type=ViolationType.OTHER,
            raw_rule="unknown_rule",
            description="Something",
        )
        assert v.severity == Severity.WARNING
        assert v.coordinate is None
        assert v.bounding_box is None
        assert v.net is None
        assert v.component is None
        assert v.layer is None
        assert v.module is None
        assert v.details is None
        assert v.source == "pcbnew_drc"

    def test_immutable(self):
        v = self._make_violation()
        with pytest.raises(Exception):
            v.description = "modified"

    def test_to_dict(self):
        v = self._make_violation()
        d = v.to_dict()
        assert d["violation_type"] == "clearance"
        assert d["raw_rule"] == "clearance"
        assert d["description"] == "Copper clearance too small"
        assert d["severity"] == "warning"
        assert d["coordinate"]["x_nm"] == 10_000_000
        assert d["coordinate"]["layer"] == "F.Cu"
        assert d["net"] == "GND"
        assert d["component"] == "R1"
        assert d["layer"] == "F.Cu"
        assert d["details"] == "Clearance: 0.10mm (min: 0.15mm)"
        assert d["source"] == "pcbnew_drc"
        assert d["bounding_box"] is None
        assert d["module"] is None

    def test_to_dict_with_bounding_box_and_module(self):
        coord_a = BoardCoordinate.from_nm(1_000_000, 2_000_000, "F.Cu")
        coord_b = BoardCoordinate.from_nm(3_000_000, 4_000_000, "F.Cu")
        v = self._make_violation(
            bounding_box=(coord_a, coord_b),
            module=("R1", "front"),
            coordinate=None,
        )
        d = v.to_dict()
        assert d["bounding_box"] is not None
        assert d["bounding_box"][0]["x_nm"] == 1_000_000
        assert d["bounding_box"][1]["y_nm"] == 4_000_000
        assert d["coordinate"] is None
        assert d["module"] == ["R1", "front"]

    def test_from_dict_round_trip(self):
        v1 = self._make_violation(
            bounding_box=(
                BoardCoordinate.from_mm(0.0, 0.0, "F.Cu"),
                BoardCoordinate.from_mm(1.0, 1.0, "F.Cu"),
            ),
            module=("U1", "back"),
        )
        d = v1.to_dict()
        v2 = DRCViolation.from_dict(d)
        assert v2 == v1
        assert v2.violation_type == ViolationType.CLEARANCE
        assert v2.severity == Severity.WARNING
        assert v2.bounding_box is not None
        assert v2.bounding_box[0].mm_x == pytest.approx(0.0)
        assert v2.bounding_box[1].mm_y == pytest.approx(1.0)
        assert v2.module == ("U1", "back")

    def test_from_dict_unknown_violation_type(self):
        d = {
            "violation_type": "some_future_rule",
            "raw_rule": "some_future_rule",
            "description": "Future rule",
            "severity": "error",
            "coordinate": None,
            "bounding_box": None,
            "net": None,
            "component": None,
            "layer": None,
            "module": None,
            "details": None,
            "source": "pcbnew_drc",
        }
        v = DRCViolation.from_dict(d)
        assert v.violation_type == ViolationType.OTHER
        assert v.raw_rule == "some_future_rule"

    def test_from_dict_unknown_severity(self):
        d = {
            "violation_type": "clearance",
            "raw_rule": "clearance",
            "description": "test",
            "severity": "critical",
            "coordinate": None,
            "bounding_box": None,
            "net": None,
            "component": None,
            "layer": None,
            "module": None,
            "details": None,
            "source": "pcbnew_drc",
        }
        v = DRCViolation.from_dict(d)
        assert v.severity == Severity.WARNING  # fallback

    def test_from_dict_missing_fields(self):
        d = {
            "violation_type": "clearance",
            "raw_rule": "clearance",
            "description": "test",
        }
        v = DRCViolation.from_dict(d)
        assert v.severity == Severity.WARNING
        assert v.coordinate is None
        assert v.net is None

    def test_display_type(self):
        v = self._make_violation(violation_type=ViolationType.CLEARANCE)
        assert v.display_type == "Clearance"

    def test_category(self):
        v = self._make_violation(violation_type=ViolationType.TRACK_WIDTH)
        assert v.category == "Electrical"

    def test_location_str_with_all_fields(self):
        v = self._make_violation()
        loc = v.location_str()
        assert "GND" in loc
        assert "R1" in loc
        assert "F.Cu" in loc

    def test_location_str_minimal(self):
        v = DRCViolation(
            violation_type=ViolationType.OTHER,
            raw_rule="unknown",
            description="test",
        )
        assert v.location_str() == "(location not specified)"

    def test_json_serializable(self):
        v = self._make_violation(
            bounding_box=(
                BoardCoordinate.from_mm(0.5, 0.5, "F.Cu"),
                BoardCoordinate.from_mm(1.5, 2.0, "F.Cu"),
            )
        )
        d = v.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["violation_type"] == "clearance"
        v2 = DRCViolation.from_dict(parsed)
        assert v2 == v


# --------------------------------------------------------------------------- #
# ViolationCollection
# --------------------------------------------------------------------------- #
class TestViolationCollection:
    def _make_collection(self) -> ViolationCollection:
        coords = [BoardCoordinate.from_mm(10.0, 5.0, "F.Cu")] * 2
        vs = [
            DRCViolation(
                violation_type=ViolationType.CLEARANCE,
                raw_rule="clearance",
                description="Clearance too small",
                severity=Severity.ERROR,
                coordinate=coords[0],
                net="GND",
                component="R1",
            ),
            DRCViolation(
                violation_type=ViolationType.TRACK_WIDTH,
                raw_rule="track_width",
                description="Track too thin",
                severity=Severity.WARNING,
                coordinate=coords[1],
                net="VCC",
                component="C1",
            ),
            DRCViolation(
                violation_type=ViolationType.INFO,  # not valid but tests info path
                raw_rule="info",
                description="Info",
                severity=Severity.INFO,
                net="SCL",
            ) if False else DRCViolation(
                violation_type=ViolationType.COMPONENT_PLACEMENT,
                raw_rule="placement",
                description="Component placement",
                severity=Severity.INFO,
                component="U1",
            ),
        ]
        return ViolationCollection(violations=vs)

    def test_total(self):
        vc = self._make_collection()
        assert vc.total == 3

    def test_by_severity_error(self):
        vc = self._make_collection()
        errors = vc.by_severity(Severity.ERROR)
        assert len(errors) == 1
        assert errors[0].violation_type == ViolationType.CLEARANCE

    def test_by_severity_warning(self):
        vc = self._make_collection()
        warnings = vc.by_severity(Severity.WARNING)
        assert len(warnings) == 1

    def test_by_severity_info(self):
        vc = self._make_collection()
        infos = vc.by_severity(Severity.INFO)
        assert len(infos) == 1

    def test_by_severity_string(self):
        vc = self._make_collection()
        errors = vc.by_severity("error")
        assert len(errors) == 1

    def test_by_type(self):
        vc = self._make_collection()
        clearance = vc.by_type(ViolationType.CLEARANCE)
        assert len(clearance) == 1
        assert clearance[0].severity == Severity.ERROR

    def test_by_type_string(self):
        vc = self._make_collection()
        track = vc.by_type("track_width")
        assert len(track) == 1

    def test_by_net(self):
        vc = self._make_collection()
        gnd = vc.by_net("GND")
        assert len(gnd) == 1
        assert gnd[0].component == "R1"

    def test_by_component(self):
        vc = self._make_collection()
        r1 = vc.by_component("R1")
        assert len(r1) == 1

    def test_by_category(self):
        vc = self._make_collection()
        electrical = vc.by_category("Electrical")
        assert len(electrical) == 2  # clearance + track_width
        component = vc.by_category("Component")
        assert len(component) == 1

    def test_severity_summary(self):
        vc = self._make_collection()
        summary = vc.severity_summary()
        assert summary == {"error": 1, "warning": 1, "info": 1}

    def test_type_summary(self):
        vc = self._make_collection()
        summary = vc.type_summary()
        assert summary == {
            "clearance": 1,
            "track_width": 1,
            "component_placement": 1,
        }

    def test_error_count(self):
        vc = self._make_collection()
        assert vc.error_count == 1

    def test_warning_count(self):
        vc = self._make_collection()
        assert vc.warning_count == 1

    def test_info_count(self):
        vc = self._make_collection()
        assert vc.info_count == 1

    def test_to_list(self):
        vc = self._make_collection()
        lst = vc.to_list()
        assert len(lst) == 3
        assert isinstance(lst[0], dict)
        assert lst[0]["violation_type"] == "clearance"

    def test_to_dict(self):
        vc = self._make_collection()
        d = vc.to_dict()
        assert d["summary"]["total"] == 3
        assert d["summary"]["errors"] == 1
        assert d["summary"]["warnings"] == 1
        assert d["summary"]["info"] == 1
        assert len(d["violations"]) == 3

    def test_from_list(self):
        vc1 = self._make_collection()
        d = vc1.to_list()
        vc2 = ViolationCollection.from_list(d)
        assert vc2.total == vc1.total
        for v1, v2 in zip(vc1.violations, vc2.violations):
            assert v1 == v2

    def test_empty_collection(self):
        vc = ViolationCollection()
        assert vc.total == 0
        assert vc.error_count == 0
        assert vc.warning_count == 0
        assert vc.info_count == 0
        assert vc.to_list() == []
        assert vc.to_dict()["summary"]["total"] == 0


# --------------------------------------------------------------------------- #
# DRCReport
# --------------------------------------------------------------------------- #
class TestDRCReport:
    def _make_report(self) -> DRCReport:
        violations = [
            DRCViolation(
                violation_type=ViolationType.CLEARANCE,
                raw_rule="clearance",
                description="Clearance too small",
                severity=Severity.ERROR,
                net="GND",
                coordinate=BoardCoordinate.from_mm(5.0, 5.0, "F.Cu"),
            ),
            DRCViolation(
                violation_type=ViolationType.UNROUTED,
                raw_rule="unrouted",
                description="Net not routed",
                severity=Severity.WARNING,
                net="NC1",
                coordinate=None,
            ),
        ]
        return DRCReport(
            board_file="/test/board.kicad_pcb",
            board_title="Test Board",
            run_timestamp="2026-08-28T12:00:00+00:00",
            source="pcbnew_drc",
            violations=ViolationCollection(violations=violations),
        )

    def test_construction(self):
        r = self._make_report()
        assert r.board_file == "/test/board.kicad_pcb"
        assert r.board_title == "Test Board"
        assert r.run_timestamp == "2026-08-28T12:00:00+00:00"
        assert r.source == "pcbnew_drc"
        assert r.total_violations == 2

    def test_summary_properties(self):
        r = self._make_report()
        assert r.error_count == 1
        assert r.warning_count == 1
        assert r.info_count == 0

    def test_to_dict(self):
        r = self._make_report()
        d = r.to_dict()
        assert d["board_file"] == "/test/board.kicad_pcb"
        assert d["board_title"] == "Test Board"
        assert d["source"] == "pcbnew_drc"
        assert d["summary"]["total"] == 2
        assert d["summary"]["errors"] == 1
        assert d["summary"]["warnings"] == 1
        assert len(d["violations"]) == 2
        assert d["violations"][0]["violation_type"] == "clearance"
        assert d["violations"][1]["coordinate"] is None

    def test_from_dict_round_trip(self):
        r1 = self._make_report()
        d = r1.to_dict()
        r2 = DRCReport.from_dict(d)
        assert r2.board_file == r1.board_file
        assert r2.total_violations == r1.total_violations
        assert r2.error_count == r1.error_count
        assert r2.warning_count == r1.warning_count
        for v1, v2 in zip(r1.violations.violations, r2.violations.violations):
            assert v1 == v2

    def test_json_serializable(self):
        r = self._make_report()
        d = r.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["board_file"] == "/test/board.kicad_pcb"

    def test_default_empty_report(self):
        r = DRCReport(board_file="empty.kicad_pcb")
        assert r.total_violations == 0
        assert r.error_count == 0
        assert r.board_title == ""
        assert r.run_timestamp == ""


# --------------------------------------------------------------------------- #
# Parser adapter (dict-based, works without pcbnew)
# --------------------------------------------------------------------------- #
class TestParserAdapter:
    def test_parse_violation_from_dict(self):
        d = {
            "violation_type": "clearance",
            "raw_rule": "clearance",
            "description": "Clearance 0.1mm < 0.15mm",
            "severity": "error",
            "coordinate": {"x_nm": 5_000_000, "y_nm": 3_000_000, "layer": "F.Cu"},
            "net": "VCC",
            "component": "U1",
            "layer": "F.Cu",
            "details": "Min clearance: 0.15mm",
            "source": "pcbnew_drc",
        }
        v = parse_violation_object(d)
        assert v is not None
        assert v.violation_type == ViolationType.CLEARANCE
        assert v.severity == Severity.ERROR
        assert v.coordinate is not None
        assert v.coordinate.mm_x == pytest.approx(5.0)
        assert v.net == "VCC"
        assert v.component == "U1"

    def test_parse_violation_none(self):
        assert parse_violation_object(None) is None

    def test_violation_to_dataclass_none(self):
        assert violation_to_dataclass(None) is None

    def test_violation_to_dataclass_dict(self):
        d = {
            "violation_type": "short",
            "raw_rule": "short",
            "description": "Short between VCC and GND",
            "severity": "error",
            "net": "VCC",
            "component": None,
            "source": "custom",
        }
        v = violation_to_dataclass(d, source="custom")
        assert v is not None
        assert v.violation_type == ViolationType.SHORT
        assert v.source == "custom"

    def test_pcbnew_available_flag(self):
        # In this headless environment, pcbnew is NOT importable.
        # The flag should accurately reflect availability.
        assert isinstance(PCBNEW_AVAILABLE, bool)

    def test_parse_pcbnew_drc_without_pcbnew_imports(self):
        """Ensure the module imports without pcbnew (deferred import works)."""
        # The import at module top of __init__.py should have succeeded.
        # parse_pcbnew_drc should raise DRCParseError when pcbnew is absent.
        from nexus_eda.drc import parse_pcbnew_drc

        with pytest.raises(DRCParseError, match="pcbnew is not available"):
            parse_pcbnew_drc(board_path="/nonexistent/board.kicad_pcb")

    def test_parse_pcbnew_drc_no_args(self):
        from nexus_eda.drc import parse_pcbnew_drc

        with pytest.raises(DRCParseError, match="Either board_path"):
            parse_pcbnew_drc()


# --------------------------------------------------------------------------- #
# Integration: full report round-trip via JSON
# --------------------------------------------------------------------------- #
class TestFullIntegration:
    def test_end_to_end_json_round_trip(self):
        """Simulate what the NL summary generator will receive."""
        violations = [
            DRCViolation(
                violation_type=ViolationType.CLEARANCE,
                raw_rule="clearance",
                description="Clearance 0.10mm < 0.15mm minimum between pads",
                severity=Severity.ERROR,
                coordinate=BoardCoordinate.from_mm(25.4, 12.7, "F.Cu"),
                net="VCC",
                component="R1",
                layer="F.Cu",
                details="Actual: 0.10mm, Required: 0.15mm",
            ),
            DRCViolation(
                violation_type=ViolationType.UNROUTED,
                raw_rule="unrouted",
                description="Net 'NC_PIN' is not routed",
                severity=Severity.WARNING,
                net="NC_PIN",
                component="U1",
                layer=None,
            ),
            DRCViolation(
                violation_type=ViolationType.COMPONENT_OVERLAP,
                raw_rule="component overlap",
                description="Components R1 and C1 overlap by 2.3mm²",
                severity=Severity.ERROR,
                coordinate=BoardCoordinate.from_mm(10.0, 10.0, "F.Cu"),
                component="R1",
                layer="F.Cu",
                details="Overlap area: 2.3mm² with C1",
            ),
        ]
        collection = ViolationCollection(violations=violations)
        report = DRCReport(
            board_file="test_board.kicad_pcb",
            board_title="Test Board",
            run_timestamp="2026-08-28T12:00:00+00:00",
            source="pcbnew_drc",
            violations=collection,
        )

        # Serialize to JSON (simulating IPC / storage).
        json_str = json.dumps(report.to_dict())
        assert len(json_str) > 0

        # Deserialize (simulating what the summary generator receives).
        parsed = json.loads(json_str)
        restored = DRCReport.from_dict(parsed)

        assert restored.total_violations == 3
        assert restored.error_count == 2
        assert restored.warning_count == 1

        # Verify each violation round-tripped correctly.
        for orig, rest in zip(violations, restored.violations.violations):
            assert orig.violation_type == rest.violation_type
            assert orig.severity == rest.severity
            assert orig.raw_rule == rest.raw_rule
            assert orig.description == rest.description
            assert orig.net == rest.net
            assert orig.component == rest.component

        # Verify the summary generator can filter by severity.
        errors = restored.violations.by_severity(Severity.ERROR)
        assert len(errors) == 2

        # Verify filtering by category works.
        electrical = restored.violations.by_category("Electrical")
        component_violations = restored.violations.by_category("Component")
        assert len(electrical) == 2  # clearance + unrouted
        assert len(component_violations) == 1  # overlap

    def test_unknown_violation_type_preserved(self):
        """Unknown rule types should map to OTHER, preserving the raw_rule."""
        v = DRCViolation(
            violation_type=ViolationType.OTHER,
            raw_rule="future_kicad_rule_2027",
            description="A rule from a future KiCad version",
            severity=Severity.WARNING,
        )
        d = v.to_dict()
        assert d["violation_type"] == "other"
        assert d["raw_rule"] == "future_kicad_rule_2027"
        v2 = DRCViolation.from_dict(d)
        assert v2.violation_type == ViolationType.OTHER
        assert v2.raw_rule == "future_kicad_rule_2027"
