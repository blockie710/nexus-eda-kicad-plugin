# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the Nexus-EDA DRC agent (Phase 2 — T2-W5.2).

Covers:
- parse_drc_report: parsing pcbnew DRC report text into structured violations
- DRCAgent in stub mode (no pcbnew): graceful fallback + report file parsing
- DRCReport data structure (counts, severity, issues, suggestions)
- Severity enum and mm_to_du conversion helper
- DRC prompt template rendering
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from nexus_eda.agents.drc_agent import (
    DRCReport,
    DRCViolation,
    DRCAgent,
    Severity,
    parse_drc_report,
    run_drc,
    mm_to_du,
    _guess_rule_id,
    _extract_component,
    _extract_net,
)


# ----------------------------------------------------------------------- #
# Fixtures
# ----------------------------------------------------------------------- #
FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_drc_text():
    """A representative pcbnew DRC report text with 5 violations."""
    return (
        "DRC report (severity 2 = error, 1 = warning, 0 = info)\n"
        "Options:\n"
        "  Minimum clearance: 0.15 mm\n"
        "  Check unrouted: yes\n"
        "  Check placement: yes\n"
        "\n"
        "************ Results **************\n"
        "\n"
        "#0 (error) Clearance - Pad U1-7 to Pad C1-1 on net 'VCC'\n"
        "    Clearance is 0.10 mm, minimum is 0.15 mm\n"
        "    Pad U1 pin 7 at (X=10.2mm, Y=15.3mm)\n"
        "    Pad C1 pin 1 at (X=10.3mm, Y=15.3mm)\n"
        "\n"
        "#1 (warning) Unconnected - Pin U1-19 on net 'SCK' is not connected\n"
        "    Component U1 pin 19\n"
        "    Net name: 'SCK'\n"
        "\n"
        "#2 (error) Minimum trace width - Trace on net 'GND' is 0.08 mm, minimum is 0.15 mm\n"
        "    Segment from (X=5.1mm, Y=8.2mm) to (X=6.5mm, Y=8.2mm)\n"
        "\n"
        "#3 (info) Solder paste - SMD pad R1-1 has no paste layer\n"
        "    Component R1, pad 1\n"
        "\n"
        "#4 (warning) Pad outline - Pad R1-1 is outside of its component courtyard\n"
        "    Component R1, pad 1\n"
        "\n"
        "************ End ************\n"
    )


@pytest.fixture
def empty_drc_text():
    """A DRC report with no violations."""
    return (
        "DRC report\n"
        "Options:\n"
        "  Minimum clearance: 0.15 mm\n"
        "\n"
        "************ Results **************\n"
        "\n"
        "No problems found\n"
        "\n"
        "************ End ************\n"
    )


