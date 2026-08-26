# SPDX-License-Identifier: Apache-2.0
"""Nexus-EDA LLM integration — llama.cpp binding wrapper, model loading, and prompts."""

from .engine import LLMEngine, LLMError, load_model, generate
from .prompts import (
    NETLIST_ANALYSIS_PROMPT,
    ROUTING_SUGGESTION_PROMPT,
    netlist_analysis_prompt,
    routing_suggestion_prompt,
)

__all__ = [
    "LLMEngine",
    "LLMError",
    "load_model",
    "generate",
    "NETLIST_ANALYSIS_PROMPT",
    "ROUTING_SUGGESTION_PROMPT",
    "netlist_analysis_prompt",
    "routing_suggestion_prompt",
]
