# SPDX-License-Identifier: Apache-2.0
"""Prompt templates for Nexus-EDA LLM agents.

All templates render via :func:`str.format` and are designed to be consumed
by the local llama.cpp engine wrapper in :mod:`nexus_eda.llm.engine`.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "NETLIST_ANALYSIS_PROMPT",
    "ROUTING_SUGGESTION_PROMPT",
    "THERMAL_ANALYSIS_PROMPT",
    "netlist_analysis_prompt",
    "routing_suggestion_prompt",
    "thermal_analysis_prompt",
]


# --------------------------------------------------------------------------- #
# Static templates
# --------------------------------------------------------------------------- #
NETLIST_ANALYSIS_PROMPT = """\
You are Nexus-EDA, an expert PCB design assistant running locally on llama.cpp.
Your task is to analyze a KiCad netlist and identify design issues.

NETLIST:
{netlist}

INSTRUCTIONS:
- Count total nets, unrouted nets, and flagged components.
- Identify placement issues: components too close, overlapping, or oddly grouped.
- Flag any nets with excessive fanout (>10 connections).
- Suggest practical fixes for the top 3 issues.
- Output a JSON object with keys: total_nets, unrouted_count, severity, issues, suggestions.
- Use "low", "medium", or "high" for severity.
- Keep response concise and JSON-valid.

ANALYSIS:"""

ROUTING_SUGGESTION_PROMPT = """\
You are Nexus-EDA, an expert PCB layout assistant running locally on llama.cpp.
Your task is to suggest an optimal routing path for a selected net.

NET NAME: {net_name}
SELECTED NET DETAILS: {net_details}
LAYER CONSTRAINTS: {layer_constraints}
OBSTACLES (traces, vias, zones): {obstacles}
AVAILABLE LAYERS: {available_layers}

INSTRUCTIONS:
- Propose a step-by-step routing path from the first pin to the last pin.
- Respect design rules: {design_rules}.
- Avoid obstacles listed above.
- Prefer the shortest path that minimizes via count.
- Estimate total trace length in mm.
- Provide confidence as 0.0–1.0.
- Output a JSON object with keys: path_description, estimated_length, confidence, violations.

SUGGESTION:"""


# --------------------------------------------------------------------------- #
# Thermal analysis template
# --------------------------------------------------------------------------- #
THERMAL_ANALYSIS_PROMPT = """\
You are Nexus-EDA, an expert PCB thermal analysis assistant running locally on llama.cpp.
Your task is to analyze component power dissipation data and identify thermal hotspots.

COMPONENT DATA:
{components}

Total power dissipation: {total_power} W
Hotspot count: {hotspot_count}
Hottest component: {hottest_component} at {hottest_temp}°C
Ambient temperature: 25°C

INSTRUCTIONS:
- Summarise the total power dissipation and the hottest component.
- For each hotspot, explain why it is overheating (high power × high thermal resistance).
- Group hotspots by root cause: excessive power, poor thermal coupling, insufficient copper, or wrong package.
- Provide 3 actionable fix suggestions ranked by impact (e.g. heatsinks, copper pour, package upgrade, thermal vias).
- If no hotspots exceed 85°C, state the board is thermally safe.
- Output a JSON object with keys: summary, severity, issues, suggestions.
- Use "low", "medium", or "high" for severity.
- Keep response concise and JSON-valid.

ANALYSIS:"""


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #
def _truncate(value: Any, limit: int = 2000) -> str:
    """Truncate long string values to keep prompts within context limits."""
    text = str(value)
    if len(text) > limit:
        return text[:limit] + "\n...[truncated]"
    return text


def netlist_analysis_prompt(netlist: str, **extra: Any) -> str:
    """Render the netlist analysis prompt from a netlist string.

    Extra keyword args are available as additional template fields (e.g.
    ``design_rules="keepout zones: ...```); each is truncated to keep the
    rendered prompt within context limits.
    """
    fields: dict[str, Any] = {"netlist": _truncate(netlist)}
    for key, val in extra.items():
        fields[key] = _truncate(val, 500)
    return NETLIST_ANALYSIS_PROMPT.format(**fields)


def routing_suggestion_prompt(
    net_name: str,
    net_details: str = "",
    layer_constraints: str = "",
    obstacles: str = "none",
    available_layers: str = "all",
    design_rules: str = "default KiCad rules",
) -> str:
    """Render the routing-suggestion prompt for a single net."""
    return ROUTING_SUGGESTION_PROMPT.format(
        net_name=net_name,
        net_details=_truncate(net_details),
        layer_constraints=_truncate(layer_constraints),
        obstacles=_truncate(obstacles),
        available_layers=available_layers,
        design_rules=_truncate(design_rules, 300),
    )


def thermal_analysis_prompt(
    components: str,
    total_power: str = "0",
    hotspot_count: str = "0",
    hottest_component: str = "N/A",
    hottest_temp: str = "0",
    **extra: Any,
) -> str:
    """Render the thermal-analysis prompt from a components text block.

    Args:
        components: Text listing component power/thermal data (one per line).
        total_power: Total board power dissipation in watts.
        hotspot_count: Number of detected hotspots.
        hottest_component: Ref designator of the hottest component.
        hottest_temp: Junction temperature of the hottest component (°C).
        **extra: Additional template fields (each truncated to 500 chars).

    Returns:
        A formatted prompt string ready for LLM generation.
    """
    fields: dict[str, Any] = {
        "components": _truncate(components),
        "total_power": total_power,
        "hotspot_count": hotspot_count,
        "hottest_component": hottest_component,
        "hottest_temp": hottest_temp,
    }
    for key, val in extra.items():
        fields[key] = _truncate(val, 500)
    return THERMAL_ANALYSIS_PROMPT.format(**fields)