# ----------------------------------------------------------------------- #
# parse_drc_report tests
# ----------------------------------------------------------------------- #
class TestParseDRCReport:
    """Tests for the DRC report text parser."""

    def test_parses_all_violations(self, sample_drc_text):
        """Parser should find all 5 violations in the sample report."""
        report = parse_drc_report(sample_drc_text)
        assert report.total_count == 5
        assert report.error_count == 2
        assert report.warning_count == 2
        assert report.info_count == 1

    def test_severity_classification(self, sample_drc_text):
        """Error-level severity should be 'high' when errors exist."""
        report = parse_drc_report(sample_drc_text)
        assert report.severity == "high"

    def test_violation_fields(self, sample_drc_text):
        """Each violation should have parsed fields populated."""
        report = parse_drc_report(sample_drc_text)
        v0 = report.violations[0]
        assert v0.severity == Severity.ERROR
        assert v0.rule_id == "MIN_CLEARANCE"
        assert v0.net == "VCC"
        assert "Clearance" in v0.description

    def test_component_extraction(self, sample_drc_text):
        """Component refs like U1-7, C1-1 should be extracted."""
        report = parse_drc_report(sample_drc_text)
        assert report.violations[0].component == "U1-7"
        assert report.violations[1].component == "U1-19"
        assert report.violations[3].component == "R1-1"

    def test_net_extraction(self, sample_drc_text):
        """Net names from 'net 'VCC'' and 'net 'SCK'' should be extracted."""
        report = parse_drc_report(sample_drc_text)
        assert report.violations[0].net == "VCC"
        assert report.violations[1].net == "SCK"
        assert report.violations[2].net == "GND"

    def test_rule_id_classification(self, sample_drc_text):
        """Rule IDs should be classified correctly by keyword."""
        report = parse_drc_report(sample_drc_text)
        rule_ids = [v.rule_id for v in report.violations]
        assert "MIN_CLEARANCE" in rule_ids
        assert "UNROUTED_DRC" in rule_ids
        assert "MIN_TRACE" in rule_ids
        assert "SOLDER_PASTE_DRC" in rule_ids
        assert "PASTE_COURTYARD_DRC" in rule_ids

    def test_empty_report(self, empty_drc_text):
        """Empty DRC report should produce zero violations."""
        report = parse_drc_report(empty_drc_text)
        assert report.total_count == 0
        assert report.error_count == 0
        assert report.warning_count == 0
        assert report.info_count == 0

    def test_empty_report_severity(self, empty_drc_text):
        """Empty report should have 'low' severity."""
        report = parse_drc_report(empty_drc_text)
        assert report.severity == "low"

    def test_continuation_lines_merged(self, sample_drc_text):
        """Multi-line violation details should be merged into description."""
        report = parse_drc_report(sample_drc_text)
        v0 = report.violations[0]
        assert "0.10 mm" in v0.description
        assert "Pad U1 pin 7" in v0.description

    def test_issues_property(self, sample_drc_text):
        """issues property should return list of descriptions."""
        report = parse_drc_report(sample_drc_text)
        assert len(report.issues) == 5
        assert all(isinstance(issue, str) for issue in report.issues)

    def test_suggestions_property(self, sample_drc_text):
        """suggestions property should return actionable fix strings."""
        report = parse_drc_report(sample_drc_text)
        assert len(report.suggestions) == 5
        assert any("clearance" in s.lower() for s in report.suggestions)

    def test_fixture_file_parsing(self):
        """Parse the committed fixture DRC report file."""
        fixture_path = FIXTURE_DIR / "sample_drc_report.txt"
        assert fixture_path.exists(), f"Fixture file missing: {fixture_path}"
        report = parse_drc_report(fixture_path.read_text(encoding="utf-8"))
        assert report.total_count == 5
        assert report.error_count == 2


# ----------------------------------------------------------------------- #
# DRCReport data structure tests
# ----------------------------------------------------------------------- #
class TestDRCReport:
    """Tests for the DRCReport dataclass."""

    def test_empty_report_defaults(self):
        """An empty DRCReport should have all-zero counts."""
        report = DRCReport()
        assert report.total_count == 0
        assert report.error_count == 0
        assert report.warning_count == 0
        assert report.info_count == 0
        assert report.violations == []

    def test_add_violation_updates_counts(self):
        """Adding a violation should increment the correct counter."""
        report = DRCReport()
        v = DRCViolation(
            rule_id="TEST",
            description="test violation",
            severity=Severity.WARNING,
        )
        report.add(v)
        assert report.total_count == 1
        assert report.warning_count == 1
        assert report.error_count == 0

    def test_severity_low(self):
        """Only warnings should yield 'low' severity."""
        report = DRCReport()
        report.add(DRCViolation("T", "w", Severity.WARNING))
        assert report.severity == "low"

    def test_severity_medium(self):
        """6+ warnings should yield 'medium' severity."""
        report = DRCReport()
        for _ in range(6):
            report.add(DRCViolation("T", "w", Severity.WARNING))
        assert report.severity == "medium"

    def test_severity_high(self):
        """Any error should yield 'high' severity."""
        report = DRCReport()
        report.add(DRCViolation("T", "w", Severity.WARNING))
        report.add(DRCViolation("T", "e", Severity.ERROR))
        assert report.severity == "high"


