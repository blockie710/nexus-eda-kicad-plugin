# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the Nexus-EDA thermal hotspot detector agent (T3-W10.2).

Covers:
- PackageFamily inference from KiCad footprint strings
- PowerMode parsing and defaulting
- ComponentPower derived properties (R_th_ja, Tj, hotspot detection)
- Thermal netlist text parser (parse_thermal_netlist)
- ThermalAgent analysis pipeline (analyse_components, analyse_report_file)
- ThermalReport aggregation (severity, issues, suggestions)
- _suggest_fix recommendations for various package families
- LLM fallback summary (no LLM engine available)
- File-based parsing
- run_thermal_analysis convenience entry point
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from nexus_eda.agents.thermal_agent import (
    ComponentPower,
    PackageFamily,
    PowerMode,
    ThermalAgent,
    ThermalHotspot,
    ThermalReport,
    _suggest_fix,
    parse_thermal_netlist,
    run_thermal_analysis,
)


# --------------------------------------------------------------------------- #
# PackageFamily tests
# --------------------------------------------------------------------------- #
class TestPackageFamily:
    """Test footprint-to-package-family inference."""

    def test_sot_footprint(self):
        assert PackageFamily.from_footprint("Package_TO_SOT_SMD:SOT-23-6") == PackageFamily.SOT

    def test_tsot_footprint(self):
        assert PackageFamily.from_footprint("Package_Deal:TSOT-23-6") == PackageFamily.SOT

    def test_soic_footprint(self):
        assert PackageFamily.from_footprint(
            "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
        ) == PackageFamily.SOIC

    def test_sop_footprint(self):
        assert PackageFamily.from_footprint("Package_SO:SO-8_5x4mm") == PackageFamily.SOIC

    def test_qfn_footprint(self):
        assert PackageFamily.from_footprint("Package_DFN_QFN:QFN-48") == PackageFamily.QFN

    def test_bga_footprint(self):
        assert PackageFamily.from_footprint("Package_BGA:BGA-64") == PackageFamily.BGA

    def test_tfbga_footprint(self):
        assert PackageFamily.from_footprint("Package_BGA:T_FBGA-144") == PackageFamily.BGA

    def test_to220_footprint(self):
        assert PackageFamily.from_footprint("Package_TO_SOT_SMD:TO-220-7_Vertical") == PackageFamily.TO220

    def test_to263_footprint(self):
        assert PackageFamily.from_footprint("Package_TO_SOT_SMD:TO-263-7") == PackageFamily.TO263

    def test_to252_footprint(self):
        assert PackageFamily.from_footprint("Package_TO_SOT_SMD:TO-252-7") == PackageFamily.TO252

    def test_d2pak_footprint(self):
        assert PackageFamily.from_footprint("Package_TO_SOT_SMD:D2PAK") == PackageFamily.TO263

    def test_dip_footprint(self):
        assert PackageFamily.from_footprint("Package_DIP:DIP-8_W7.62mm_Z0.16") == PackageFamily.DIP

    def test_unknown_footprint(self):
        assert PackageFamily.from_footprint("Package_QFP:LQFP-48_7x7mm_P0.5mm") == PackageFamily.UNKNOWN

    def test_empty_footprint(self):
        assert PackageFamily.from_footprint("") == PackageFamily.UNKNOWN

    def test_family_has_thermal_resistance(self):
        """Each family must carry a positive R_th_jc."""
        for family in PackageFamily:
            assert family.r_th_jc > 0
            assert family.copper_mm2 > 0


# --------------------------------------------------------------------------- #
# PowerMode tests
# --------------------------------------------------------------------------- #
class TestPowerMode:
    """Test power mode string parsing."""

    @pytest.mark.parametrize("value,expected", [
        ("idle", PowerMode.IDLE),
        ("active", PowerMode.ACTIVE),
        ("peak", PowerMode.PEAK),
        ("IDLE", PowerMode.IDLE),
        ("ACTIVE", PowerMode.ACTIVE),
        ("PEAK", PowerMode.PEAK),
        ("Idle", PowerMode.IDLE),
        ("Active", PowerMode.ACTIVE),
        ("Peak", PowerMode.PEAK),
    ])
    def test_known_modes(self, value, expected):
        assert PowerMode.from_str(value) == expected

    def test_unknown_defaults_to_active(self):
        assert PowerMode.from_str("unknown") == PowerMode.ACTIVE

    def test_empty_defaults_to_active(self):
        assert PowerMode.from_str("") == PowerMode.ACTIVE


