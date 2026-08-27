# SPDX-License-Identifier: Apache-2.0
"""Subscription tier definitions for Nexus-EDA SaaS billing.

Tiers are aligned with the Phase 2-5 plan (T5-W21.1) and the pitch deck:

    - Free      : Local-only, community tier           ($0)
    - Maker     : Local + E2EE cloud sync              ($19/mo)
    - Pro       : Cloud LLMs + advanced BOM optimizer  ($49/mo)
    - Enterprise: Custom (air-gapped K8s, physics validation, SLA)

Each tier carries a machine-readable feature matrix so the rest of the
codebase can gate capabilities without hard-coding prices.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "TIERS",
    "TIER_ENTERPRISE",
    "TIER_FREE",
    "TIER_MAKER",
    "TIER_PRO",
    "BillingError",
    "SubscriptionTier",
    "get_tier_by_id",
    "get_tier_by_slug",
]


class BillingError(RuntimeError):
    """Raised on billing/subscription configuration or runtime errors."""


@dataclass(frozen=True)
class SubscriptionTier:
    """A single subscription tier with pricing and feature flags.

    Attributes:
        id:            Opaque numeric tier id (Stripe price id suffix).
        slug:          Human/machine-friendly key, e.g. ``"pro"``.
        name:          Display name shown in the UI.
        description:   Short marketing blurb.
        price_usd:     Monthly recurring price in USD. ``None`` for Free.
        annual_price_usd: Optional annual price (if offered).
        stripe_price_id: Stripe *Price* object id used in Checkout. May be a
            live or test price id — resolved at ``BillingService`` init.
        max_nets:      Max netlist complexity / board size limit.
        max_components: Max component count on a single board.
        max_agents:    Max concurrent AI agents.
        cloud_sync:    Whether E2EE cloud sync is enabled.
        cloud_llms:    Whether cloud LLM providers (GPT-4.5, Claude) are used.
        bom_optimizer: Whether advanced BOM optimization is enabled.
        priority_support: Support response SLA tier.
        is_custom:     True for Enterprise (custom-priced, not in public list).
    """

    id: int
    slug: str
    name: str
    description: str
    price_usd: float | None
    annual_price_usd: float | None
    stripe_price_id: str | None
    max_nets: int
    max_components: int
    max_agents: int
    cloud_sync: bool
    cloud_llms: bool
    bom_optimizer: bool
    priority_support: str
    is_custom: bool = False
    features: list[str] = field(default_factory=list)

    @property
    def is_free(self) -> bool:
        return self.price_usd is None or self.price_usd == 0

    @property
    def monthly_price(self) -> float:
        """Convenience accessor returning 0.0 for the Free tier."""
        return self.price_usd or 0.0


# --------------------------------------------------------------------------- #
# Tier catalog — canonical definitions
# --------------------------------------------------------------------------- #
TIER_FREE = SubscriptionTier(
    id=0,
    slug="free",
    name="Community",
    description="Local-first PCB design with open-source AI agents. "
    "Perfect for hobbyists, students, and open-hardware projects.",
    price_usd=None,
    annual_price_usd=None,
    stripe_price_id=None,
    max_nets=50,
    max_components=500,
    max_agents=1,
    cloud_sync=False,
    cloud_llms=False,
    bom_optimizer=False,
    priority_support="community",
    is_custom=False,
    features=[
        "Local LLM inference (DeepSeek-V3, llama.cpp)",
        "Netlist analysis",
        "Routing suggestions",
        "Basic DRC checks",
        "Community support",
    ],
)

TIER_MAKER = SubscriptionTier(
    id=1,
    slug="maker",
    name="Maker",
    description="Local + End-to-end encrypted cloud sync for indie devs "
    "and small teams building 1-5 boards per year.",
    price_usd=19.0,
    annual_price_usd=190.0,
    stripe_price_id="price_maker",
    max_nets=500,
    max_components=5000,
    max_agents=3,
    cloud_sync=True,
    cloud_llms=False,
    bom_optimizer=False,
    priority_support="email_48h",
    is_custom=False,
    features=[
        "Everything in Free",
        "E2EE cloud sync across devices",
        "500 designs / 5 000 components",
        "3 concurrent AI agents",
        "Email support (48h SLA)",
    ],
)

TIER_PRO = SubscriptionTier(
    id=2,
    slug="pro",
    name="Pro",
    description="Cloud LLM copilots + advanced BOM optimization. "
    "Targeted at startups and professional engineers.",
    price_usd=49.0,
    annual_price_usd=490.0,
    stripe_price_id="price_pro",
    max_nets=5000,
    max_components=50000,
    max_agents=10,
    cloud_sync=True,
    cloud_llms=True,
    bom_optimizer=False,
    priority_support="email_24h",
    is_custom=False,
    features=[
        "Everything in Maker",
        "Cloud LLMs: GPT-4.5, Claude 3.5 Sonnet",
        "Advanced BOM optimization (LCSC/JLCPCB)",
        "5 000 designs / 50 000 components",
        "10 concurrent AI agents",
        "Email support (24h SLA)",
    ],
)

TIER_ENTERPRISE = SubscriptionTier(
    id=3,
    slug="enterprise",
    name="Enterprise",
    description="Self-hosted Kubernetes deployment with air-gapped physics "
    "validation, ITAR/GDPR compliance, and dedicated SLA. "
    "Custom pricing.",
    price_usd=None,
    annual_price_usd=None,
    stripe_price_id="price_enterprise",
    max_nets=1_000_000,
    max_components=1_000_000,
    max_agents=100,
    cloud_sync=False,
    cloud_llms=False,
    bom_optimizer=True,
    priority_support="dedicated_slack_4h",
    is_custom=True,
    features=[
        "Everything in Pro",
        "Air-gapped self-hosted Kubernetes",
        "Physics validation (Simbeor field solver integration)",
        "ITAR / GDPR / SOC 2 compliance",
        "SSO / SAML integration",
        "Dedicated account manager",
        "SLA: 4-hour response, 99.9 % uptime",
    ],
)

# Ordered list of public (non-custom) tiers, cheapest → most expensive.
TIERS: list[SubscriptionTier] = [TIER_FREE, TIER_MAKER, TIER_PRO]

# Complete catalog including Enterprise (for admin/internal use).
ALL_TIERS: list[SubscriptionTier] = [*TIERS, TIER_ENTERPRISE]


def get_tier_by_slug(slug: str) -> SubscriptionTier:
    """Look up a tier by its slug (case-insensitive).

    Raises:
        BillingError: If no tier matches.
    """
    for tier in ALL_TIERS:
        if tier.slug.lower() == slug.lower():
            return tier
    raise BillingError(f"Unknown subscription tier slug: {slug!r}")


def get_tier_by_id(tier_id: int) -> SubscriptionTier:
    """Look up a tier by its numeric id.

    Raises:
        BillingError: If no tier matches.
    """
    for tier in ALL_TIERS:
        if tier.id == tier_id:
            return tier
    raise BillingError(f"Unknown subscription tier id: {tier_id}")