# ----------------------------------------------------------------------- #
# Severity enum tests
# ----------------------------------------------------------------------- #
class TestSeverityEnum:
    """Tests for the Severity enum."""

    def test_enum_values(self):
        assert Severity.ERROR.value == "error"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"

    def test_from_pcbnew_numeric(self):
        """pcbnew severity codes: 0=info, 1=warning, 2=error."""
        assert Severity.from_pcbnew(0) == Severity.INFO
        assert Severity.from_pcbnew(1) == Severity.WARNING
        assert Severity.from_pcbnew(2) == Severity.ERROR

    def test_from_pcbnew_string(self):
        assert Severity.from_pcbnew("0") == Severity.INFO
        assert Severity.from_pcbnew("1") == Severity.WARNING
        assert Severity.from_pcbnew("2") == Severity.ERROR

    def test_from_pcbnew_unknown(self):
        """Unknown code should default to WARNING."""
        assert Severity.from_pcbnew(99) == Severity.WARNING
        assert Severity.from_pcbnew("foo") == Severity.WARNING


# ----------------------------------------------------------------------- #
# DRCAgent stub-mode tests (no pcbnew available)
# ----------------------------------------------------------------------- #
class TestDRCAgentStub:
    """Tests for DRCAgent when pcbnew is not available (CI/headless)."""

    def test_has_pcbnew_is_false_without_kicad(self):
        """Without pcbnew import, has_pcbnew should be True only if board present."""
        agent = DRCAgent(board=None)
        # pcbnew may or may not be importable in CI; if not, has_pcbnew is False
        # If pcbnew IS available but board is None, has_pcbnew is still False
        assert agent.has_pcbnew is False

    def test_run_drc_fallback_without_pcbnew(self):
        """Without pcbnew, run_pcbnew_drc should return a graceful empty report."""
        agent = DRCAgent(board=None)
        report = agent.run_pcbnew_drc()
        assert report.total_count == 0
        assert report.summary is not None
        assert "pcbnew" in report.summary.lower()

    def test_run_drc_with_report_path(self, tmp_path):
        """parse_report_file should parse a fixture report file."""
        fixture = FIXTURE_DIR / "sample_drc_report.txt"
        agent = DRCAgent(board=None)
        report = agent.parse_report_file(fixture)
        assert report.total_count == 5
        assert report.error_count == 2

    def test_run_drc_file_not_found(self, tmp_path):
        """parse_report_file should raise FileNotFoundError for missing file."""
        agent = DRCAgent(board=None)
        with pytest.raises(FileNotFoundError):
            agent.parse_report_file(tmp_path / "nonexistent.drc")

    def test_summarise_without_llm_fallback(self, sample_drc_text):
        """summarise without an LLM engine should use the text fallback."""
        report = parse_drc_report(sample_drc_text)
        agent = DRCAgent(board=None, llm_engine=None)
        summary = agent.summarise(report)
        assert "5" in summary  # total count
        assert "error" in summary.lower() or "Errors" in summary

    def test_summarise_empty_report(self):
        """summarise on an empty report should say no violations."""
        report = DRCReport()
        agent = DRCAgent(board=None)
        summary = agent.summarise(report)
        assert "No DRC violations" in summary


# ----------------------------------------------------------------------- #
# run_drc convenience function tests
# ----------------------------------------------------------------------- #
class TestRunDRC:
    """Tests for the run_drc convenience function."""

    def test_run_drc_with_report_path(self):
        """run_drc with report_path should parse the file and return violations."""
        fixture = FIXTURE_DIR / "sample_drc_report.txt"
        report = run_drc(report_path=str(fixture))
        assert report.total_count == 5
        assert report.error_count == 2

    def test_run_drc_without_pcbnew_no_path(self):
        """run_drc without pcbnew or report_path should return empty + note."""
        report = run_drc()
        assert report.total_count == 0
        assert report.summary is not None
        assert "pcbnew" in report.summary.lower()