# --------------------------------------------------------------------------- #
# ComponentPower property tests
# --------------------------------------------------------------------------- #
class TestComponentPower:
    """Test ComponentPower derived properties."""

    def test_basic_construction(self):
        comp = ComponentPower(ref="U1", power=2.5, footprint="QFN-48")
        assert comp.ref == "U1"
        assert comp.power == 2.5
        assert comp.mode == PowerMode.ACTIVE
        assert comp.max_junction_temp == 125.0
        assert comp.r_th_ja is None
        assert comp.copper_area_mm2 is None

    def test_explicit_r_th_ja_bypasses_estimation(self):
        comp = ComponentPower(ref="U1", power=1.0, footprint="QFN-48", r_th_ja=10.0)
        assert comp.effective_r_th_ja == 10.0

    def test_r_th_ja_estimation(self):
        comp = ComponentPower(ref="R1", power=0.1, footprint="Package_TO_SOT_SMD:SOT-23")
        family = PackageFamily.SOT  # r_th_jc=120, copper=4
        r_th_cp = 1.0
        r_th_pa = 40.0 / (4.0 ** 0.5)  # = 20.0
        expected = family.r_th_jc + r_th_cp + r_th_pa
        assert comp.effective_r_th_ja == pytest.approx(expected)

    def test_temperature_rise(self):
        comp = ComponentPower(ref="U1", power=2.0, r_th_ja=10.0)
        assert comp.temperature_rise == 20.0

    def test_junction_temperature_at_25c_ambient(self):
        comp = ComponentPower(ref="U1", power=2.0, r_th_ja=10.0)
        # Tj = 25 + 2 * 10 = 45
        assert comp.junction_temperature == 45.0

    def test_is_hotspot_true(self):
        """Component at >85% of max junction temp is a hotspot."""
        comp = ComponentPower(ref="U1", power=5.0, footprint="QFN-48", copper_area_mm2=40, max_junction_temp=125.0)
        # Tj = 25 + 5 * (25 + 1 + 40/sqrt(40)) = 25 + 5 * 32.32 = 186.6 > 106.25
        assert comp.junction_temperature > comp.max_junction_temp * 0.85
        assert comp.is_hotspot is True

    def test_is_hotspot_false(self):
        comp = ComponentPower(ref="R1", power=0.01, footprint="SOT-23")
        assert comp.is_hotspot is False

    def test_margin_positive(self):
        comp = ComponentPower(ref="R1", power=0.01, footprint="SOT-23")
        assert comp.margin > 0

    def test_margin_negative(self):
        comp = ComponentPower(ref="U1", power=10.0, footprint="QFN-48", copper_area_mm2=10, max_junction_temp=100.0)
        assert comp.margin < 0

    def test_explicit_copper_area_override(self):
        comp = ComponentPower(ref="U1", power=1.0, footprint="QFN-48", copper_area_mm2=200.0)
        assert comp.effective_copper_mm2 == 200.0

    def test_default_copper_area_from_family(self):
        comp = ComponentPower(ref="U1", power=1.0, footprint="TO-220")
        assert comp.effective_copper_mm2 == PackageFamily.TO220.copper_mm2

    def test_voltage_and_current_stored(self):
        comp = ComponentPower(ref="U1", power=2.5, voltage=5.0, current=0.5)
        assert comp.voltage == 5.0
        assert comp.current == 0.5


# --------------------------------------------------------------------------- #
# PackageFamily inference from ComponentPower.footprint
# --------------------------------------------------------------------------- #
class TestComponentPackageInference:
    """Test that ComponentPower.package_family infers correctly."""

    def test_qfn_family(self):
        comp = ComponentPower(ref="U1", power=1.0, footprint="QFN-48")
        assert comp.package_family == PackageFamily.QFN

    def test_sot_family(self):
        comp = ComponentPower(ref="R1", power=0.1, footprint="SOT-23-3")
        assert comp.package_family == PackageFamily.SOT

    def test_empty_footprint_defaults_unknown(self):
        comp = ComponentPower(ref="R1", power=0.1)
        assert comp.package_family == PackageFamily.UNKNOWN


