# SPDX-License-Identifier: Apache-2.0
"""DRC (Design Rule Check) agent for Nexus-EDA.

Integrates with KiCad's ``pcbnew`` DRC engine to run design-rule checks
on the current board, parse violations, and (optionally) feed the
violation report into the local LLM for a plain-English summary.

When ``pcbnew`` is not importable (e.g. running outside the KiCad host
or in CI), the agent falls back to parsing a pcbnew DRC report file
(``.drc`` / DRC report text format) that was produced by a prior KiCad
session.  This keeps the agent fully testable in headless environments
while still leveraging the real pcbnew DRC engine when available.

Key classes
-----------
- :class:`DRCViolation`  — structured representation of a single DRC violation.
- :class:`DRCReport`      — container for a batch of violations with metadata.
- :class:`DRCAgent`       — high-level orchestrator that can run pcbnew DRC
                            or parse a report file, then summarise via LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# --------------------------------------------------------------------------- #
# pcbnew compatibility shim
# --------------------------------------------------------------------------- #
try:
    import pcbnew  # type: ignore[import-not-found]
    _HAS_PCBNEW = True
except ImportError:  # pragma: no cover - environment dependent
    pcbnew = None  # type: ignore[assignment]
    _HAS_PCBNEW = False


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
class Severity(Enum):
    """DRC violation severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @classmethod
    def from_pcbnew(cls, code: int | str) -> "Severity":
        """Map pcbnew severity code to :class:`Severity`.

        pcbnew uses numeric codes where 0 = info, 1 = warning, 2 = error.
        """
        mapping = {0: cls.INFO, 1: cls.WARNING, 2: cls.ERROR}
        if isinstance(code, str):
            if code.isdigit():
                code = int(code)
            else:
                # Non-numeric string: unknown severity, default to WARNING
                return cls.WARNING
        return mapping.get(code, cls.WARNING)


@dataclass
class DRCViolation:
    """A single DRC violation.

    Attributes:
        rule_id: Short identifier for the rule violated (e.g. ``MIN_TRACE``).
        description: Human-readable description of the violation.
        severity: One of :class:`Severity` values.
        component: Reference designator of the offending component, if known.
        net: Net name involved, if known.
        x, y: Position on the board (in mm) where the violation was detected.
        details: Free-form additional context from pcbnew.
    """

    rule_id: str
    description: str
    severity: Severity
    component: Optional[str] = None
    net: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    details: Optional[str] = None


@dataclass
class DRCReport:
    """Aggregated DRC result for a single board analysis run.

    Attributes:
        violations: List of :class:`DRCViolation` objects.
        total_count: Total number of violations found.
        error_count: Number of error-severity violations.
        warning_count: Number of warning-severity violations.
        info_count: Number of info-severity violations.
        summary: Optional plain-text or LLM-generated summary.
    """

    violations: list[DRCViolation] = field(default_factory=list)
    total_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    summary: Optional[str] = None

    def __post_init__(self) -> None:
        self._recalculate_counts()

    def _recalculate_counts(self) -> None:
        self.total_count = len(self.violations)
        self.error_count = sum(1 for v in self.violations if v.severity == Severity.ERROR)
        self.warning_count = sum(1 for v in self.violations if v.severity == Severity.WARNING)
        self.info_count = sum(1 for v in self.violations if v.severity == Severity.INFO)

    def add(self, violation: DRCViolation) -> None:
        """Add a violation and refresh counters."""
        self.violations.append(violation)
        self._recalculate_counts()

    @property
    def severity(self) -> str:
        """Overall severity: ``'low'``, ``'medium'``, or ``'high'``."""
        if self.error_count > 0:
            return "high"
        if self.warning_count > 5:
            return "medium"
        if self.warning_count > 0:
            return "low"
        return "low"

    @property
    def issues(self) -> list[str]:
        """List of human-readable violation descriptions."""
        return [v.description for v in self.violations]

    @property
    def suggestions(self) -> list[str]:
        """List of suggested fixes derived from violation types."""
        return [_suggestion_for(v) for v in self.violations if v.rule_id]