# ----------------------------------------------------------------------- #
# Helper function tests
# ----------------------------------------------------------------------- #
class TestHelpers:
    """Tests for internal helper functions."""

    def test_guess_rule_id_clearance(self):
        assert _guess_rule_id("Clearance between pads") == "MIN_CLEARANCE"

    def test_guess_rule_id_unrouted(self):
        assert _guess_rule_id("Unconnected pin") == "UNROUTED_DRC"

    def test_guess_rule_id_trace_width(self):
        assert _guess_rule_id("Minimum trace width") == "MIN_TRACE"

    def test_guess_rule_id_zone(self):
        assert _guess_rule_id("Zone fill issue") == "ZONE_DRC"

    def test_guess_rule_id_solder_paste(self):
        assert _guess_rule_id("Solder paste missing") == "SOLDER_PASTE_DRC"

    def test_guess_rule_id_short(self):
        assert _guess_rule_id("Short between nets") == "SHORT_DRC"

    def test_guess_rule_id_generic(self):
        assert _guess_rule_id("Something unexpected") == "GENERIC_DRC"

    def test_extract_component_standard(self):
        assert _extract_component("Pad U1-7 to Pad C1-1") == "U1-7"

    def test_extract_component_solder_paste(self):
        assert _extract_component("SMD pad R1-1 has no paste") == "R1-1"

    def test_extract_component_none(self):
        assert _extract_component("no components here") is None

    def test_extract_net_quoted(self):
        assert _extract_net("on net 'VCC'") == "VCC"

    def test_extract_net_name_prefix(self):
        assert _extract_net("Net name: 'SCK'") == "SCK"

    def test_extract_net_none(self):
        assert _extract_net("no net here") is None

    def test_mm_to_du_without_pcbnew(self):
        """mm_to_du should work without pcbnew (fallback to 1e6 multiplier)."""
        # With pcbnew, the conversion may use IUTIL_Mm2iu; without it, 1e6
        result = mm_to_du(0.15)
        assert result == 150000  # 0.15 * 1e6


# ----------------------------------------------------------------------- #
# DRC prompt template tests
# ----------------------------------------------------------------------- #
class TestDRCPrompt:
    """Tests for the DRC analysis prompt template."""

    def test_drc_analysis_prompt_rendered(self):
        """drc_analysis_prompt should produce a valid prompt string."""
        from nexus_eda.llm.prompts import drc_analysis_prompt, DRC_ANALYSIS_PROMPT

        violations_text = "#1 (error) Clearance - Pad U1-7 to Pad C1-1\n"
        prompt = drc_analysis_prompt(violations_text, total=1)
        assert "VIOLATIONS:" in prompt
        assert "Clearance" in prompt
        assert "JSON object" in prompt
        assert "ANALYSIS:" in prompt

    def test_drc_analysis_prompt_has_all_keys(self):
        """The prompt template should mention all required JSON keys."""
        from nexus_eda.llm.prompts import DRC_ANALYSIS_PROMPT

        assert "summary" in DRC_ANALYSIS_PROMPT
        assert "severity" in DRC_ANALYSIS_PROMPT
        assert "issues" in DRC_ANALYSIS_PROMPT
        assert "suggestions" in DRC_ANALYSIS_PROMPT


# ----------------------------------------------------------------------- #
# DRCViolation dataclass tests
# ----------------------------------------------------------------------- #
class TestDRCViolation:
    """Tests for the DRCViolation dataclass."""

    def test_defaults(self):
        """DRCViolation should have sensible defaults for optional fields."""
        v = DRCViolation(
            rule_id="TEST",
            description="test",
            severity=Severity.WARNING,
        )
        assert v.component is None
        assert v.net is None
        assert v.x is None
        assert v.y is None
        assert v.details is None

    def test_full_construction(self):
        v = DRCViolation(
            rule_id="MIN_CLEARANCE",
            description="Clearance too small",
            severity=Severity.ERROR,
            component="U1-7",
            net="VCC",
            x=10.2,
            y=15.3,
            details="0.10 mm < 0.15 mm",
        )
        assert v.rule_id == "MIN_CLEARANCE"
        assert v.severity == Severity.ERROR
        assert v.component == "U1-7"
        assert v.net == "VCC"
        assert v.x == 10.2
        assert v.y == 15.3

    def test_recalculate_on_init(self):
        """_recalculate_counts should run on __post_init__."""
        report = DRCReport(violations=[
            DRCViolation("A", "a", Severity.ERROR),
            DRCViolation("B", "b", Severity.WARNING),
            DRCViolation("C", "c", Severity.INFO),
        ])
        assert report.total_count == 3
        assert report.error_count == 1
        assert report.warning_count == 1
        assert report.info_count == 1
