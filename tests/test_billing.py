# SPDX-License-Identifier: Apache-2.0
"""Tests for the Nexus-EDA billing module — subscription tiers."""

import os
import sys

import pytest

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from nexus_eda.billing import (
    ALL_TIERS,
    TIER_ENTERPRISE,
    TIER_FREE,
    TIER_MAKER,
    TIER_PRO,
    TIERS,
    BillingError,
    BillingService,
    CheckoutResult,
    SubscriptionStatus,
    get_billing_service,
    get_tier_by_id,
    get_tier_by_slug,
    reset_billing_service,
)


# --------------------------------------------------------------------------- #
# Tier model tests
# --------------------------------------------------------------------------- #
class TestTierModels:
    """Tests for SubscriptionTier definitions and lookups."""

    def test_free_tier_is_zero_cost(self):
        """Free tier must have price_usd=None and is_free=True."""
        assert TIER_FREE.price_usd is None
        assert TIER_FREE.is_free
        assert TIER_FREE.monthly_price == 0.0

    def test_maker_tier_pricing(self):
        """Maker tier is $19/month."""
        assert TIER_MAKER.price_usd == 19.0
        assert not TIER_MAKER.is_free
        assert TIER_MAKER.monthly_price == 19.0

    def test_pro_tier_pricing(self):
        """Pro tier is $49/month."""
        assert TIER_PRO.price_usd == 49.0
        assert not TIER_PRO.is_free
        assert TIER_PRO.monthly_price == 49.0

    def test_enterprise_is_custom(self):
        """Enterprise tier is custom-priced (no public price)."""
        assert TIER_ENTERPRISE.is_custom
        assert TIER_ENTERPRISE.price_usd is None

    def test_tier_slugs(self):
        """Each tier has a unique, lowercase slug."""
        slugs = {t.slug for t in ALL_TIERS}
        assert slugs == {"free", "maker", "pro", "enterprise"}

    def test_tier_ids_are_unique(self):
        """Each tier has a unique numeric id."""
        ids = [t.id for t in ALL_TIERS]
        assert len(ids) == len(set(ids))

    def test_tiers_list_excludes_enterprise(self):
        """Public TIERS list has 3 entries (free, maker, pro)."""
        assert len(TIERS) == 3
        assert TIER_ENTERPRISE not in TIERS

    def test_all_tiers_includes_enterprise(self):
        """ALL_TIERS includes Enterprise."""
        assert len(ALL_TIERS) == 4
        assert TIER_ENTERPRISE in ALL_TIERS

    def test_get_tier_by_slug(self):
        assert get_tier_by_slug("free") == TIER_FREE
        assert get_tier_by_slug("MAKER") == TIER_MAKER
        assert get_tier_by_slug("pro") == TIER_PRO
        assert get_tier_by_slug("enterprise") == TIER_ENTERPRISE

    def test_get_tier_by_slug_unknown(self):
        with pytest.raises(BillingError, match="Unknown subscription tier slug"):
            get_tier_by_slug("nonexistent")

    def test_get_tier_by_id(self):
        assert get_tier_by_id(0) == TIER_FREE
        assert get_tier_by_id(1) == TIER_MAKER
        assert get_tier_by_id(2) == TIER_PRO
        assert get_tier_by_id(3) == TIER_ENTERPRISE

    def test_get_tier_by_id_unknown(self):
        with pytest.raises(BillingError, match="Unknown subscription tier id"):
            get_tier_by_id(99)

    def test_maker_enables_cloud_sync(self):
        assert TIER_MAKER.cloud_sync is True

    def test_free_disables_cloud_sync(self):
        assert TIER_FREE.cloud_sync is False

    def test_pro_enables_cloud_llms(self):
        assert TIER_PRO.cloud_llms is True

    def test_maker_disables_cloud_llms(self):
        assert TIER_MAKER.cloud_llms is False

    def test_enterprise_enables_bom_optimizer(self):
        assert TIER_ENTERPRISE.bom_optimizer is True


