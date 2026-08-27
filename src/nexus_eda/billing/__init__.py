# SPDX-License-Identifier: Apache-2.0
"""Nexus-EDA billing integration with Stripe subscription tiers.

Provides subscription tier management, Stripe checkout session creation,
and webhook handling for the SaaS revenue model.
"""

from .models import (
    ALL_TIERS,
    TIER_ENTERPRISE,
    TIER_FREE,
    TIER_MAKER,
    TIER_PRO,
    TIERS,
    BillingError,
    SubscriptionTier,
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
    "ALL_TIERS",
    "TIERS",
    "TIER_ENTERPRISE",
    "TIER_FREE",
    "TIER_MAKER",
    "TIER_PRO",
    "BillingError",
    "BillingService",
    "CheckoutResult",
    "SubscriptionStatus",
    "SubscriptionTier",
    "get_billing_service",
    "get_tier_by_id",
    "get_tier_by_slug",
    "reset_billing_service",
]
