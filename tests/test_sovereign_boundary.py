# SPDX-License-Identifier: Apache-2.0
"""Tests for the sovereign data boundary."""
import os
import sys
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from nexus_eda.sovereign.boundary import (
    SovereignBoundary,
    SovereignPolicy,
    SovereignResult,
    ENTRY_POINTS,
    ENTRY_POINT_COUNT,
    SovereignEntryPoint,
    BoundaryError,
)


def test_entry_point_count():
    """All 28 entry points are defined."""
    assert ENTRY_POINT_COUNT == 28
    assert len(ENTRY_POINTS) == 28
    print("PASS: test_entry_point_count")


def test_entry_point_families():
    """Entry points are partitioned into the 4 families."""
    families = [ep.family for ep in ENTRY_POINTS]
    assert families.count("export") == 8
    assert families.count("import") == 6
    assert families.count("query") == 7
    assert families.count("control") == 7
    print("PASS: test_entry_point_families")


def test_boundary_export_strips_pdk():
    """Export entry points strip PDK paths."""
    boundary = SovereignBoundary()
    ep = boundary.get_entry_point("ep_export_netlist_json")
    data = {"pdk_path": "/pdk/asiapdk/OpenVIA/techfile.json"}
    result = boundary.export("ep_export_netlist_json", data)
    assert "[PDK_PATH_REDACTED]" in json.dumps(result.data)
    assert result.stripped_fields, "Should have stripped fields"
    print("PASS: test_boundary_export_strips_pdk")


def test_boundary_export_strips_project_paths():
    """Export entry points strip Windows project paths."""
    boundary = SovereignBoundary()
    data = {"file": r"C:\Users\bhogl\Projects\nexus-eda\worktrees\T4-W18\test.kicad_pcb"}
    result = boundary.export("ep_export_netlist_json", data)
    assert "[PROJECT_PATH_REDACTED]" in json.dumps(result.data)
    print("PASS: test_boundary_export_strips_project_paths")


def test_boundary_export_strips_user_id():
    """Export entry points strip user identifiers."""
    boundary = SovereignBoundary()
    data = {"designer": "User: blockie"}
    result = boundary.export("ep_export_netlist_json", data)
    assert "[USER_ID_REDACTED]" in json.dumps(result.data)
    print("PASS: test_boundary_export_strips_user_id")


def test_boundary_netlist_stripping():
    """Query entry points with strips_netlist=True return empty."""
    boundary = SovereignBoundary()
    result = boundary.query("ep_query_netlist_stats", "net R1 (port 1)")
    assert result.data == "", "Netlist should be fully stripped"
    assert "netlist" in result.stripped_fields
    print("PASS: test_boundary_netlist_stripping")


def test_boundary_unknown_entry_point():
    """Unknown entry points raise BoundaryError."""
    boundary = SovereignBoundary()
    try:
        boundary.get_entry_point("ep_does_not_exist")
        assert False, "Should have raised BoundaryError"
    except BoundaryError:
        pass
    print("PASS: test_boundary_unknown_entry_point")


def test_boundary_wrong_family():
    """Using export() with a query endpoint raises."""
    boundary = SovereignBoundary()
    try:
        boundary.export("ep_query_netlist_stats", {})
        assert False, "Should have raised BoundaryError"
    except BoundaryError:
        pass
    print("PASS: test_boundary_wrong_family")


def test_boundary_network_isolation():
    """Network isolation blocks exports referencing URLs."""
    boundary = SovereignBoundary()
    data = {"url": "https://api.lcsc.com/browse/"}
    try:
        boundary.export("ep_export_netlist_json", data)
        assert False, "Should have blocked network reference"
    except BoundaryError as e:
        assert "air-gap" in str(e).lower() or "network" in str(e).lower()
    print("PASS: test_boundary_network_isolation")


def test_boundary_non_training_guarantee():
    """Non-training guarantee blocks model training data."""
    boundary = SovereignBoundary()
    data = {"training_data": "some weights for model fine_tune"}
    try:
        boundary.export("ep_export_netlist_json", data)
        assert False, "Should have blocked training data"
    except BoundaryError:
        pass
    print("PASS: test_boundary_non_training_guarantee")


def test_boundary_audit_trail():
    """All operations generate audit entries."""
    boundary = SovereignBoundary()
    boundary.query("ep_query_design_metrics", {"components": 42})
    assert len(boundary.audit_log()) == 1
    entry = boundary.audit_log()[0]
    assert entry["entry_point"] == "ep_query_design_metrics"
    print("PASS: test_boundary_audit_trail")


def test_boundary_list_entry_points():
    """list_entry_points returns all 28 as dicts."""
    boundary = SovereignBoundary()
    entries = boundary.list_entry_points()
    assert len(entries) == 28
    assert entries[0]["name"].startswith("ep_")
    print("PASS: test_boundary_list_entry_points")


def test_boundary_verify_non_training():
    """verify_non_training returns True when policy is active."""
    boundary = SovereignBoundary()
    assert boundary.verify_non_training() is True
    print("PASS: test_boundary_verify_non_training")


def test_boundary_control_operations():
    """Control entry points work without stripping."""
    boundary = SovereignBoundary()
    result = boundary.control("ep_control_training_guard", {})
    assert result.entry_point == "ep_control_training_guard"
    print("PASS: test_boundary_control_operations")


def test_boundary_import_surfaces():
    """Import entry points strip PDK and project paths."""
    boundary = SovereignBoundary()
    data = {"lib": "/shared/pdk/lib/symbols.lib", "path": "C:\\Users\\x\\Projects\\proj\\schematic.sch"}
    result = boundary.import_data("ep_import_reference_layout", data)
    serialized = json.dumps(result.data)
    assert "[PDK_PATH_REDACTED]" in serialized or "lib" not in serialized
    print("PASS: test_boundary_import_surfaces")


if __name__ == "__main__":
    test_entry_point_count()
    test_entry_point_families()
    test_boundary_export_strips_pdk()
    test_boundary_export_strips_project_paths()
    test_boundary_export_strips_user_id()
    test_boundary_netlist_stripping()
    test_boundary_unknown_entry_point()
    test_boundary_wrong_family()
    test_boundary_network_isolation()
    test_boundary_non_training_guarantee()
    test_boundary_audit_trail()
    test_boundary_list_entry_points()
    test_boundary_verify_non_training()
    test_boundary_control_operations()
    test_boundary_import_surfaces()
    print("\nAll sovereign boundary tests passed!")