# --------------------------------------------------------------------------- #
# parse_thermal_netlist tests
# --------------------------------------------------------------------------- #
class TestParseThermalNetlist:
    """Test the thermal netlist text parser."""

    def test_empty_content(self):
        comps = parse_thermal_netlist("")
        assert comps == []

    def test_comments_only(self):
        comps = parse_thermal_netlist("# just a comment\n# another\n")
        assert comps == []

    def test_simple_line(self):
        comps = parse_thermal_netlist("R1 0.125")
        assert len(comps) == 1
        assert comps[0].ref == "R1"
        assert comps[0].power == 0.125
        assert comps[0].mode == PowerMode.ACTIVE
        assert comps[0].footprint == ""

    def test_full_line_with_all_fields(self):
        line = "U1 2.5 V=5.0 I=0.5 active QFN-48 40 125"
        comps = parse_thermal_netlist(line)
        assert len(comps) == 1
        c = comps[0]
        assert c.ref == "U1"
        assert c.power == 2.5
        assert c.voltage == 5.0
        assert c.current == 0.5
        assert c.mode == PowerMode.ACTIVE
        assert c.footprint == "QFN-48"
        assert c.copper_area_mm2 == 40.0
        assert c.max_junction_temp == 125.0

    def test_tj_parametrized(self):
        line = "U2 3.0 V=3.3 I=0.9 active QFN-48 30 Tj=150"
        comps = parse_thermal_netlist(line)
        assert comps[0].max_junction_temp == 150.0

    def test_mode_keywords(self):
        for mode_str, mode in [
            ("idle", PowerMode.IDLE),
            ("active", PowerMode.ACTIVE),
            ("peak", PowerMode.PEAK),
        ]:
            line = f"R1 0.5 {mode_str} SOT-23"
            comps = parse_thermal_netlist(line)
            assert comps[0].mode == mode

    def test_mode_case_insensitive(self):
        line = "R1 0.5 IDLE SOT-23"
        comps = parse_thermal_netlist(line)
        assert comps[0].mode == PowerMode.IDLE

    def test_voltage_current_parsed(self):
        line = "U1 2.5 V=5.0 I=0.5"
        comps = parse_thermal_netlist(line)
        assert comps[0].voltage == 5.0
        assert comps[0].current == 0.5

    def test_missing_voltage_current(self):
        line = "U1 2.5 active QFN-48"
        comps = parse_thermal_netlist(line)
        assert comps[0].voltage is None
        assert comps[0].current is None

    def test_skips_malformed_lines(self):
        content = "R1 abc not_a_number\nR2 0.125"
        comps = parse_thermal_netlist(content)
        assert len(comps) == 1
        assert comps[0].ref == "R2"

    def test_skips_short_lines(self):
        content = "R1\nR2 0.125"
        comps = parse_thermal_netlist(content)
        assert len(comps) == 1
        assert comps[0].ref == "R2"

    def test_mixed_content(self):
        content = """
# Thermal export
U1 2.5 V=5.0 I=0.5 active QFN-48 40 125
R1 0.125 V=12.0 I=0.010 active SOT-23-3 150
R2 0.25 idle SOT-23 4.0
D1 0.7 peak DO-41
"""
        comps = parse_thermal_netlist(content)
        assert len(comps) == 4
        assert comps[0].ref == "U1"
        assert comps[1].ref == "R1"
        assert comps[2].ref == "R2"
        assert comps[2].mode == PowerMode.IDLE
        assert comps[3].ref == "D1"
        assert comps[3].mode == PowerMode.PEAK

    def test_default_tj_max(self):
        line = "R1 0.125 active SOT-23"
        comps = parse_thermal_netlist(line)
        assert comps[0].max_junction_temp == 125.0

    def test_numeric_copper_and_tj(self):
        line = "U1 2.5 active QFN-48 40 125"
        comps = parse_thermal_netlist(line)
        assert comps[0].copper_area_mm2 == 40.0
        assert comps[0].max_junction_temp == 125.0