def _suggestion_for(violation: DRCViolation) -> str:
    """Generate a simple suggestion string for a DRC violation."""
    rule = violation.rule_id
    if rule == "MIN_TRACE":
        return f"Increase trace width on net '{violation.net}' to meet minimum {violation.details or 'design rule'}."
    if rule == "MIN_CLEARANCE":
        return f"Increase clearance between {violation.component or 'components'} to meet minimum spacing."
    if rule == "UNROUTED_DRC":
        return f"Complete routing on net '{violation.net}' — {violation.description}."
    if rule == "ZONE_DRC":
        return f"Adjust copper zone: {violation.description}."
    if rule == "SMD_HOLE":
        return f"Remove non-plated hole from SMD pad {violation.component}."
    return f"Review {rule}: {violation.description}."


# --------------------------------------------------------------------------- #
# DRC report file parser (text format that pcbnew exports)
# --------------------------------------------------------------------------- #
# Pcbnew DRC report text format example:
#
# DRC report (options...)
#
# ************ Results **************
#
# #1  (error)  Clearance: 0.15mm between (...)
# #2  (warning) Pad ...
# ...
#
# ************ End ************

_DRC_LINE_RE = re.compile(
    r"^(?P<num>#\d+)\s*"           # violation number, e.g. "#1"
    r"\((?P<sev>error|warning|info)\)\s*"  # severity in parentheses
    r"(?P<rule>.+?)\s*"            # rule / description up to dash
    r"-\s*"                        # separator dash
    r"(?P<detail>.*)$",           # remaining detail
)


class DRCParseError(Exception):
    """Raised when a DRC report file cannot be parsed."""


def parse_drc_report(content: str) -> DRCReport:
    """Parse pcbnew DRC report text into a :class:`DRCReport`.

    Args:
        content: Raw text of a pcbnew DRC report (as written to ``*.cmp``
            or the DRC dialog ``Save`` output, or the ``.drc`` file).

    Returns:
        A :class:`DRCReport` populated with parsed violations.
    """

    report = DRCReport()
    current_violation: Optional[dict[str, Any]] = None

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue

        # Skip footer/header separator lines
        if line.startswith("***") or line.startswith("DRC report") or line.startswith("Options:") or line.startswith("  "):
            continue

        # Match numbered violation lines like "#1  (error)  Clearance - ..."
        match = _DRC_LINE_RE.match(line)
        if match:
            # Flush previous violation
            if current_violation:
                _flush_violation(report, current_violation)

            sev_str = match.group("sev").lower()
            severity = (
                Severity.ERROR if sev_str == "error"
                else Severity.WARNING if sev_str == "warning"
                else Severity.INFO
            )
            rule_text = match.group("rule").strip()
            detail = match.group("detail").strip()

            current_violation = {
                "rule_id": _guess_rule_id(rule_text),
                "description": f"{rule_text} — {detail}" if detail else rule_text,
                "severity": severity,
                "component": _extract_component(text=rule_text + " " + detail),
                "net": _extract_net(detail),
                "details": detail,
            }
        elif current_violation is not None and not line.startswith("****"):
            # Continuation lines (e.g. pad/stackup info)
            current_violation["description"] += f" {line}"
            if current_violation["details"]:
                current_violation["details"] += f" {line}"

    # Flush the last violation
    if current_violation:
        _flush_violation(report, current_violation)

    return report


def _flush_violation(report: DRCReport, data: dict[str, Any]) -> None:
    """Create a DRCViolation from a parsed dict and add it to the report."""
    violation = DRCViolation(
        rule_id=data["rule_id"],
        description=data["description"].strip(),
        severity=data["severity"],
        component=data.get("component"),
        net=data.get("net"),
        details=data.get("details"),
    )
    report.add(violation)


