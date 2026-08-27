#!/usr/bin/env python
"""Quick smoke test for the billing module."""
import sys
sys.path.insert(0, "src")

from nexus_eda.billing import (
    TIER_FREE, TIER_MAKER, TIER_PRO, TIER_ENTERPRISE,
    TIERS, BillingService, get_tier_by_slug, get_tier_by_id,
)

print("=== Subscription Tiers ===")
for t in [TIER_FREE, TIER_MAKER, TIER_PRO, TIER_ENTERPRISE]:
    price = f"${t.price_usd}/mo" if t.price_usd else "custom"
    print(f"  {t.name:12s} slug={t.slug:10s} price={price:15s} features={len(t.features)}")

print("\n=== BillingService (no Stripe key) ===")
svc = BillingService()
print(f"  is_configured: {svc.is_configured}")
print(f"  test_mode:     {svc.test_mode}")
cust = svc.get_or_create_customer("demo@nexus-eda.com")
print(f"  customer stub: {cust}")

print("\n  --- Checkout Sessions (paid tiers only) ---")
for tier in TIERS:
    if tier.is_free:
        status = svc.assign_free_tier("demo@nexus-eda.com")
        print(f"  checkout {tier.slug:8s} -> FREE (no checkout needed) status={status.status}")
        continue
    result = svc.create_checkout_session(
        "demo@nexus-eda.com", tier,
        "https://nexus-eda.com/success",
        "https://nexus-eda.com/cancel",
    )
    print(f"  checkout {tier.slug:8s} -> {result.url[:55]}... (test={result.is_test_mode})")

print("\nAll imports and checkout flows verified OK.")
