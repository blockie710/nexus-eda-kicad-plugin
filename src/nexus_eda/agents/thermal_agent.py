# SPDX-License-Identifier: Apache-2.0
"""Thermal hotspot detector agent for Nexus-EDA (Phase 3 — T3-W10.2).

Models component power dissipation and performs steady-state thermal analysis
to identify hotspots on a PCB.  When ``pcbnew`` is available the agent reads
power/net/class data directly from the board; otherwise it falls back to
parsing a structured thermal netlist file produced by a prior KiCad session.

Key classes
-----------
- :class:`PowerMode`              — operating mode enum (IDLE / ACTIVE / PEAK).
- :class:`ComponentPower`         — per-component power dissipation entry.
- :class:`ThermalHotspot`         — a detected hotspot with temperature estimate.
- :class:`ThermalReport`          — aggregated thermal analysis result.
- :class:`ThermalAgent`           — high-level orchestrator.
- :func:`parse_thermal_netlist`   — text/fallback parser for exported data.
- :func:`run_thermal_analysis`    — convenience entry point.

Thermal model
-------------
A simplified steady-state conduction model is used:

    T_junction = T_ambient + P_dissipated * R_th_ja

where ``R_th_ja`` (junction-to-ambient thermal resistance, °C/W) is estimated
from the component package and PCB copper area via empirical correlations.
The model is intentionally simple (single-point, steady-state, no convection
modelling) so that it is fully testable in CI without pcbnew, while still
producing actionable hotspot rankings.
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
# Enums
# --------------------------------------------------------------------------- #
class PowerMode(Enum):
    """Operating mode of a component."""

    IDLE = "idle"
    ACTIVE = "active"
    PEAK = "peak"

    @classmethod
    def from_str(cls, value: str) -> "PowerMode":
        """Parse a power mode from a string, defaulting to ACTIVE."""
        norm = value.strip().lower()
        for member in cls:
            if member.value == norm:
                return member
        # Unknown string — default to ACTIVE rather than raising
        return cls.ACTIVE


class PackageFamily(Enum):
    """PCB package families with associated thermal characteristics.

    Each family carries a base junction-to-case thermal resistance (R_th_jc, °C/W)
    and a default PCB copper area (mm²) used to estimate the PCB-path resistance.
    """

    SOD = ("SOD", 250.0, 2.0)    # Small Outline Diode, ~2 mm² pad
    SOT = ("SOT", 120.0, 4.0)    # Small Outline Transistor, ~4 mm²
    SOIC = ("SOIC", 85.0, 15.0)  # Small Outline IC, ~15 mm²
    QFN = ("QFN", 25.0, 40.0)    # Quad Flat No-leads, ~40 mm²
    BGA = ("BGA", 15.0, 60.0)    # Ball Grid Array, ~60 mm²
    TO220 = ("TO220", 3.0, 200.0)  # Power transistor, ~200 mm²
    TO263 = ("TO263", 4.0, 100.0)  # D2PAK, ~100 mm²
    TO252 = ("TO252", 6.0, 60.0)   # Smaller power package
    DIP = ("DIP", 50.0, 10.0)     # Dual Inline Package, ~10 mm²
    UNKNOWN = ("UNKNOWN", 100.0, 10.0)

    def __init__(self, label: str, r_th_jc: float, copper_mm2: float) -> None:
        self.label = label
        self.r_th_jc = r_th_jc  # °C/W
        self.copper_mm2 = copper_mm2  # mm² of PCB copper area

    @classmethod
    def from_footprint(cls, footprint: str) -> "PackageFamily":
        """Infer a package family from a KiCad footprint string.

        Handles typical KiCad footprint names like
        ``Package_TO_SOT_SMD:SOT-23-6`` or ``Package_Deal:TSOT-23-6``.
        """
        fp = footprint.lower().replace("_", "")
        if "to220" in fp or "to-220" in fp:
            return cls.TO220
        if "to263" in fp or "to-263" in fp or "d2pak" in fp:
            return cls.TO263
        if "to252" in fp or "to-252" in fp or "dpak" in fp:
            return cls.TO252
        if "sod" in fp or "sd" in fp:
            return cls.SOD
        if "sot" in fp:
            return cls.SOT
        if "qfn" in fp:
            return cls.QFN
        if "bga" in fp or "tfbga" in fp:
            return cls.BGA
        if "soic" in fp or "so-" in footprint.lower() or "sop" in fp:
            return cls.SOIC
        if "dip" in fp:
            return cls.DIP
        return cls.UNKNOWN


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass
class ComponentPower:
    """Power dissipation data for a single component.

    Attributes:
        ref: Component reference designator (e.g. ``U1``, ``R1``).
        power: Dissipated power in watts (W).
        voltage: Voltage across the component in volts (V).
        current: Current through the component in amperes (A).
        mode: Operating mode (:class:`PowerMode`).
        footprint: KiCad footprint string (used for package inference).
        r_th_ja: Junction-to-ambient thermal resistance in °C/W.
            If None, it is estimated from the footprint.
        copper_area_mm2: Optional override for PCB copper area around the
            component in mm².  If None, the package family default is used.
        max_junction_temp: Maximum junction temperature rating in °C
            (defaults to 125 °C for silicon).
    """

    ref: str
    power: float
    voltage: Optional[float] = None
    current: Optional[float] = None
    mode: PowerMode = PowerMode.ACTIVE
    footprint: str = ""
    r_th_ja: Optional[float] = None
    copper_area_mm2: Optional[float] = None
    max_junction_temp: float = 125.0

    # -- derived properties --------------------------------------------------- #
    @property
    def package_family(self) -> PackageFamily:
        """Inferred package family from the footprint string."""
        return PackageFamily.from_footprint(self.footprint) if self.footprint else PackageFamily.UNKNOWN

    @property
    def effective_copper_mm2(self) -> float:
        """Copper area used for thermal calculation."""
        if self.copper_area_mm2 is not None:
            return self.copper_area_mm2
        return self.package_family.copper_mm2

    @property
    def effective_r_th_ja(self) -> float:
        """Effective junction-to-ambient thermal resistance (°C/W).

        Computed as::

            R_th_ja = R_th_jc + R_th_cp + R_th_pa

        where ``R_th_cp`` (case-to-PCB) is a small constant (~1 °C/W for
        typical soldering) and ``R_th_pa`` (PCB-to-ambient) is estimated
        via an empirical correlation inversely proportional to the square
        root of the copper area.
        """
        if self.r_th_ja is not None:
            return self.r_th_ja

        r_th_jc = self.package_family.r_th_jc
        r_th_cp = 1.0  # case-to-PCB thermal resistance (°C/W)
        # PCB-to-ambient: empirical formula R_th_pa = 40 / sqrt(A_mm2)
        # This gives ~8.9 °C/W for 20 mm², ~2.9 °C/W for 200 mm² — reasonable.
        r_th_pa = 40.0 / (self.effective_copper_mm2 ** 0.5)

        return r_th_jc + r_th_cp + r_th_pa

    @property
    def temperature_rise(self) -> float:
        """Steady-state temperature rise above ambient (°C)."""
        return self.power * self.effective_r_th_ja

    @property
    def junction_temperature(self) -> float:
        """Junction temperature at the default 25 °C ambient (°C).

        Computed as ``T_ambient(25 °C) + P_dissipated × R_th_ja``.
        For ambient-aware calculations use
        ``ambient_temp + comp.temperature_rise``.
        """
        return 25.0 + self.temperature_rise

    @property
    def is_hotspot(self) -> bool:
        """True if the junction temperature exceeds 85 % of max rating.

        Uses the default 25 °C ambient.  The :class:`ThermalAgent` uses
        a proper ambient-aware check in :meth:`analyse_components`.
        """
        return self.junction_temperature > (self.max_junction_temp * 0.85)

    @property
    def margin(self) -> float:
        """Temperature margin to max junction rating (positive = safe).

        Uses the default 25 °C ambient.
        """
        return self.max_junction_temp - self.junction_temperature


@dataclass
class ThermalHotspot:
    """A detected thermal hotspot.

    Attributes:
        ref: Component reference designator.
        junction_temp: Estimated junction temperature (°C).
        power: Dissipated power (W).
        r_th_ja: Effective thermal resistance (°C/W).
        margin: Temperature margin to max rating (°C).
        max_junction_temp: Max junction rating (°C).
        recommendation: Human-readable fix suggestion.
    """

    ref: str
    junction_temp: float
    power: float
    r_th_ja: float
    margin: float
    max_junction_temp: float
    recommendation: str


@dataclass
class ThermalReport:
    """Aggregated thermal analysis result for a board.

    Attributes:
        ambient_temp: Ambient temperature in °C.
        components: List of analysed components.
        hotspots: List of detected hotspots (sorted by temperature desc).
        total_power: Sum of all component power dissipation (W).
        hottest_component: Ref of the hottest component.
        hottest_temp: Junction temperature of the hottest component (°C).
        summary: Optional plain-text or LLM-generated summary.
    """

    ambient_temp: float = 25.0
    components: list[ComponentPower] = field(default_factory=list)
    hotspots: list[ThermalHotspot] = field(default_factory=list)
    total_power: float = 0.0
    hottest_component: Optional[str] = None
    hottest_temp: float = 0.0
    summary: Optional[str] = None

    # -- aggregation ---------------------------------------------------------- #
    @property
    def total_count(self) -> int:
        """Total number of components analysed."""
        return len(self.components)

    @property
    def hotspot_count(self) -> int:
        """Number of detected hotspots."""
        return len(self.hotspots)

    @property
    def severity(self) -> str:
        """Overall thermal severity: ``'low'``, ``'medium'``, or ``'high'``.

        - ``high`` if any component exceeds its max junction temperature.
        - ``medium`` if any hotspot has < 10 °C margin.
        - ``medium`` if 3+ hotspots exist.
        - ``low`` otherwise.
        """
        # Check for temperature limit exceeded
        for comp in self.components:
            if self.ambient_temp + comp.temperature_rise > comp.max_junction_temp:
                return "high"
        # Check hotspot margins
        critical = sum(1 for h in self.hotspots if h.margin < 10.0)
        if critical > 0 or len(self.hotspots) >= 3:
            return "medium"
        if len(self.hotspots) > 0:
            return "low"
        return "low"

    @property
    def issues(self) -> list[str]:
        """List of human-readable thermal issues."""
        issues = []
        for comp in self.components:
            tj = self.ambient_temp + comp.temperature_rise
            if tj > comp.max_junction_temp:
                issues.append(
                    f"Component {comp.ref} exceeds max junction temperature: "
                    f"{tj:.1f}°C > {comp.max_junction_temp}°C"
                )
        for h in self.hotspots:
            issues.append(
                f"Hotspot {h.ref}: Tj={h.junction_temp:.1f}°C, margin={h.margin:.1f}°C"
            )
        return issues

    @property
    def suggestions(self) -> list[str]:
        """List of repair recommendations, one per hotspot."""
        return [h.recommendation for h in self.hotspots]


def _suggest_fix(comp: ComponentPower, tj: float) -> str:
    """Generate a fix suggestion for an overheating component."""
    margin = comp.max_junction_temp - tj
    if comp.package_family == PackageFamily.TO220:
        return f"Add heatsink to {comp.ref} or increase copper pour area."
    if comp.package_family == PackageFamily.SOT:
        return f"Use larger package for {comp.ref} or add thermal via array."
    if comp.package_family == PackageFamily.SOD:
        return f"Verify {comp.ref} power rating; consider parallel device."
    if margin < 0:
        # Component exceeds max junction temperature — recommend how much
        # to increase copper area.  Using the PCB-to-ambient model
        # R_th_pa = 40 / sqrt(A_mm2), the total R_th_ja = R_th_jc + R_th_cp
        # + R_th_pa.  To bring Tj back to the max rating we need:
        #   P * R_th_ja_new = T_max - T_ambient
        # Solving for the required R_th_pa and then A_mm2:
        #   R_th_pa_req = (T_max - T_amb) / P - R_th_jc - R_th_cp
        #   A_req = (40 / R_th_pa_req)^2
        if comp.power > 0:
            t_amb = 25.0
            r_th_jc = comp.package_family.r_th_jc
            r_th_cp = 1.0
            r_th_pa_req = (comp.max_junction_temp - t_amb) / comp.power - r_th_jc - r_th_cp
            if r_th_pa_req > 0:
                a_req = (40.0 / r_th_pa_req) ** 2
                pct_increase = max(0, int((a_req / comp.effective_copper_mm2 - 1) * 100))
                return (
                    f"Increase copper area for {comp.ref} by {pct_increase}% "
                    f"(approx {pct_increase}% more via area or thermal vias)."
                )
        return (
            f"Reduce power dissipation or improve thermal coupling for {comp.ref}."
        )
    return f"Reduce power dissipation or improve thermal coupling for {comp.ref}."


# --------------------------------------------------------------------------- #
# Thermal netlist text parser (fallback — no pcbnew)
# --------------------------------------------------------------------------- #
#
# Format for exported thermal data (one component per line):
#
#   R1 0.125 V=5.0 I=0.010 active SOT-23-3 150 125
#   ^  ^     ^    ^    ^    ^     ^            ^   ^
#   |  power volt curr mode footprint copper  Tj_max
#
# Fields are space-separated; optional columns (voltage, current, mode,
# footprint, copper_area_mm2, max_junction_temp) may be omitted.
# Lines starting with '#' are comments.
# The parser uses a structured token approach: named tokens (V=, I=, Tj=,
# mode keywords) are recognised by their prefix; bare numeric tokens after
# the power value are interpreted positionally (copper_area, then Tj_max);
# bare alphanumeric tokens that are not numeric are treated as mode then
# footprint in order.
#


def parse_thermal_netlist(content: str) -> list[ComponentPower]:
    """Parse a structured thermal netlist text into component power entries.

    Args:
        content: Text with one component per line.  Comments (lines
            starting with ``#``) are skipped.

    Returns:
        List of :class:`ComponentPower` objects.

    Format per line::

        <ref> <power_W> [V=<voltage> I=<current>] [mode] [footprint] [copper_mm2] [Tj_max]

    Example::

        # Thermal data export
        U1 2.5 V=5.0 I=0.5 active QFN-48 40 125
        R1 0.125 V=12.0 I=0.010 active SOT-23-3
    """
    components: list[ComponentPower] = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        tokens = line.split()
        if len(tokens) < 2:
            continue

        ref = tokens[0]
        try:
            power = float(tokens[1])
        except ValueError:
            continue

        voltage: Optional[float] = None
        current: Optional[float] = None
        mode = PowerMode.ACTIVE
        footprint = ""
        copper_area: Optional[float] = None
        max_junction_temp: Optional[float] = None

        # Walk remaining tokens with a state-machine that categorises each
        # by prefix / type.  This replaces the fragile positional logic that
        # depended on an uninitialised ``mode_set`` variable.
        for tok in tokens[2:]:
            if tok.startswith("V=") and len(tok) > 2:
                try:
                    voltage = float(tok[2:])
                except ValueError:
                    pass
            elif tok.startswith("I=") and len(tok) > 2:
                try:
                    current = float(tok[2:])
                except ValueError:
                    pass
            elif tok.startswith("Tj=") and len(tok) > 3:
                try:
                    max_junction_temp = float(tok[3:])
                except ValueError:
                    pass
            elif _is_numeric(tok):
                # Bare numeric token — positional: first is copper area,
                # second is max junction temperature.
                if copper_area is None:
                    copper_area = float(tok)
                elif max_junction_temp is None:
                    max_junction_temp = float(tok)
                # Extra numeric tokens beyond these two are ignored.
            elif tok.lower() in {"idle", "active", "peak"}:
                mode = PowerMode.from_str(tok)
            elif not footprint and not _is_numeric(tok):
                # First non-numeric, non-keyword token is the footprint.
                footprint = tok

        comp = ComponentPower(
            ref=ref,
            power=power,
            voltage=voltage,
            current=current,
            mode=mode,
            footprint=footprint,
            copper_area_mm2=copper_area,
            max_junction_temp=max_junction_temp if max_junction_temp is not None else 125.0,
        )
        components.append(comp)

    return components


def _is_numeric(s: str) -> bool:
    """Check if a string represents a number (int or float)."""
    try:
        float(s)
        return True
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
# Thermal Agent
# --------------------------------------------------------------------------- #
class ThermalAgent:
    """Thermal analysis agent for PCB power-dissipation hotspot detection.

    Prefers the live ``pcbnew`` API when available.  When ``pcbnet`` is
    absent (e.g. CI/headless), the agent can parse a previously exported
    thermal netlist file via :meth:`parse_file` or
    :meth:`analyse_components`.

    Attributes:
        board: The pcbnew board object (None when not in KiCad).
        ambient_temp: Ambient temperature in °C.
        llm_engine: Optional LLM engine for natural-language summaries.
    """

    def __init__(
        self,
        board: Any = None,
        llm_engine: Any = None,
        ambient_temp: float = 25.0,
    ) -> None:
        self.board = board
        self.llm_engine = llm_engine
        self.ambient_temp = ambient_temp

    @property
    def has_pcbnew(self) -> bool:
        """True if the live pcbnew API is available."""
        return _HAS_PCBNEW and self.board is not None

    # ------------------------------------------------------------------ #
    # pcbnew board integration
    # ------------------------------------------------------------------ #
    def extract_component_power(self) -> list[ComponentPower]:
        """Extract power dissipation data from a pcbnew board.

        This method reads footprint, net, and designator information from
        the live pcbnew board and estimates power dissipation from component
        net connections and known device types (e.g. regulator VIN→VOUT voltage
        drop × current, resistor V²/R).

        Falls back to an empty list when ``pcbnew`` is not available.
        """
        if not self.has_pcbnew:
            return []

        assert pcbnew is not None  # for type checkers

        components: list[ComponentPower] = []

        # Iterate over all footprint modules on the board
        for mod in self.board.GetModules():
            ref = mod.GetReference() or ""
            footprint = mod.GetFPID().GetLibItemName() or ""
            value = (mod.GetValue() or "").strip()

            # Estimate power based on component type
            power, voltage, current = self._estimate_power(ref, footprint, value)

            comp = ComponentPower(
                ref=ref,
                power=power,
                voltage=voltage,
                current=current,
                mode=PowerMode.ACTIVE,
                footprint=footprint,
            )
            components.append(comp)

        return components

    def _estimate_power(
        self, ref: str, footprint: str, value: str
    ) -> tuple[float, Optional[float], Optional[float]]:
        """Estimate power dissipation for a component from its ref/value.

        This implements heuristic power estimation for common component types:

        - **Resistors** (R*): P = V²/R using the net voltage.
        - **Regulators/ICs** (U* with "V" or "REG" in value): P = V_drop × I.
        - **Diodes** (D*): P ≈ 0.7 × I (typical forward drop).
        - **MOSFETs** (Q*): P = R_DS(on) × I² (use value as R_DS(on) if numeric).

        Default: 0.125 W per component (typical low-power estimate).
        """
        ref_upper = ref.upper()
        # Strip unit prefix from value (e.g. "10k" -> 10000, "4.7k" -> 4700)
        try:
            numeric_val = self._parse_component_value(value)
        except ValueError:
            numeric_val = None

        # MOSFET: Q* — value may be R_DS(on)
        if ref_upper.startswith("Q"):
            if numeric_val is not None:
                # P = I²R — assume 2A switching current
                current = 2.0
                power = current * current * numeric_val
                return power, None, current
            return 0.5, None, 1.0

        # Regulator / IC: U* with voltage in value
        if ref_upper.startswith("U") and ("V" in value.upper() or "REG" in value.upper()):
            # e.g. "LM1117-5.0" → 5V output, assume 1A load, 12V input
            voltage_match = re.search(r"(\d+\.?\d*)\s*[Vv]", value)
            if voltage_match:
                v_out = float(voltage_match.group(1))
                current = 1.0  # assume 1A load
                power = (12.0 - v_out) * current  # V_drop × I
                return power, v_out, current
            # Generic regulator — assume 0.5W dissipation
            return 0.5, None, 1.0

        # Resistor: R* with value
        if ref_upper.startswith("R") and numeric_val is not None:
            # P = V²/R — assume 5V across resistor
            voltage = 5.0
            power = voltage * voltage / numeric_val
            current = voltage / numeric_val
            return power, voltage, current

        # Diode: D*
        if ref_upper.startswith("D"):
            # Forward voltage ~0.7V, assume 1A
            return 0.7, 0.7, 1.0

        # Capacitor: C* — negligible dissipation, model ESR loss
        if ref_upper.startswith("C") and numeric_val is not None:
            # Assume ESR ≈ 0.05Ω, switching current 0.5A at 100kHz
            esr = 0.05
            current = 0.5
            power = current * current * esr
            return power, None, current

        # Default: 0.125W (typical small-component dissipation)
        return 0.125, None, None

    @staticmethod
    def _parse_component_value(value: str) -> float:
        """Parse a KiCad component value into ohms/watts (float).

        Handles suffixes: k/kilo, M/mega, m/milli, u/micro, n/nano, p/pico.
        E.g. ``"10k"`` → 10000, ``"4.7u"`` → 4.7e-6, ``"0.1F"`` → 0.1.
        """
        if not value:
            raise ValueError(f"Empty value: {value!r}")

        v = value.strip().upper()
        # Remove common prefixes
        v = v.replace("Ω", "").replace("R", "").replace("K", "K").replace("Ω", "")

        # Handle multiplier suffixes
        multiplier = 1.0
        suffix_map = {
            "K": 1e3,
            "M": 1e6,
            "U": 1e-6,
            "N": 1e-9,
            "P": 1e-12,
            "KOHM": 1e3,
            "MOHM": 1e6,
        }
        for suffix, mult in suffix_map.items():
            if v.endswith(suffix):
                v = v[: -len(suffix)]
                multiplier = mult
                break

        return float(v) * multiplier

    # ------------------------------------------------------------------ #
    # File-based parsing fallback
    # ------------------------------------------------------------------ #
    def parse_file(self, filepath: str | Path) -> list[ComponentPower]:
        """Parse a thermal netlist export file.

        Args:
            filepath: Path to a ``.thermal`` or ``.txt`` export file.

        Returns:
            List of :class:`ComponentPower` objects.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Thermal data file not found: {path}")

        content = path.read_text(encoding="utf-8")
        return parse_thermal_netlist(content)

    # ------------------------------------------------------------------ #
    # Analysis
    # ------------------------------------------------------------------ #
    def analyse_components(
        self, components: list[ComponentPower]
    ) -> ThermalReport:
        """Run thermal analysis on a list of components.

        Args:
            components: List of :class:`ComponentPower` objects to analyse.

        Returns:
            A :class:`ThermalReport` with hotspots and severity.
        """
        report = ThermalReport(ambient_temp=self.ambient_temp)
        report.components = list(components)

        # Calculate total power
        report.total_power = sum(c.power for c in components)

        # Identify hotspots: components exceeding 85% of max junction temp
        hotspots: list[ThermalHotspot] = []
        for comp in components:
            tj = self.ambient_temp + comp.temperature_rise
            if comp.is_hotspot or tj > 85.0:
                hotspot = ThermalHotspot(
                    ref=comp.ref,
                    junction_temp=tj,
                    power=comp.power,
                    r_th_ja=comp.effective_r_th_ja,
                    margin=comp.margin,
                    max_junction_temp=comp.max_junction_temp,
                    recommendation=_suggest_fix(comp, tj),
                )
                hotspots.append(hotspot)

        # Sort by junction temperature descending
        hotspots.sort(key=lambda h: h.junction_temp, reverse=True)
        report.hotspots = hotspots

        # Track hottest component
        if components:
            hottest = max(components, key=lambda c: self.ambient_temp + c.temperature_rise)
            report.hottest_component = hottest.ref
            report.hottest_temp = self.ambient_temp + hottest.temperature_rise

        return report

    def analyse_board(self) -> ThermalReport:
        """Run a full thermal analysis on the pcbnew board.

        Extracts component power data from the board (if pcbnew is available),
        then runs :meth:`analyse_components`.

        Returns:
            A :class:`ThermalReport`.  If pcbnew is unavailable and no
            report file has been parsed, returns an empty report.
        """
        components = self.extract_component_power()
        return self.analyse_components(components)

    def analyse_report_file(self, filepath: str | Path) -> ThermalReport:
        """Parse a thermal export file and run analysis on it.

        Args:
            filepath: Path to a ``.thermal`` export file.

        Returns:
            A :class:`ThermalReport` built from the parsed components.
        """
        components = self.parse_file(filepath)
        return self.analyse_components(components)

    # ------------------------------------------------------------------ #
    # LLM-enhanced summary
    # ------------------------------------------------------------------ #
    def summarise(self, report: ThermalReport, max_tokens: int = 512) -> str:
        """Generate an LLM-powered plain-English thermal summary.

        Falls back to a text summary if no LLM engine is available.

        Args:
            report: A :class:`ThermalReport` to summarise.
            max_tokens: Maximum tokens for the LLM response.

        Returns:
            A human-readable summary string.
        """
        if not report.components or self.llm_engine is None:
            return self._fallback_summary(report)

        from nexus_eda.llm.prompts import thermal_analysis_prompt

        components_text = self._components_to_text(report)
        prompt = thermal_analysis_prompt(
            components_text,
            total_power=f"{report.total_power:.3f}",
            hotspot_count=str(report.hotspot_count),
            hottest_component=report.hottest_component or "N/A",
            hottest_temp=f"{report.hottest_temp:.1f}",
        )

        try:
            raw = self._call_llm(prompt, max_tokens)
            return _extract_json_field(raw, "summary") or raw.strip()
        except Exception:
            return self._fallback_summary(report)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _fallback_summary(self, report: ThermalReport) -> str:
        """Generate a basic text summary without an LLM."""
        if not report.components:
            return (
                "No thermal data available. Ensure the board is loaded or "
                "a thermal export file is provided."
            )
        lines = [
            f"Thermal Summary: {report.total_count} component(s) analysed",
            f"  Total power dissipation: {report.total_power:.3f} W",
            f"  Hotspot(s) detected: {report.hotspot_count}",
            f"  Hottest component: {report.hottest_component or 'N/A'} "
            f"at {report.hottest_temp:.1f}°C",
            f"  Severity: {report.severity}",
            "",
        ]

        if report.hotspots:
            lines.append("Hotspot details:")
            for h in report.hotspots:
                lines.append(
                    f"  [{h.ref}] Tj={h.junction_temp:.1f}°C "
                    f"(margin: {h.margin:.1f}°C) — {h.recommendation}"
                )

        if not report.hotspots:
            lines.append("No thermal hotspots detected above 85°C.")

        return "\n".join(lines)

    @staticmethod
    def _components_to_text(report: ThermalReport) -> str:
        """Convert a ThermalReport into structured text for the LLM prompt."""
        lines = [
            f"Ambient temperature: {report.ambient_temp}°C",
            f"Total power: {report.total_power:.3f} W",
            f"Components: {report.total_count}",
            "",
            "COMP_ID | Power(W) | Voltage(V) | Current(A) | R_th(°C/W) | Tj(°C) | Footprint",
        ]
        for comp in report.components:
            lines.append(
                f"{comp.ref} | {comp.power:.4f} | "
                f"{comp.voltage or '-'} | {comp.current or '-'} | "
                f"{comp.effective_r_th_ja:.1f} | {comp.junction_temperature:.1f} | "
                f"{comp.footprint or 'N/A'}"
            )
        return "\n".join(lines)

    def _call_llm(self, prompt: str, max_tokens: int = 512) -> str:
        """Call the LLM engine — supports LLMEngine wrapper and raw Llama."""
        engine = self.llm_engine

        if hasattr(engine, "generate"):
            return engine.generate(prompt, max_tokens=max_tokens)

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

        raise RuntimeError("LLM engine does not support generate() or __call__()")


# --------------------------------------------------------------------------- #
# JSON extraction helper (shared with DRC agent pattern)
# --------------------------------------------------------------------------- #
def _extract_json_field(text: str, field: str) -> Optional[str]:
    """Extract a field from a JSON object embedded in an LLM response."""
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
# Public API
# --------------------------------------------------------------------------- #
def run_thermal_analysis(
    board: Any = None,
    components: Optional[list[ComponentPower]] = None,
    report_path: Optional[str] = None,
    llm_engine: Any = None,
    ambient_temp: float = 25.0,
) -> ThermalReport:
    """Convenience function: run thermal analysis and optionally summarise.

    Args:
        board: pcbnew board object (optional — used when pcbnew is available).
        components: Pre-built list of :class:`ComponentPower` entries.
        report_path: Path to a thermal export file (overrides ``board``).
        llm_engine: Optional LLM engine for summaries.
        ambient_temp: Ambient temperature in °C.

    Returns:
        A :class:`ThermalReport` with hotspots populated and an
        LLM-generated summary if an engine was provided.
    """
    agent = ThermalAgent(
        board=board,
        llm_engine=llm_engine,
        ambient_temp=ambient_temp,
    )

    if report_path:
        report = agent.analyse_report_file(report_path)
    elif components is not None:
        report = agent.analyse_components(components)
    else:
        report = agent.analyse_board()

    if llm_engine is not None and report.components:
        report.summary = agent.summarise(report)

    return report
