# SPDX-License-Identifier: Apache-2.0
"""Configuration loader for Nexus-EDA support automation.

Loads ``support_config.yaml`` (or a custom path) and normalises it into a
:class:`~nexus_eda.support.models.SupportConfig` with typed category and FAQ
entries.  Falls back to built-in defaults when the file is missing so the
module is usable out-of-the-box.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from .models import FAQEntry, SupportConfig, TicketCategory

# -- Default configuration -------------------------------------------------- #

DEFAULT_CATEGORIES: list[TicketCategory] = [
    TicketCategory(
        name="billing",
        label="Billing & Subscriptions",
        description="Questions about Stripe subscriptions, invoices, refunds, and pricing tiers.",
        keywords=[
            "refund", "invoice", "subscription", "billing", "charge",
            "stripe", "cancel", "pricing", "payment", "billing cycle",
            "upgrade", "downgrade", "pro", "enterprise", "maker",
            "overcharge", "dispute", "receipt", "failed payment",
        ],
        agent_profile="nexus-minimal",
        priority=4,
        sla_hours=4.0,
    ),
    TicketCategory(
        name="technical",
        label="Technical Support",
        description="Installation issues, plugin errors, pcbnew integration, and local LLM setup.",
        keywords=[
            "error", "install", "crash", "plugin", "pcbnew", "ki cad",
            "kicad", "llama cpp", "load model", "cuda", "vram", "gpu",
            "trace", "exception", "stack trace", "windows", "python",
            "import error", "runtime", "hang", "freeze", "driver",
        ],
        agent_profile="nexus-llm",
        priority=5,
        sla_hours=8.0,
    ),
    TicketCategory(
        name="feature",
        label="Feature Requests & Feedback",
        description="Suggestions for new features, design improvements, and capability requests.",
        keywords=[
            "feature", "request", "suggestion", "roadmap", "would be nice",
            "could you add", "enhancement", "improvement", "missing",
            "wish", "idea", "proposal", "feedback", "integrate", "support for",
        ],
        agent_profile="nexus-fast",
        priority=2,
        sla_hours=48.0,
    ),
    TicketCategory(
        name="bug",
        label="Bug Reports",
        description="Confirmed or suspected bugs, crashes, incorrect output from agents.",
        keywords=[
            "bug", "bug report", "crash", "broken", "wrong", "incorrect",
            "does not work", "fails", "failure", "regression", "glitch",
            "malfunction", "unexpected", "issue", "not working", "error",
        ],
        agent_profile="nexus-llm",
        priority=5,
        sla_hours=6.0,
    ),
    ]


DEFAULT_FAQ_ENTRIES: list[FAQEntry] = [
    FAQEntry(
        question="How do I install the Nexus-EDA KiCad plugin?",
        answer=(
            "Open KiCad's Plugin Manager (Tools → Plugin and Content Manager), "
            "search for 'Nexus-EDA', click Install, and restart KiCad. "
            "Alternatively, run ``pip install -e .`` from the plugin directory, "
            "then point KiCad to the installed package."
        ),
        keywords=["install", "installation", "plugin manager", "pip install", "kicad"],
        category="technical",
        confidence_boost=1.2,
    ),
    FAQEntry(
        question="My local LLM model won't load — what should I do?",
        answer=(
            "Ensure you have a compatible quantized GGUF model (Q4_K_M format) "
            "and set the NEXUS_LLM_MODEL_PATH environment variable to its path. "
            "The RTX 4090 recommendation is Qwen3-Coder-32B-Q4_K_M (~18 GB). "
            "Run ``python -c 'from nexus_eda.llm.engine import load_model; load_model()'`` "
            "to verify the model loads."
        ),
        keywords=["model", "load", "gguf", "env", "path", "gpu", "vram"],
        category="technical",
        confidence_boost=1.3,
    ),
    FAQEntry(
        question="How do I cancel or downgrade my subscription?",
        answer=(
            "Visit your account page at app.nexuseda.com/account/billing, "
            "click 'Manage Subscription', and select 'Cancel Plan' or "
            "'Downgrade'.  You'll retain Pro features until the end of the "
            "current billing period.  No prorated refunds are issued for "
            "downgrades, but you may request a full refund within 7 days "
            "of a new payment."
        ),
        keywords=["cancel", "downgrade", "subscription", "billing", "refund", "account"],
        category="billing",
        confidence_boost=1.2,
    ),
    FAQEntry(
        question="What are the pricing tiers?",
        answer=(
            "Nexus-EDA offers four tiers: Free (1 project, community models), "
            "Maker ($19/mo, 10 projects, Qwen2.5-7B), "
            "Pro ($49/mo, unlimited projects, Qwen3-Coder-32B), "
            "and Enterprise (custom pricing, ITAR/GDPR compliance, dedicated support)."
        ),
        keywords=["pricing", "price", "cost", "tiers", "free", "maker", "pro", "enterprise"],
        category="billing",
        confidence_boost=1.0,
    ),
    FAQEntry(
        question="Is Nexus-EDA air-gapped and sovereign?",
        answer=(
            "Yes.  All LLM inference runs locally on your machine via llama.cpp. "
            "Phase 4 adds encrypted local storage (AES-256) and SABLE-inspired "
            "28 scoped entry points that strip all paths, PDK data, and model "
            "weights from outbound telemetry."
        ),
        keywords=["air gap", "airgapped", "sovereign", "local", "offline", "privacy", "encryption"],
        category="technical",
        confidence_boost=0.9,
    ),
    FAQEntry(
        question="How do I request a new feature?",
        answer=(
            "Submit feature requests as GitHub Issues (github.com/blockie710/nexus-eda-kicad-plugin/issues) "
            "using the 'feature-request' template.  All proposals are reviewed "
            "against the 12-month roadmap and prioritised by community votes."
        ),
        keywords=["feature", "request", "roadmap", "github", "issue", "proposal", "contribute"],
        category="feature",
        confidence_boost=0.8,
    ),
]


# -- Paths ------------------------------------------------------------------ #

_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # repo root
_DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "support_config.yaml"


def default_config_path() -> Path:
    """Return the default support_config.yaml path (repo-level config dir)."""
    return _DEFAULT_CONFIG_PATH


def _builtin_config() -> SupportConfig:
    """Return a :class:`SupportConfig` with the built-in defaults."""
    return SupportConfig(
        categories=list(DEFAULT_CATEGORIES),
        faq_entries=list(DEFAULT_FAQ_ENTRIES),
    )


def load_config(
    path: Optional[str | Path] = None,
) -> SupportConfig:
    """Load support configuration from a YAML file.

    Parameters
    ----------
    path:
        Path to a YAML config file.  If *None*, the default
        ``config/support_config.yaml`` is tried; if it does not exist,
        built-in defaults are returned.

    Returns
    -------
    SupportConfig
        Typed configuration with categories and FAQ entries.
    """
    if path is None:
        path = _DEFAULT_CONFIG_PATH

    p = Path(path)
    if not p.exists():
        return _builtin_config()

    with open(p, "r", encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}

    categories = [
        TicketCategory.from_dict(c) for c in raw.get("categories", [])
    ]
    if not categories:
        categories = list(DEFAULT_CATEGORIES)

    faq_entries = [
        FAQEntry.from_dict(e) for e in raw.get("faq", [])
    ]
    if not faq_entries:
        faq_entries = list(DEFAULT_FAQ_ENTRIES)

    return SupportConfig(
        categories=categories,
        faq_entries=faq_entries,
        router_fallback_model=raw.get("router_fallback_model",
                                      "Qwen2.5-Coder-7B-Q4_K_M"),
        faq_fallback_model=raw.get("faq_fallback_model",
                                   "Qwen2.5-Coder-7B-Q4_K_M"),
        confidence_threshold=float(raw.get("confidence_threshold", 0.5)),
        llm_max_tokens=int(raw.get("llm_max_tokens", 512)),
        llm_temperature=float(raw.get("llm_temperature", 0.1)),
        auto_reply=bool(raw.get("auto_reply", False)),
        auto_reply_categories=list(raw.get("auto_reply_categories", [])),
        raw=raw,
    )


def _text_for_matching(text: str) -> str:
    """Normalise text for keyword matching: lowercase, strip extra spaces."""
    return " ".join(text.lower().strip().split())
