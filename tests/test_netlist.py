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
      (node (ref R1) (pin 2)))
  )
)
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


def test_parse_multi_component_netlist():
    """Test parsing a netlist with multiple components (regression for
    the (comp vs (components matching bug).

    The parser must find (comp followed by whitespace, not (comp at the
    start of (components, so that all individual components are parsed
    rather than the entire (components ...) block being consumed as one.
    """
    content = """(kicad_netlist (version 20211014)
  (components
    (comp (ref R1)
      (field Value 10k)
      (field Footprint Resistor_SMD:R_0805))
    (comp (ref C1)
      (field Value 0.1uF)
      (field Footprint Capacitor_SMD:C_0603))
    (comp (ref U1)
      (field Value ATmega328P)
      (field Footprint Package_DIP:DIP-28_W7.62mm)))
  (nets
    (net (code 1) (name "GND")
      (node (ref R1) (pin 2))
      (node (ref C1) (pin 2))
      (node (ref U1) (pin 22)))
  )
)
"""
    path = _write_temp(content)
    try:
        data = parse_netlist(path)
        assert len(data.components) == 3
        assert set(data.components.keys()) == {"R1", "C1", "U1"}
        assert data.components["R1"]["Value"] == "10k"
        assert data.components["C1"]["Value"] == "0.1uF"
        assert data.components["U1"]["Value"] == "ATmega328P"
        assert data.components["U1"]["Footprint"] == "Package_DIP:DIP-28_W7.62mm"
        print("PASS: test_parse_multi_component_netlist")
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
      (node (ref R1) (pin 3)))
  )
)
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


def test_parse_test_netlist_file():
    """Test parsing the bundled test_netlist.net fixture file."""
    fixture = os.path.join(
        os.path.dirname(__file__), '..', 'test_netlist.net'
    )
    data = parse_netlist(fixture)
    assert isinstance(data, NetlistData)
    assert data.version == "20211014"
    # Must find all 3 components, not just 1 (regression for (comp vs (components)
    assert len(data.components) == 3
    assert set(data.components.keys()) == {"R1", "C1", "U1"}
    # R1 is a resistor, not the MCU — fields must belong to the correct ref
    assert data.components["R1"]["Value"] == "10k"
    assert data.components["R1"]["Footprint"] == "Resistor_SMD:R_0805"
    assert data.components["C1"]["Value"] == "0.1uF"
    assert data.components["U1"]["Value"] == "ATmega328P"
    # 6 nets total
    assert len(data.nets) == 6
    assert data.nets["GND"] == ["R1/2", "C1/2", "U1/22"]
    assert data.nets["VCC"] == ["R1/1", "C1/1", "U1/7", "U1/20", "U1/AVCC"]
    # DRC: FLOATING, SCK, MOSI, MISO each have only 1 node → 4 warnings
    violations = validate_netlist(data)
    net_isolation = [v for v in violations if v.rule_id == "NET_ISOLATION"]
    assert len(net_isolation) == 4
    print("PASS: test_parse_test_netlist_file")


if __name__ == "__main__":
    test_parse_empty_netlist()
    test_parse_simple_netlist()
    test_parse_multi_component_netlist()
    test_validate_netlist()
    test_parse_test_netlist_file()
    print("All tests passed!")