def _guess_rule_id(text: str) -> str:
    """Guess a short rule ID from the pcbnew violation description text."""
    text_lower = text.lower()
    if "clearance" in text_lower:
        return "MIN_CLEARANCE"
    if "unrouted" in text_lower or "not routed" in text_lower:
        return "UNROUTED_DRC"
    if "unconnected" in text_lower or "un-connected" in text_lower:
        return "UNROUTED_DRC"
    if "trace" in text_lower and "width" in text_lower:
        return "MIN_TRACE"
    if "zone" in text_lower:
        return "ZONE_DRC"
    if "smd" in text_lower and "hole" in text_lower:
        return "SMD_HOLE"
    if "short" in text_lower:
        return "SHORT_DRC"
    if "open" in text_lower:
        return "OPEN_DRC"
    if "solder paste" in text_lower:
        return "SOLDER_PASTE_DRC"
    if "courtyard" in text_lower or "pad outline" in text_lower:
        return "PASTE_COURTYARD_DRC"
    return "GENERIC_DRC"


def _extract_component(text: str) -> Optional[str]:
    """Try to extract a component reference designator from text.

    Handles both standard refs (``R1``, ``U2``) and pcbnew-style pad refs
    (``U1-7``, ``C1-1``, ``R1/1``).
    """
    # e.g. U1-7, C1-1, R1/1, U28
    match = re.search(r"\b([RCLU]\d+(?:[-/]\d+)?)\b", text)
    return match.group(1) if match else None