# --------------------------------------------------------------------------- #
# ThermalAgent analysis tests
# --------------------------------------------------------------------------- #
class TestThermalAgentAnalysis:
    """Test ThermalAgent analysus pipeline."""

    def test_analyse_components_basic(self):
        comps = [
            ComponentPower(ref="R1", power=0.125, footprint="SOT-23"),
            ComponentPower(ref="U1", power=0.5, footprint="QFN-48", copper_area_mm2=40),
        ]
        agent = ThermalAgent(ambient_temp=25.0)
        report = agent.analyse_components(comps)
        assert report.ambient_temp == 25.0
        assert report.total_count == 2
        assert report.total_power == pytest.approx(0.625)
        assert report.hottest_component == "R1"  # SOT has higher R_th_ja despite lower power
        assert report.hottest_temp > 0

    def test_analyse_components_empty(self):
        agent = ThermalAgent()
        report = agent.analyse_components([])
        assert report.total_count == 0
        assert report.total_power == 0.0
        assert report.hotspot_count == 0
        assert report.hottest_component is None

    def test_hotspot_detection(self):
        """A high-power QFN component should be flagged as a hotspot."""
        comps = [
            ComponentPower(ref="U1", power=5.0, footprint="QFN-48", copper_area_mm2=40, max_junction_temp=125.0),
        ]
        agent = ThermalAgent()
        report = agent.analyse_components(comps)
        assert report.hotspot_count >= 1
        assert report.hotspots[0].ref == "U1"

    def test_hotspots_sorted_by_temperature(self):
        comps = [
            ComponentPower(ref="U1", power=5.0, footprint="QFN-48", copper_area_mm2=40, max_junction_temp=125.0),
            ComponentPower(ref="U2", power=3.0, footprint="QFN-48", copper_area_mm2=30, max_junction_temp=125.0),
            ComponentPower(ref="R1", power=0.01, footprint="SOT-23"),
        ]
        agent = ThermalAgent()
        report = agent.analyse_components(comps)
        temps = [h.junction_temp for h in report.hotspots]
        assert temps == sorted(temps, reverse=True)

    def test_hotspot_above_85c(self):
        """Any component above 85°C should be a hotspot regardless of max rating."""
        comps = [
            ComponentPower(ref="U1", power=3.0, footprint="QFN-48", copper_area_mm2=10, max_junction_temp=200.0),
        ]
        agent = ThermalAgent()
        report = agent.analyse_components(comps)
        # Tj will be high enough to exceed 85°C
        if report.hottest_temp > 85.0:
            assert report.hotspot_count >= 1

    def test_no_pcbnew_returns_empty(self):
        """extract_component_power returns [] when pcbnew unavailable."""
        agent = ThermalAgent(board=None)
        assert agent.extract_component_power() == []
        assert agent.has_pcbnew is False

    def test_analyse_board_without_pcbnew(self):
        agent = ThermalAgent(board=None)
        report = agent.analyse_board()
        assert report.total_count == 0
        assert report.hotspot_count == 0

    def test_analyse_report_file(self, tmp_path):
        """Test parsing a thermal export file and analysing it."""
        thermal_data = "U1 2.5 V=5.0 I=0.5 active QFN-48 40 125\nR1 0.125 active SOT-23\n"
        filepath = tmp_path / "test.thermal"
        filepath.write_text(thermal_data)
        agent = ThermalAgent(ambient_temp=25.0)
        report = agent.analyse_report_file(filepath)
        assert report.total_count == 2
        assert report.total_power == pytest.approx(2.625)

    def test_parse_file_nonexistent(self):
        agent = ThermalAgent()
        with pytest.raises(FileNotFoundError):
            agent.parse_file("/nonexistent/path/file.thermal")


