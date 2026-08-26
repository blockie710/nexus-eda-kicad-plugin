# SPDX-License-Identifier: Apache-2.0
"""Tests for the netlist parser."""

import os
import sys
import tempfile

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from nexus_eda.netlist import parse_netlist, validate_netlist, NetlistData


def _write_temp(content: str) -> str:
    """Write content to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix='.net')
    with os.fdopen(fd, 'w') as f:
        f.write(content)
    return path


def test_parse_empty_netlist():
    """Test parsing an empty netlist."""
    content = "(kicad_netlist (version 20211014) (components) (nets))"
    path = _write_temp(content)
    try:
        data = parse_netlist(path)
        assert isinstance(data, NetlistData)
        assert data.version == "20211014"
        assert data.components == {}
        assert data.nets == {}
        print("PASS: test_parse_empty_netlist")
    finally:
        os.unlink(path)


def test_parse_simple_netlist():
    """Test parsing a simple netlist with one component and one net."""
    content = """(kicad_netlist (version 20211014)
  (components
    (comp (ref R1)
      (field Value 10k)
      (field Footprint Resistor_SMD:R_0805)))
  (nets
    (net (code 1) (name "NET_R1")
      (node (ref R1) (pin 1))
      (node (ref R1) (pin 2)))))
"""
    path = _write_temp(content)
    try:
        data = parse_netlist(path)
        assert isinstance(data, NetlistData)
        assert data.version == "20211014"
        assert "R1" in data.components
        assert data.components["R1"]["Value"] == "10k"
        assert data.components["R1"]["Footprint"] == "Resistor_SMD:R_0805"
        assert "NET_R1" in data.nets
        assert data.nets["NET_R1"] == ["R1/1", "R1/2"]
        print("PASS: test_parse_simple_netlist")
    finally:
        os.unlink(path)


def test_validate_netlist():
    """Test validation of a netlist."""
    content = """(kicad_netlist (version 20211014)
  (components
    (comp (ref R1)
      (field Value 10k)
      (field Footprint Resistor_SMD:R_0805)))
  (nets
    (net (code 1) (name "GND")
      (node (ref R1) (pin 1))
      (node (ref R1) (pin 2)))
    (net (code 2) (name "FLOAT")
      (node (ref R1) (pin 3))))]
"""
    path = _write_temp(content)
    try:
        data = parse_netlist(path)
        violations = validate_netlist(data)
        assert len(violations) == 1
        assert violations[0].rule_id == "NET_ISOLATION"
        assert violations[0].net == "FLOAT"
        assert violations[0].severity == "warning"
        print("PASS: test_validate_netlist")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    test_parse_empty_netlist()
    test_parse_simple_netlist()
    test_validate_netlist()
    print("All tests passed!")