def _extract_net(text: str) -> Optional[str]:
    """Try to extract a net name from pcbnew DRC detail text.

    Handles formats like ``net 'VCC'``, ``Net name: 'SCK'``, or
    bare quoted names.
    """
    # e.g. net 'VCC' or Net name: 'SCK'
    match = re.search(r"net\s+'([^']+)'", text, re.IGNORECASE)
    if match:
        return match.group(1)
    # e.g. Net name: 'GND'
    match = re.search(r"name:\s+'([^']+)'", text, re.IGNORECASE)
    if match:
        return match.group(1)
    # e.g. on net 'VCC'
    match = re.search(r"on net '([^']+)'", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


# --------------------------------------------------------------------------- #
# DRC Agent
# --------------------------------------------------------------------------- #
class DRCAgent:
    """Runs DRC checks on a KiCad board and summarises results.

    The agent prefers the live ``pcbnew`` API when available.  When
    ``pcbnew`` is absent (e.g. CI/headless), it can parse a previously
    exported DRC report file via :meth:`parse_report_file`.

    Attributes:
        board: The pcbnew board object (None when not in KiCad).
        llm_engine: Optional LLM engine for natural-language summaries.
    """

    def __init__(
        self,
        board: Any = None,
        llm_engine: Any = None,
    ) -> None:
        self.board = board if board is not None else (pcbnew.GetBoard() if _HAS_PCBNEW and pcbnew is not None else None)
        self.llm_engine = llm_engine

    @property
    def has_pcbnew(self) -> bool:
        """True if the live pcbnew API is available."""
        return _HAS_PCBNEW and self.board is not None

    # ------------------------------------------------------------------ #
    # pcbnew DRC integration
    # ------------------------------------------------------------------ #
    def run_pcbnew_drc(
        self,
        min_clearance: float = 0.15,
        enable_unconnected: bool = True,
        enable_placement: bool = True,
    ) -> DRCReport:
        """Run pcbnew's built-in DRC engine on the current board.

        Falls back to :meth:`parse_report_file` if pcbnew is unavailable;
        in that case ``report_path`` must be set or the report will be empty.

        Args:
            min_clearance: Minimum clearance in mm for the DRC check.
            enable_unconnected: Check for unconnected pads.
            enable_placement: Check for component placement issues.

        Returns:
            A :class:`DRCReport` with all violations found.
        """
        if not self.has_pcbnew:
            # pcbnew not available — return an empty report with a note
            report = DRCReport()
            report.summary = (
                "pcbnew DRC could not run in this environment (pcbnew not available). "
                "Use parse_report_file() to analyse a previously exported DRC report."
            )
            return report

        assert pcbnew is not None  # for type checkers

        # Configure the DRC
        settings = pcbnew.DRC_SETTINGS()  # type: ignore[union-attr]
        settings.SetClearance(mm_to_du(min_clearance))
        # enable_unconnected and enable_placement map to pcbnew flags
        settings.SetDoUnconnected(enable_unconnected)
        settings.SetDoPlacement(enable_placement)

        # Run DRC and capture the result
        board = self.board
        # pcbnew's DRC runner (KiCad 7+ API)
        reporter = _ViolationReporter()
        try:
            runner = pcbnew.DRC_RUNNER()  # type: ignore[union-attr]
            runner.SetReportCallback(reporter.callback)
            runner.Run(board, settings)
        except Exception:  # pragma: no cover - depends on KiCad version
            # Fallback: use the simpler API
            try:
                board.RunDrc(min_clearance)  # type: ignore[union-attr]
            except Exception:
                pass

        report = reporter.report
        report.summary = None  # Will be set by LLM summarisation if available
        return report

    # ------------------------------------------------------------------ #
    # File-based parsing fallback
    # ------------------------------------------------------------------ #
    def parse_report_file(self, report_path: str | Path) -> DRCReport:
        """Parse a pcbnew DRC report file exported from a prior session.

        Args:
            report_path: Path to a ``.drc`` or DRC report text file.

        Returns:
            A :class:`DRCReport` with parsed violations.
        """
        path = Path(report_path)
        if not path.exists():
            raise FileNotFoundError(f"DRC report not found: {path}")

        content = path.read_text(encoding="utf-8")
        report = parse_drc_report(content)
        report.summary = None
        return report

    # ------------------------------------------------------------------ #
    # LLM-enhanced summary
    # ------------------------------------------------------------------ #
    def summarise(self, report: DRCReport, max_tokens: int = 512) -> str:
        """Generate an LLM-powered plain-English summary of violations.

        If no LLM engine is available, falls back to a basic text summary.

        Args:
            report: A :class:`DRCReport` to summarise.
            max_tokens: Maximum tokens for the LLM response.

        Returns:
            A human-readable summary string.
        """
        if not report.total_count:
            return "No DRC violations found. The board passes all configured design rules."

        if self.llm_engine is None:
            return self._fallback_summary(report)

        # Build the prompt for the LLM
        from nexus_eda.llm.prompts import (
            drc_analysis_prompt,
        )

        violations_text = self._violations_to_text(report)
        prompt = drc_analysis_prompt(violations_text, total=report.total_count)

        try:
            raw = self._call_llm(prompt, max_tokens)
            # The LLM may return JSON; extract the summary field if so
            return _extract_json_field(raw, "summary") or raw.strip()
        except Exception:
            return self._fallback_summary(report)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _fallback_summary(self, report: DRCReport) -> str:
        """Generate a basic text summary without an LLM."""
        lines = [
            f"DRC Summary: {report.total_count} violation(s) found",
            f"  Errors:   {report.error_count}",
            f"  Warnings: {report.warning_count}",
            f"  Info:     {report.info_count}",
            "",
        ]
        # Group by rule
        by_rule: dict[str, int] = {}
        for v in report.violations:
            by_rule[v.rule_id] = by_rule.get(v.rule_id, 0) + 1

        lines.append("Violation breakdown by rule:")
        for rule, count in sorted(by_rule.items(), key=lambda x: -x[1]):
            lines.append(f"  {rule}: {count}")

        if report.violations:
            lines.append("")
            lines.append("Top issues:")
            for v in report.violations[:5]:
                lines.append(f"  [{v.severity.value}] {v.description}")

        return "\n".join(lines)

    @staticmethod
    def _violations_to_text(report: DRCReport) -> str:
        """Convert a DRC report into a structured text block for the LLM."""
        lines = [
            f"Total violations: {report.total_count}",
            f"Errors: {report.error_count}, Warnings: {report.warning_count}, Info: {report.info_count}",
            "",
        ]
        for i, v in enumerate(report.violations, 1):
            lines.append(
                f"#{i} [{v.severity.value}] {v.rule_id}: {v.description}"
                f"{f' (net={v.net})' if v.net else ''}"
                f"{f' (component={v.component})' if v.component else ''}"
            )
        return "\n".join(lines)

    def _call_llm(self, prompt: str, max_tokens: int = 512) -> str:
        """Call the LLM engine — supports both llama_cpp.Llama and llama-cpp-server HTTP."""
        engine = self.llm_engine

        # If it's our LLMEngine wrapper
        if hasattr(engine, "generate"):
            return engine.generate(prompt, max_tokens=max_tokens)

        # If it's a raw llama_cpp.Llama instance
        if hasattr(engine, "__call__"):
            output: str = ""
            for chunk in engine(
                prompt,
                max_tokens=max_tokens,
                temperature=0.1,
                top_p=0.9,
            ):
                delta = chunk["choices"][0].get("delta", {}).get("content", "") or ""
                output += delta
            return output

        raise RuntimeError("LLM engine does not support generate() or __call__")


# --------------------------------------------------------------------------- #
# pcbnew interop helpers
# --------------------------------------------------------------------------- #
def mm_to_du(mm: float) -> int:
    """Convert millimetres to pcbnew internal units (nanometres * 1e6)."""
    if _HAS_PCBNEW and pcbnew is not None:
        try:
            return pcbnew.IUTIL_Mm2iu(mm)  # type: ignore[union-attr]
        except AttributeError:
            pass
    # pcbnew uses 1e-6 mm per internal unit
    return int(mm * 1e6)


class _ViolationReporter:
    """Internal callback that collects DRC violations from pcbnew's C++ runner.

    This object is passed as a callback to pcbnew's DRC runner.  The C++
    side calls back with violation details which we translate into
    :class:`DRCViolation` objects.
    """

    def __init__(self) -> None:
        self.report = DRCReport()
        self._counter = 0

    def callback(
        self,
        severity: int,
        rule_id: str,
        description: str,
        x: float,
        y: float,
        component: str = "",
        net: str = "",
    ) -> None:
        self._counter += 1
        self.report.add(
            DRCViolation(
                rule_id=rule_id or "GENERIC_DRC",
                description=description,
                severity=Severity.from_pcbnew(severity),
                component=component if component else None,
                net=net if net else None,
                x=x,
                y=y,
            )
        )


def _extract_json_field(text: str, field: str) -> Optional[str]:
    """Try to extract a JSON field from a mixed LLM response.

    The LLM may return prose followed by a JSON block.  This helper
    attempts to find and parse the JSON, then return the requested field.
    """
    # Find the first { ... } block
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    import json

    try:
        data = json.loads(text[start : end + 1])
        return data.get(field)
    except (json.JSONDecodeError, TypeError):
        return None


# --------------------------------------------------------------------------- #
# Public API stubs (for plugin entry point and agent __init__)
# --------------------------------------------------------------------------- #
def run_drc(
    board: Any = None,
    min_clearance: float = 0.15,
    report_path: Optional[str] = None,
    llm_engine: Any = None,
) -> DRCReport:
    """Convenience function: run DRC or parse a report file.

    Args:
        board: pcbnew board object (optional — used when pcbnew is available).
        min_clearance: Minimum clearance in mm for DRC.
        report_path: Path to a saved DRC report file.  When provided
            (and pcbnew is unavailable) this is used as the data source.
        llm_engine: Optional LLM engine for summaries.

    Returns:
        A :class:`DRCReport` populated with violations.
    """
    agent = DRCAgent(board=board, llm_engine=llm_engine)

    if report_path:
        report = agent.parse_report_file(report_path)
    else:
        report = agent.run_pcbnew_drc(min_clearance=min_clearance)

    # Auto-generate summary if LLM engine is available
    if llm_engine is not None:
        report.summary = agent.summarise(report)

    return report