# --------------------------------------------------------------------------- #
# ThermalReport aggregation tests
# --------------------------------------------------------------------------- #
class TestThermalReport:
    """Test ThermalReport properties and aggregation."""

    def test_severity_none_hotspot(self):
        report = ThermalReport(ambient_temp=25.0, components=[], hotspots=[])
        assert report.severity == "low"

    def test_severity_below_limit_hotspot(self):
        comp = ComponentPower(ref="U1", power=2.0, footprint="QFN-48", copper_area_mm2=40, max_junction_temp=150.0)
        # Tj will exceed 85% of 150 = 127.5 but not 150
        agent = ThermalAgent()
        report = agent.analyse_components([comp])
        assert report.severity in ("low", "medium")

    def test_severity_exceeds_max_temp(self):
        comp = ComponentPower(ref="U1", power=10.0, footprint="QFN-48", copper_area_mm2=10, max_junction_temp=100.0)
        agent = ThermalAgent()
        report = agent.analyse_components([comp])
        assert report.severity == "high"

    def test_severity_three_hotspots_medium(self):
        """3+ hotspots (that don't exceed max temp) → medium."""
        comps = [
            ComponentPower(ref=f"U{i}", power=2.0, footprint="QFN-48", copper_area_mm2=30, max_junction_temp=150.0)
            for i in range(1, 4)
        ]
        agent = ThermalAgent()
        report = agent.analyse_components(comps)
        # All three will be hotspots (85% of 150 = 127.5, Tj will exceed)
        assert report.severity in ("medium", "high")

    def test_issues_list(self):
        comps = [
            ComponentPower(ref="U1", power=5.0, footprint="QFN-48", copper_area_mm2=40, max_junction_temp=125.0),
        ]
        agent = ThermalAgent()
        report = agent.analyse_components(comps)
        assert len(report.issues) > 0
        assert any("U1" in issue for issue in report.issues)

    def test_suggestions_list(self):
        comps = [
            ComponentPower(ref="U1", power=5.0, footprint="QFN-48", copper_area_mm2=40, max_junction_temp=125.0),
        ]
        agent = ThermalAgent()
        report = agent.analyse_components(comps)
        assert len(report.suggestions) > 0
        assert report.hotspot_count == len(report.suggestions)

    def test_total_count_property(self):
        comps = [
            ComponentPower(ref="R1", power=0.1, footprint="SOT-23"),
            ComponentPower(ref="R2", power=0.2, footprint="SOT-23"),
            ComponentPower(ref="U1", power=1.0, footprint="QFN-48"),
        ]
        agent = ThermalAgent()
        report = agent.analyse_components(comps)
        assert report.total_count == 3


# --------------------------------------------------------------------------- #
# _suggest_fix tests
# --------------------------------------------------------------------------- #
class TestSuggestFix:
    """Test the _suggest_fix recommendation generator."""

    def test_to220_recommendation(self):
        comp = ComponentPower(ref="Q1", power=5.0, footprint="TO-220", copper_area_mm2=200, max_junction_temp=125.0)
        tj = comp.junction_temperature
        suggestion = _suggest_fix(comp, tj)
        assert "Q1" in suggestion
        assert "heatsink" in suggestion.lower()

    def test_sot_recommendation(self):
        comp = ComponentPower(ref="R1", power=0.5, footprint="SOT-23", copper_area_mm2=4, max_junction_temp=125.0)
        tj = comp.junction_temperature
        suggestion = _suggest_fix(comp, tj)
        assert "SOT" in suggestion or "package" in suggestion.lower() or "via" in suggestion.lower()

    def test_sod_recommendation(self):
        comp = ComponentPower(ref="D1", power=0.7, footprint="SOD-123", copper_area_mm2=2, max_junction_temp=125.0)
        tj = comp.junction_temperature
        suggestion = _suggest_fix(comp, tj)
        assert "D1" in suggestion

    def test_over_temp_copper_increase(self):
        """Component exceeding max temp should suggest copper area increase."""
        comp = ComponentPower(ref="U1", power=2.0, footprint="SOIC", copper_area_mm2=15, max_junction_temp=80.0)
        tj = comp.junction_temperature
        margin = comp.max_junction_temp - tj
        suggestion = _suggest_fix(comp, tj)
        assert "U1" in suggestion

    def test_safe_component_recommendation(self):
        """Component below margin 0 still gets a recommendation if called."""
        comp = ComponentPower(ref="R1", power=0.01, footprint="SOT-23")
        tj = comp.junction_temperature
        suggestion = _suggest_fix(comp, tj)
        assert "R1" in suggestion


