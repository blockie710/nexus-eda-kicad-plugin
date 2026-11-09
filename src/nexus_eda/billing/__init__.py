# SPDX-License-Identifier: Apache-2.0
"""Nexus-EDA billing integration with Stripe subscription tiers.

Provides subscription tier management, Stripe checkout session creation,
and webhook handling for the SaaS revenue model.
"""

from .models import (
    BillingError,
    SubscriptionTier,
    TIER_FREE,
    TIER_MAKER,
    TIER_PRO,
    TIER_ENTERPRISE,
    TIERS,
    ALL_TIERS,
    get_tier_by_id,
    get_tier_by_slug,
)
from .service import (
    BillingService,
    CheckoutResult,
    SubscriptionStatus,
    get_billing_service,
    reset_billing_service,
)

__all__ = [
    "BillingError",
    "SubscriptionTier",
    "BillingService",
    "CheckoutResult",
    "SubscriptionStatus",
    "TIER_FREE",
    "TIER_MAKER",
    "TIER_PRO",
    "TIER_ENTERPRISE",
    "TIERS",
    "ALL_TIERS",
    "get_tier_by_id",
    "get_tier_by_slug",
    "get_billing_service",
    "reset_billing_service",
]
