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
    "DRC_ANALYSIS_PROMPT",
    "netlist_analysis_prompt",
    "routing_suggestion_prompt",
    "drc_analysis_prompt",
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
# DRC analysis template
# --------------------------------------------------------------------------- #
DRC_ANALYSIS_PROMPT = """\\
You are Nexus-EDA, an expert PCB design review assistant running locally on llama.cpp.
Your task is to analyze a list of DRC (Design Rule Check) violations and produce
a clear, actionable summary.

VIOLATIONS:
{violations}

INSTRUCTIONS:
- Summarise the total number of violations and their severity breakdown.
- Group similar violation types together.
- For each group, provide a concise explanation of the root cause.
- Provide practical, actionable fix suggestions for the top 3 most critical issues.
- If there are no violations, state that the board passes DRC.
- Use "low", "medium", or "high" for overall severity.
- Output a JSON object with keys: summary, severity, issues, suggestions.
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


def drc_analysis_prompt(violations: str, total: int = 0, **extra: Any) -> str:
    """Render the DRC analysis prompt from a violations text block.

    Args:
        violations: Text listing DRC violations (one per line).
        total: Total violation count (used in the prompt for context).
        **extra: Additional template fields (each truncated to 500 chars).

    Returns:
        A formatted prompt string ready for LLM generation.
    """
    fields: dict[str, Any] = {
        "violations": _truncate(violations),
    }
    for key, val in extra.items():
        fields[key] = _truncate(val, 500)
    rendered = DRC_ANALYSIS_PROMPT.format(**fields)
    # The template also has {total} available if needed via f-string substitution
    if total:
        rendered = rendered.replace("{total}", str(total))
    return rendered