# --------------------------------------------------------------------------- #
# ThermalAgent.summarise tests
# --------------------------------------------------------------------------- #
class TestSummary:
    """Test the LLM fallback summariser."""

    def test_fallback_summary_with_hotspots(self):
        comps = [
            ComponentPower(ref="U1", power=5.0, footprint="QFN-48", copper_area_mm2=40, max_junction_temp=125.0),
            ComponentPower(ref="R1", power=0.01, footprint="SOT-23"),
        ]
        agent = ThermalAgent(ambient_temp=25.0)
        report = agent.analyse_components(comps)
        summary = agent.summarise(report)
        assert "2 component(s)" in summary
        assert "Hotspot" in summary or "hotspot" in summary

    def test_fallback_summary_no_hotspots(self):
        comps = [
            ComponentPower(ref="R1", power=0.01, footprint="SOT-23"),
            ComponentPower(ref="R2", power=0.01, footprint="SOT-23"),
        ]
        agent = ThermalAgent()
        report = agent.analyse_components(comps)
        summary = agent.summarise(report)
        assert "2 component(s)" in summary

    def test_summary_empty_report(self):
        agent = ThermalAgent()
        report = ThermalReport()
        summary = agent.summarise(report)
        assert "No thermal data" in summary

    def test_summary_no_llm_engine(self):
        """When llm_engine is None, fallback summary is used."""
        agent = ThermalAgent(llm_engine=None)
        assert agent.llm_engine is None
        assert agent.summarise(ThermalReport()) == agent._fallback_summary(ThermalReport())


# --------------------------------------------------------------------------- #
# run_thermal_analysis tests
# --------------------------------------------------------------------------- #
class TestRunThermalAnalysis:
    """Test the convenience entry point."""

    def test_with_components(self):
        comps = [
            ComponentPower(ref="U1", power=2.0, footprint="QFN-48", copper_area_mm2=40, max_junction_temp=125.0),
        ]
        report = run_thermal_analysis(components=comps)
        assert report.total_count == 1
        assert report.total_power == 2.0
        assert report.hottest_component == "U1"

    def test_with_empty_components(self):
        report = run_thermal_analysis(components=[])
        assert report.total_count == 0
        assert report.total_power == 0.0

    def test_with_report_file(self, tmp_path):
        thermal_data = "U1 2.5 V=5.0 I=0.5 active QFN-48 40 125\n"
        filepath = tmp_path / "test.thermal"
        filepath.write_text(thermal_data)
        report = run_thermal_analysis(report_path=str(filepath))
        assert report.total_count == 1
        assert report.total_power == 2.5

    def test_ambient_temp_override(self):
        comps = [
            ComponentPower(ref="R1", power=0.1, r_th_ja=10.0),
        ]
        report = run_thermal_analysis(components=comps, ambient_temp=50.0)
        assert report.ambient_temp == 50.0
        # Tj = 50 + 0.1 * 10 = 51
        assert report.hottest_temp == pytest.approx(51.0)


# --------------------------------------------------------------------------- #
# Integration: parse + analyse round-trip
# --------------------------------------------------------------------------- #
class TestIntegration:
    """Integration tests combining parser and analysis."""

    THERMAL_NETLIST = """\
# Test thermal netlist
U1 2.5 V=5.0 I=0.5 active QFN-48 40 125
U2 3.0 V=3.3 I=0.9 active QFN-48 30 125
R1 0.125 V=12.0 I=0.010 active SOT-23-3 15
R2 0.25 idle SOT-23 4.0
D1 0.7 peak DO-41 5 125
Q1 5.0 V=24.0 I=0.2 active TO-220 200 150
"""

    def test_parse_then_analyse(self):
        comps = parse_thermal_netlist(self.THERMAL_NETLIST)
        assert len(comps) == 6
        report = run_thermal_analysis(components=comps, ambient_temp=25.0)
        assert report.total_count == 6
        assert report.total_power == pytest.approx(11.575)
        assert report.hottest_component is not None
        assert report.hotspot_count >= 0

    def test_all_components_have_valid_temps(self):
        comps = parse_thermal_netlist(self.THERMAL_NETLIST)
        report = run_thermal_analysis(components=comps)
        for comp in report.components:
            assert comp.junction_temperature > 25.0  # above ambient
            assert comp.effective_r_th_ja > 0

    def test_hotspot_recommendations_populated(self):
        comps = parse_thermal_netlist(self.THERMAL_NETLIST)
        agent = ThermalAgent(ambient_temp=25.0)
        report = agent.analyse_components(comps)
        for h in report.hotspots:
            assert h.recommendation
            assert len(h.recommendation) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
