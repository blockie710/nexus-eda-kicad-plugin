# SPDX-License-Identifier: Apache-2.0
"""Unit tests for Nexus-EDA agents."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest

from nexus_eda.agents import analyze_netlist, optimize_bom, suggest_routing


def test_analyze_netlist_stub():
    """Phase 1: Stub returns expected default structure."""
    # board = pcbnew.GetBoard()  # Requires KiCad runtime
    # For now, test the data contract
    result = analyze_netlist(None)
    assert result.unrouted_count == 0
    assert result.total_nets == 0
    assert result.severity in ("low", "medium", "high")
    assert isinstance(result.issues, list)
    assert isinstance(result.suggestions, list)


def test_optimize_bom_stub():
    """Phase 1: Stub returns expected default structure."""
    result = optimize_bom(None)
    assert result.total_savings == 0.0
    assert isinstance(result.replaced_parts, list)
    assert isinstance(result.warnings, list)


def test_suggest_routing_stub():
    """Phase 1: Stub returns expected default structure."""
    result = suggest_routing(None)
    assert isinstance(result.path_description, str)
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.violations, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