# --------------------------------------------------------------------------- #
# BillingService tests (no Stripe key → test mode)
# --------------------------------------------------------------------------- #
class TestBillingServiceNoKey:
    """Tests for BillingService when Stripe is not configured."""

    def setup_method(self):
        reset_billing_service()
        # Ensure no env keys leak in.
        for key in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_API_BASE"):
            os.environ.pop(key, None)

    def teardown_method(self):
        reset_billing_service()

    def test_service_is_not_configured_without_key(self):
        svc = BillingService()
        assert not svc.is_configured

    def test_test_mode_when_no_key(self):
        svc = BillingService()
        assert svc.test_mode

    def test_get_or_create_customer_returns_stub_id(self):
        svc = BillingService()
        cust_id = svc.get_or_create_customer("test@example.com")
        assert cust_id.startswith("cus_test_")

    def test_customer_cache(self):
        svc = BillingService()
        first = svc.get_or_create_customer("test@example.com")
        second = svc.get_or_create_customer("test@example.com")
        assert first == second

    def test_create_checkout_session_pro_returns_url(self):
        svc = BillingService()
        result = svc.create_checkout_session(
            customer_email="test@example.com",
            tier=TIER_PRO,
            success_url="https://nexus-eda.com/success",
            cancel_url="https://nexus-eda.com/cancel",
        )
        assert isinstance(result, CheckoutResult)
        assert "checkout.stripe.com/test" in result.url
        assert result.is_test_mode is True
        assert result.session_id.startswith("cs_test_tier_pro_")

    def test_create_checkout_session_maker(self):
        svc = BillingService()
        result = svc.create_checkout_session(
            customer_email="test@example.com",
            tier=TIER_MAKER,
            success_url="https://nexus-eda.com/success",
            cancel_url="https://nexus-eda.com/cancel",
        )
        assert result.is_test_mode is True
        assert "tier_maker" in result.url

    def test_create_checkout_session_free_raises(self):
        svc = BillingService()
        with pytest.raises(BillingError, match="free"):
            svc.create_checkout_session(
                customer_email="test@example.com",
                tier=TIER_FREE,
                success_url="https://nexus-eda.com/success",
                cancel_url="https://nexus-eda.com/cancel",
            )

    def test_create_checkout_session_enterprise_raises(self):
        svc = BillingService()
        with pytest.raises(BillingError, match="custom-priced"):
            svc.create_checkout_session(
                customer_email="test@example.com",
                tier=TIER_ENTERPRISE,
                success_url="https://nexus-eda.com/success",
                cancel_url="https://nexus-eda.com/cancel",
            )

    def test_assign_free_tier(self):
        svc = BillingService()
        status = svc.assign_free_tier("test@example.com")
        assert isinstance(status, SubscriptionStatus)
        assert status.tier == TIER_FREE
        assert status.status == "active"

    def test_get_subscription_status_falls_back_to_free(self):
        svc = BillingService()
        status = svc.get_subscription_status("nobody@example.com")
        assert status.tier == TIER_FREE
        assert status.status == "active"

    def test_customer_portal_returns_test_url(self):
        svc = BillingService()
        url = svc.create_customer_portal_session(
            "test@example.com",
            return_url="https://nexus-eda.com/back",
        )
        assert "billing.stripe.com/test" in url

    def test_webhook_without_secret_raises(self):
        svc = BillingService()
        with pytest.raises(BillingError, match="STRIPE_WEBHOOK_SECRET"):
            svc.handle_webhook(b'{"type": "test"}', "t=123,v1=abc")

    def test_webhook_test_mode_parses_json(self):
        svc = BillingService(webhook_secret="whsec_test")
        event = svc.handle_webhook(b'{"type": "checkout.session.completed"}', "sig")
        assert event["type"] == "checkout.session.completed"


# --------------------------------------------------------------------------- #
# Singleton tests
# --------------------------------------------------------------------------- #
class TestBillingServiceSingleton:

    def teardown_method(self):
        reset_billing_service()

    def test_singleton_returns_same_instance(self):
        svc1 = get_billing_service()
        svc2 = get_billing_service()
        assert svc1 is svc2

    def test_force_refresh_creates_new_instance(self):
        svc1 = get_billing_service()
        svc2 = get_billing_service(force_refresh=True)
        assert svc1 is not svc2

    def test_singleton_propagates_test_mode(self):
        svc = get_billing_service(test_mode=True)
        assert svc.test_mode
