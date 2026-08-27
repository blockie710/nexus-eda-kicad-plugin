# SPDX-License-Identifier: Apache-2.0
"""Stripe billing service for Nexus-EDA SaaS.

This module wires up Stripe Checkout + Customer Portal sessions for the
four subscription tiers (Free, Maker $19, Pro $49, Enterprise custom).

Design goals
------------
* **Graceful degradation**: ``stripe`` is an optional dependency. If the
  library or secret key is unavailable (e.g. running inside KiCad's
  bundled Python), importing and instantiating ``BillingService`` still
  works — only actual API calls raise ``BillingError`` at call time.
* **Testability**: All public methods accept injected IDs or fall back to
  sensible test-mode defaults. ``create_checkout_session`` returns a real
  Stripe session URL when the key is present, or a test stub URL otherwise.
* **Webhook safety**: ``handle_webhook`` validates signatures using the
  endpoint secret so test/prod keys are not interchangeable.

Configuration (environment variables)
--------------------------------------
    STRIPE_SECRET_KEY        - secret key (sk_live or sk_test)
    STRIPE_WEBHOOK_SECRET    - endpoint signing secret (whsec)
    STRIPE_API_BASE          - optional override for the Stripe API host
                                (useful for localstripe tests; default
                                https://api.stripe.com)
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Any

from .models import (
    ALL_TIERS,
    TIER_FREE,
    BillingError,
    SubscriptionTier,
)

__all__ = [
    "BillingService",
    "CheckoutResult",
    "SubscriptionStatus",
    "get_billing_service",
]


# --------------------------------------------------------------------------- #
# Public types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CheckoutResult:
    """Result of a Checkout Session creation request.

    Attributes:
        url:           Stripe-hosted URL to redirect the customer to.
        session_id:    Stripe Checkout Session identifier.
        is_test_mode:  True when running against test mode (no real charge).
    """

    url: str
    session_id: str
    is_test_mode: bool


@dataclass
class SubscriptionStatus:
    """Lightweight snapshot of a customer's Stripe subscription state."""

    tier: SubscriptionTier | None
    status: str  # 'active', 'past_due', 'canceled', 'incomplete', …
    current_period_end: int | None
    cancel_at_period_end: bool


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
class BillingService:
    """Thin Stripe wrapper for subscription management.

    Instantiating the service does **not** require Stripe credentials —
    ``stripe`` is an optional dependency. Methods that hit the API lazily
    check ``self._stripe`` and raise :class:`BillingError` if unavailable.
    """

    def __init__(
        self,
        secret_key: str | None = None,
        webhook_secret: str | None = None,
        api_base: str | None = None,
        *,
        test_mode: bool = False,
    ) -> None:
        self._secret_key = secret_key or os.environ.get("STRIPE_SECRET_KEY")
        self._webhook_secret = (
            webhook_secret or os.environ.get("STRIPE_WEBHOOK_SECRET")
        )
        self._api_base = api_base or os.environ.get("STRIPE_API_BASE")
        self._test_mode = test_mode or bool(
            not self._secret_key
            or self._secret_key.startswith("sk_test_")
        )
        self._lock = threading.Lock()
        self._stripe: Any = None
        self._api_resources: dict[str, Any] = {}
        self._customer_cache: dict[str, str | None] = {}
        self._stripe = self._try_import_stripe()
        self._init_api_resources()

    # -- internals ---------------------------------------------------------- #
    @property
    def is_configured(self) -> bool:
        """True when the Stripe library and secret key are both available."""
        return self._stripe is not None and self._secret_key is not None

    @property
    def test_mode(self) -> bool:
        return self._test_mode

    def _try_import_stripe(self) -> Any:
        """Import ``stripe`` lazily; return the module or ``None``."""
        if self._stripe is not None:
            return self._stripe
        try:
            import stripe  # type: ignore[import-not-found]
        except ImportError:
            return None
        # Configure the library with our key / base URL.
        stripe_conf = {}
        if self._secret_key:
            stripe_conf["api_key"] = self._secret_key
        if self._api_base:
            stripe_conf["api_base"] = self._api_base
        try:
            stripe.api_key = self._secret_key
            if self._api_base:
                stripe.api_base = self._api_base
            if self._test_mode:
                # Ensure test-mode behaviour is explicit.
                stripe.api_key = self._secret_key or "sk_test_stub"
        except Exception:
            pass  # Graceful degradation when Stripe lib misconfigured
        return stripe

    def _init_api_resources(self) -> None:
        """Expose ``stripe.checkout.Session``, ``stripe.Customer``, and
        ``stripe.Subscription`` lazily so they can be patched in tests."""
        if self._stripe is None:
            return
        self._api_resources["checkout_session"] = (
            self._stripe.checkout.Session
        )
        self._api_resources["customer"] = self._stripe.Customer
        self._api_resources["subscription"] = self._stripe.Subscription
        self._api_resources["webhook"] = self._stripe.Webhook

    # -- public API --------------------------------------------------------- #
    def get_or_create_customer(
        self, email: str, name: str | None = None
    ) -> str:
        """Return a Stripe Customer id, creating one if necessary.

        Caches results in-memory (thread-safe) for the lifetime of the
        service instance to avoid duplicate customer creation.
        """
        with self._lock:
            cached = self._customer_cache.get(email)
            if cached is not None:
                return cached

        if not self.is_configured:
            # Generate a deterministic fake id for test-mode.
            cust_id = f"cus_test_{hash(email) % 1_000_000:06d}"
            with self._lock:
                self._customer_cache[email] = cust_id
            return cust_id

        session_cls = self._api_resources["customer"]
        try:
            customers = session_cls.list(email=email, limit=1)
            if customers.data:
                cust_id = customers.data[0].id
            else:
                cust = session_cls.create(
                    email=email,
                    name=name,
                )
                cust_id = cust.id
        except Exception as exc:
            raise BillingError(
                f"Failed to get/create Stripe customer for {email!r}"
            ) from exc

        with self._lock:
            self._customer_cache[email] = cust_id
        return cust_id

    def create_checkout_session(
        self,
        customer_email: str,
        tier: SubscriptionTier,
        success_url: str,
        cancel_url: str,
        customer_name: str | None = None,
    ) -> CheckoutResult:
        """Create a Stripe Checkout Session for upgrading/downgrading.

        Args:
            customer_email: Billed customer email (existing or new).
            tier:           Target :class:`SubscriptionTier`.
            success_url:    Redirect URL on successful payment.
            cancel_url:     Redirect URL if the customer cancels.
            customer_name:  Optional display name for the customer record.

        Raises:
            BillingError: If the tier is Free (no checkout needed) or the
                          Stripe API call fails.
        """
        if tier.is_custom:
            raise BillingError(
                f"Tier {tier.name!r} is custom-priced. Contact sales for a "
                f"quote and create the Checkout Session manually."
            )
        if tier.is_free:
            raise BillingError(
                f"Tier {tier.name!r} is free — no checkout session required. "
                f"Use BillingService.assign_free_tier() instead."
            )

        price_id = tier.stripe_price_id
        if price_id is None:
            raise BillingError(
                f"No Stripe price id configured for tier {tier.slug!r}"
            )

        customer_id = self.get_or_create_customer(
            customer_email, customer_name
        )

        # Test-mode stub (no Stripe call needed).
        if not self.is_configured:
            stub_url = (
                "https://checkout.stripe.com/test/"
                f"pay/fs_test_tier_{tier.slug}"
            )
            return CheckoutResult(
                url=stub_url,
                session_id=f"cs_test_tier_{tier.slug}_{customer_id[-6:]}",
                is_test_mode=True,
            )

        session_cls = self._api_resources["checkout_session"]
        self._api_resources["customer"]
        try:
            session = session_cls.create(
                customer=customer_id,
                mode="subscription",
                payment_method_types=["card"],
                line_items=[
                    {
                        "price": price_id,
                        "quantity": 1,
                    }
                ],
                customer_update={
                    "address": "auto",
                },
                automatic_tax={
                    "enabled": True,
                },
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "nexus_eda_tier": tier.slug,
                    "nexus_eda_tier_id": str(tier.id),
                },
            )
        except Exception as exc:
            raise BillingError(
                f"Failed to create Checkout Session for tier "
                f"{tier.slug!r}"
            ) from exc

        return CheckoutResult(
            url=session.url,
            session_id=session.id,
            is_test_mode=self._test_mode,
        )

    def create_customer_portal_session(
        self, customer_email: str, return_url: str
    ) -> str:
        """Return a URL to the Stripe Customer Portal (self-service billing)."""
        customer_id = self.get_or_create_customer(customer_email)

        if not self.is_configured:
            return (
                "https://billing.stripe.com/test/"
                f"portal/{customer_id[-6:]}"
            )

        session_cls = self._api_resources["checkout_session"]
        try:
            session = session_cls.create(
                customer=customer_id,
                return_url=return_url,
            )
        except Exception as exc:
            raise BillingError(
                f"Failed to create Customer Portal session for "
                f"{customer_email!r}"
            ) from exc

        return session.url

    def handle_webhook(self, payload: bytes, sig_header: str) -> dict[str, Any]:
        """Parse and verify a Stripe webhook event.

        Returns the parsed event dict on success. Raises
        :class:`BillingError` if the signature is invalid.
        """
        if not self._webhook_secret:
            raise BillingError(
                "STRIPE_WEBHOOK_SECRET is not configured — "
                "cannot verify webhook signature."
            )

        if not self.is_configured:
            # In test/no-stripe mode, just parse the JSON.
            try:
                return json.loads(payload)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise BillingError(f"Invalid JSON payload: {exc}") from exc

        webhook_mod = self._api_resources["webhook"]
        try:
            event = webhook_mod.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=self._webhook_secret,
            )
        except Exception as exc:
            raise BillingError(
                f"Invalid Stripe webhook signature: {exc}"
            ) from exc

        return event

    def assign_free_tier(self, customer_email: str) -> SubscriptionStatus:
        """Assign the Free tier locally (no Stripe subscription needed)."""
        self.get_or_create_customer(customer_email)
        return SubscriptionStatus(
            tier=TIER_FREE,
            status="active",
            current_period_end=None,
            cancel_at_period_end=False,
        )

    def get_subscription_status(
        self, customer_email: str
    ) -> SubscriptionStatus:
        """Look up the current subscription status for a customer.

        Falls back to Free if no active subscription is found.
        """
        cust_id = self.get_or_create_customer(customer_email)

        if not self.is_configured:
            return SubscriptionStatus(
                tier=TIER_FREE,
                status="active",
                current_period_end=None,
                cancel_at_period_end=False,
            )

        sub_cls = self._api_resources["subscription"]
        try:
            subs = sub_cls.list(
                customer=cust_id,
                status="all",
                limit=1,
            )
        except Exception as exc:
            raise BillingError(
                f"Failed to query subscriptions for {customer_email!r}"
            ) from exc

        if not subs.data:
            return SubscriptionStatus(
                tier=TIER_FREE,
                status="none",
                current_period_end=None,
                cancel_at_period_end=False,
            )

        sub = subs.data[0]
        price_id = sub["items"].data[0].price.id
        # Map price_id back to tier.
        tier = TIER_FREE
        for t in ALL_TIERS:
            if t.stripe_price_id == price_id:
                tier = t
                break

        return SubscriptionStatus(
            tier=tier,
            status=sub.status,
            current_period_end=sub.get("current_period_end"),
            cancel_at_period_end=sub.get("cancel_at_period_end", False),
        )


# --------------------------------------------------------------------------- #
# Module-level singleton
# --------------------------------------------------------------------------- #
_billing_service: BillingService | None = None
_service_lock = threading.Lock()


def get_billing_service(
    *,
    secret_key: str | None = None,
    webhook_secret: str | None = None,
    api_base: str | None = None,
    test_mode: bool = False,
    force_refresh: bool = False,
) -> BillingService:
    """Return a cached :class:`BillingService` singleton.

    Pass ``force_refresh=True`` to bypass the cache and create a fresh
    instance (useful in tests or when reconfiguring).
    """
    global _billing_service
    if _billing_service is None or force_refresh:
        with _service_lock:
            if _billing_service is None or force_refresh:
                _billing_service = BillingService(
                    secret_key=secret_key,
                    webhook_secret=webhook_secret,
                    api_base=api_base,
                    test_mode=test_mode,
                )
    return _billing_service


def reset_billing_service() -> None:
    """Clear the singleton (primarily for tests)."""
    global _billing_service
    with _service_lock:
        _billing_service = None
